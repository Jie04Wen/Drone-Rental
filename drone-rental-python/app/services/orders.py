from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from math import ceil

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..alipay import AlipayClient
from ..common import BusinessException, C, ResultCode, serialize
from ..config import Settings
from ..models import AirspaceRecord, Drone, FaultReport, OrderReturnLog, Payment, RentalOrder, User
from ..schemas import (DepositSettlementDTO, OrderCreateDTO, ReturnApplyDTO, ReturnShipmentDTO)

from ..redis import invalidate_drone_cache
from ..security import CurrentUser
from ..storage import StorageService
from .drones import check_rentable, decrease_stock, get_drone, increase_stock
from .helpers import make_no, paginate
from .notifications import send_notification
from .files import sign_payload_field
from .users import check_operable, check_qualification
import logging

logger = logging.getLogger(__name__)

ORDER_STATUS_DESC = {
    0: "待支付", 1: "待发货", 2: "待收货", 3: "租赁中", 4: "已归还",
    5: "已取消", 6: "已退款", 7: "待归还/待寄回", 8: "待商家收货",
}
PAYMENT_TIMEOUT = timedelta(minutes=30)
PAYMENT_TIMEOUT_REASON = "支付超时，订单自动取消"


def get_order(db: Session, order_id: int) -> RentalOrder:
    order = db.scalar(select(RentalOrder).where(RentalOrder.id == order_id, RentalOrder.deleted == 0))
    if order is None:
        raise BusinessException(ResultCode.ORDER_NOT_EXIST)
    return order


def get_order_for_update(db: Session, order_id: int) -> RentalOrder:
    order = db.scalar(
        select(RentalOrder)
        .where(RentalOrder.id == order_id, RentalOrder.deleted == 0)
        .with_for_update()
    )
    if order is None:
        raise BusinessException(ResultCode.ORDER_NOT_EXIST)
    return order


def get_payment_by_order(db: Session, order_id: int) -> Payment | None:
    """Corresponds to PaymentServiceImpl.getByOrderId()."""
    return db.scalar(
        select(Payment).where(Payment.order_id == order_id, Payment.deleted == 0).limit(1)
    )


def payment_amount(order: RentalOrder) -> Decimal:
    return (order.total_amount or Decimal("0")) + (order.deposit_amount or Decimal("0"))


def payment_deadline(order: RentalOrder) -> datetime:
    return order.created_time + PAYMENT_TIMEOUT


def remaining_payment_seconds(order: RentalOrder, now: datetime | None = None) -> int:
    if order.order_status != C.ORDER_UNPAID:
        return 0
    return max(ceil((payment_deadline(order) - (now or datetime.now())).total_seconds()), 0)


def _cancel_expired_order(
        db: Session,
        order: RentalOrder,
        now: datetime | None = None,
) -> bool:
    now = now or datetime.now()
    if order.order_status != C.ORDER_UNPAID or now < payment_deadline(order):
        return False
    order.order_status = C.ORDER_CANCELLED
    order.cancel_reason = PAYMENT_TIMEOUT_REASON
    order.cancel_time = now
    db.scalar(select(Drone).where(Drone.id == order.drone_id).with_for_update())
    increase_stock(db, order.drone_id, 1, order.id, None)
    return True


def close_expired_unpaid_orders(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now()
    expired_ids = db.scalars(select(RentalOrder.id).where(
        RentalOrder.order_status == C.ORDER_UNPAID,
        RentalOrder.deleted == 0,
        RentalOrder.created_time <= now - PAYMENT_TIMEOUT,
    )).all()
    closed = 0
    for order_id in expired_ids:
        order = get_order_for_update(db, order_id)
        if _cancel_expired_order(db, order, now):
            closed += 1
    db.commit()
    if closed:
        invalidate_drone_cache()
    return closed


def ensure_payment_open(db: Session, order: RentalOrder) -> None:
    if _cancel_expired_order(db, order):
        db.commit()
        invalidate_drone_cache()
        raise BusinessException(message="订单已超过30分钟支付有效期，系统已自动取消")


def early_return_rental_refund(
        order: RentalOrder,
        fault_full_refund: bool = False,
) -> tuple[int, int, Decimal]:
    """Return chargeable days, unused days and refundable rent for an early return."""
    rental_days = max(int(order.rental_days or 0), 0)
    if rental_days == 0 or order.return_shipped_time is None:
        return rental_days, 0, Decimal("0.00")
    if fault_full_refund:
        return 0, rental_days, (order.total_amount or Decimal("0")).quantize(Decimal("0.01"))

    used_days = (order.return_shipped_time.date() - order.rental_start_time.date()).days + 1
    chargeable_days = min(max(used_days, 1), rental_days)
    unused_days = rental_days - chargeable_days
    refundable_rent = min(
        (order.unit_price or Decimal("0")) * Decimal(unused_days),
        order.total_amount or Decimal("0"),
    ).quantize(Decimal("0.01"))
    return chargeable_days, unused_days, refundable_rent


def returned_on_service_start_day(order: RentalOrder) -> bool:
    if order.return_shipped_time is None:
        return False
    service_start_time = order.receive_time or order.rental_start_time
    return order.return_shipped_time.date() == service_start_time.date()


def is_same_day_fault_return(db: Session, order: RentalOrder) -> bool:
    if not returned_on_service_start_day(order):
        return False
    return db.scalar(select(FaultReport.id).where(
        FaultReport.order_id == order.id,
        FaultReport.deleted == 0,
        FaultReport.audit_status == C.FAULT_CONFIRMED,
    ).limit(1)) is not None


def add_return_log(
        db: Session,
        order: RentalOrder,
        action: str,
        from_status: int,
        to_status: int,
        current: CurrentUser,
        remark: str | None = None,
) -> None:
    db.add(OrderReturnLog(
        order_id=order.id, order_no=order.order_no, action=action,
        from_status=from_status, to_status=to_status,
        operator_id=current.user_id, operator_role=current.role,
        express_company=order.return_express_company,
        express_no=order.return_express_no, remark=remark,
    ))


def notify_admins(db: Session, title: str, content: str, order_no: str) -> None:
    admins = db.scalars(select(User).where(
        User.role == C.ROLE_ADMIN, User.status == C.USER_STATUS_NORMAL, User.deleted == 0
    )).all()
    for admin in admins:
        send_notification(db, admin.id, title, content, "order", order_no)


def page_payments(
        db: Session,
        page_num: int,
        page_size: int,
        payment_status: int | None = None,
        user_id: int | None = None,
) -> dict:
    """Corresponds to PaymentServiceImpl.pagePayments()."""
    stmt = select(Payment).where(Payment.deleted == 0)
    if payment_status is not None:
        stmt = stmt.where(Payment.payment_status == payment_status)
    if user_id is not None:
        stmt = stmt.where(Payment.user_id == user_id)
    return paginate(db, stmt.order_by(Payment.created_time.desc()), page_num, page_size)


def order_vo(db: Session, order: RentalOrder, storage: StorageService | None = None) -> dict:
    data = serialize(order);
    data.pop("deleted", None);
    data.pop("updatedTime", None)
    user = db.get(User, order.user_id);
    drone = db.get(Drone, order.drone_id)
    record = db.get(AirspaceRecord, order.airspace_record_id) if order.airspace_record_id else None
    payment = get_payment_by_order(db, order.id)
    fault_full_refund = is_same_day_fault_return(db, order)
    chargeable_days, unused_days, rental_refund = early_return_rental_refund(
        order, fault_full_refund
    )
    data.update({"username": (user.nickname or user.username) if user else None,
                 "droneModel": drone.model if drone else None, "droneImage": drone.image if drone else None,
                 "regionName": record.region_name if record else None,
                 "payableAmount": payment.amount if payment else payment_amount(order),
                 "paymentMethod": payment.payment_method if payment else None,
                 "paymentStatus": payment.payment_status if payment else None,
                 "payTime": payment.payment_time if payment else None,
                 "payDeadline": payment_deadline(order),
                 "remainingPaymentSeconds": remaining_payment_seconds(order),
                 "refundedAmount": payment.refund_amount or Decimal("0") if payment else Decimal("0"),
                 "chargeableRentalDays": chargeable_days,
                 "unusedRentalDays": unused_days,
                 "rentalRefundAmount": rental_refund,
                 "faultFullRefund": fault_full_refund,
                 # Corresponds to OrderVO.getOrderStatusDesc().
                 "orderStatusDesc": ORDER_STATUS_DESC.get(order.order_status, "未知")})
    if storage is not None:
        sign_payload_field(data, "droneImage", "droneImageKey", storage)
    return data


def create_order(db: Session, dto: OrderCreateDTO, current: CurrentUser) -> dict:
    """Corresponds to OrderServiceImpl.createOrder; caller owns one transaction."""
    check_operable(db, current.user_id);
    check_qualification(db, current.user_id)
    drone = get_drone(db, dto.drone_id);
    check_rentable(drone)
    if dto.airspace_record_id is not None:
        record = db.scalar(select(AirspaceRecord).where(AirspaceRecord.id == dto.airspace_record_id,
                                                        AirspaceRecord.deleted == 0))
        if record is None: raise BusinessException(ResultCode.AIRSPACE_NOT_EXIST)
        if record.user_id != current.user_id: raise BusinessException(message="该空域备案不属于当前用户")
        if record.audit_status != C.AUDIT_APPROVED: raise BusinessException(ResultCode.AIRSPACE_NOT_APPROVED)
    days = (dto.end_date - dto.start_date).days + 1
    if days <= 0: raise BusinessException(message="租赁结束日期必须大于等于开始日期")
    order = RentalOrder(order_no=make_no("ORD"), user_id=current.user_id, drone_id=dto.drone_id,
                        airspace_record_id=dto.airspace_record_id,
                        rental_start_time=datetime.combine(dto.start_date, time.min),
                        rental_end_time=datetime.combine(dto.end_date, time(23, 59, 59)), rental_days=days,
                        unit_price=drone.price_per_day, total_amount=drone.price_per_day * Decimal(days),
                        deposit_amount=drone.deposit or Decimal("0"), deposit_status=C.DEPOSIT_PENDING,
                        deposit_deduction_amount=Decimal("0"), deposit_refund_amount=Decimal("0"),
                        order_status=C.ORDER_UNPAID, remark=dto.remark,
                        delivery_address=None)  # Java ignores deliveryAddress during creation; payment supplies it later.
    try:
        db.add(order);
        db.flush()
        decrease_stock(db, drone.id, 1, order.id, current.user_id)
        db.add(Payment(payment_no=make_no("PAY"), order_id=order.id, order_no=order.order_no,
                       user_id=order.user_id, amount=payment_amount(order), payment_type=C.PAYMENT_ORDER,
                       payment_method="SIMULATED", payment_status=C.PAYMENT_UNPAID))
        db.commit()
        invalidate_drone_cache()
        db.refresh(order)
    except Exception:
        db.rollback()
        raise
    return order_vo(db, order)


def ensure_owner(order: RentalOrder, current: CurrentUser, admin_allowed: bool = False) -> None:
    if order.user_id != current.user_id and not (admin_allowed and current.role == C.ROLE_ADMIN):
        raise BusinessException(ResultCode.FORBIDDEN)


def pay(
        db: Session,
        order_id: int,
        address: str | None,
        payment_method: str | None,
        current: CurrentUser,
        settings: Settings,
) -> dict[str, str]:
    """Corresponds to OrderController.pay and OrderServiceImpl.simulatePay."""
    order = get_order_for_update(db, order_id);
    ensure_owner(order, current)
    if order.order_status != C.ORDER_UNPAID: raise BusinessException(ResultCode.ORDER_ALREADY_PAID)
    ensure_payment_open(db, order)
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id, Payment.deleted == 0).limit(1))
    if payment is None:
        payment = Payment(payment_no=make_no("PAY"), order_id=order.id, order_no=order.order_no,
                          user_id=order.user_id, amount=payment_amount(order), payment_type=C.PAYMENT_ORDER,
                          payment_method="SIMULATED", payment_status=C.PAYMENT_UNPAID);
        db.add(payment)

    if address and address.strip(): order.delivery_address = address.strip()

    if settings.alipay_enabled and payment_method == "alipay":
        # 已支付订单自动对账
        client = AlipayClient(settings)
        # 先查询支付宝，避免已经支付的订单再次创建交易
        trade = client.query_trade(order.order_no)

        if trade.get("tradeStatus") in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
            try:
                alipay_amount = Decimal(str(trade.get("totalAmount")))
            except (InvalidOperation, ValueError, TypeError):
                raise BusinessException(message="支付宝返回的交易金额格式错误")

            if alipay_amount != payment.amount:
                raise BusinessException(message="支付宝交易金额与本地订单金额不一致")

            confirm_paid_callback(db, order.id, "alipay")
            return {"channel": "alipay_confirmed"}

        form = client.create_page_pay(
            order.order_no,
            f"无人机租赁订单 {order.order_no}",
            format(payment.amount, "f"),
            settings.alipay_return_url,
            payment_deadline(order),
        )
        if form is None:
            # 检测私钥、公钥、网关 配置是否正确
            raise BusinessException(
                message="支付宝支付创建失败，请检查应用私钥、支付宝公钥和网关配置"
            )
        payment.payment_method = "alipay"
        db.commit()
        return {"channel": "alipay_form", "form": form}

    order.order_status = C.ORDER_PAID
    if payment_method:
        payment.payment_method = payment_method
    payment.payment_status = C.PAYMENT_PAID;
    payment.payment_time = datetime.now()
    send_notification(db, order.user_id, "订单支付成功",
                      f"您的订单 {order.order_no} 已支付成功，等待商家发货。",
                      "payment", order.order_no)
    db.commit()
    return {"channel": "simulated"}


def confirm_paid_callback(db: Session, order_id: int, payment_method: str | None) -> None:
    """Corresponds to OrderServiceImpl.confirmPaidByCallback."""
    order = get_order_for_update(db, order_id)
    if order.order_status != C.ORDER_UNPAID:
        if order.order_status == C.ORDER_CANCELLED and order.cancel_reason == PAYMENT_TIMEOUT_REASON:
            raise BusinessException(message="订单已超过30分钟支付有效期，不能确认支付")
        return
    ensure_payment_open(db, order)
    order.order_status = C.ORDER_PAID
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id, Payment.deleted == 0).limit(1))
    if payment is None:
        payment = Payment(payment_no=make_no("PAY"), order_id=order.id, order_no=order.order_no,
                          user_id=order.user_id, amount=payment_amount(order), payment_type=C.PAYMENT_ORDER,
                          payment_method=payment_method or "SIMULATED", payment_status=C.PAYMENT_UNPAID)
        db.add(payment)
    if payment_method:
        payment.payment_method = payment_method
    payment.payment_status = C.PAYMENT_PAID
    payment.payment_time = datetime.now()
    send_notification(db, order.user_id, "订单支付成功",
                      f"您的订单 {order.order_no} 已支付成功，等待商家发货。",
                      "payment", order.order_no)
    db.commit()


def cancel(db: Session, order_id: int, reason: str | None, current: CurrentUser) -> None:
    order = get_order_for_update(db, order_id)
    ensure_owner(order, current, admin_allowed=True)
    if order.order_status != C.ORDER_UNPAID: raise BusinessException(ResultCode.ORDER_CANNOT_CANCEL)
    order.order_status = C.ORDER_CANCELLED
    order.cancel_reason = reason
    order.cancel_time = datetime.now()
    db.scalar(select(Drone).where(Drone.id == order.drone_id).with_for_update())
    increase_stock(db, order.drone_id, 1, order.id, current.user_id)
    db.commit()
    invalidate_drone_cache()


def apply_return(
        db: Session,
        order_id: int,
        dto: ReturnApplyDTO,
        current: CurrentUser,
) -> dict[str, int | str]:
    order = get_order_for_update(db, order_id)
    ensure_owner(order, current)
    if order.order_status != C.ORDER_RENTING:
        raise BusinessException(message="只有租赁中的订单可以申请退租")
    reason = (dto.reason or "").strip()
    before = order.order_status
    order.order_status = C.ORDER_RETURN_REQUESTED
    order.return_applied_time = datetime.now()
    order.return_apply_reason = reason or None
    add_return_log(db, order, "apply_return", before, order.order_status, current, reason or None)
    send_notification(
        db, order.user_id, "退租申请已提交",
        f"您的订单 {order.order_no} 已进入待寄回状态，请填写寄回物流。",
        "order", order.order_no,
    )
    notify_admins(
        db, "用户申请退租",
        f"订单 {order.order_no} 已申请退租，等待用户填写寄回物流。",
        order.order_no,
    )
    db.commit()
    return {"orderStatus": order.order_status, "orderStatusDesc": ORDER_STATUS_DESC[order.order_status]}


def submit_return_shipment(
        db: Session,
        order_id: int,
        dto: ReturnShipmentDTO,
        current: CurrentUser,
) -> dict[str, int | str]:
    order = get_order_for_update(db, order_id)
    ensure_owner(order, current)
    if order.order_status != C.ORDER_RETURN_REQUESTED:
        raise BusinessException(message="只有待寄回订单可以填写寄回物流")
    company, express_no = dto.express_company.strip(), dto.express_no.strip()
    if not company or not express_no:
        raise BusinessException(message="寄回快递公司和快递单号不能为空")
    before = order.order_status
    order.return_express_company = company
    order.return_express_no = express_no
    order.return_shipped_time = datetime.now()
    order.order_status = C.ORDER_RETURN_SHIPPED
    add_return_log(db, order, "submit_return_shipment", before, order.order_status, current,
                   f"{company} {express_no}")
    send_notification(
        db, order.user_id, "寄回物流已提交",
        f"您的订单 {order.order_no} 已提交寄回物流，等待商家收货验机。",
        "order", order.order_no,
    )
    notify_admins(
        db, "退租设备已寄回",
        f"订单 {order.order_no} 已填写寄回物流：{company} {express_no}，请收货后验机并结算押金。",
        order.order_no,
    )
    db.commit()
    return {"orderStatus": order.order_status, "orderStatusDesc": ORDER_STATUS_DESC[order.order_status]}


def _paid_payment(db: Session, order: RentalOrder) -> Payment:
    payment = get_payment_by_order(db, order.id)
    if payment is None:
        raise BusinessException(ResultCode.PAYMENT_NOT_EXIST)
    if payment.payment_status not in (C.PAYMENT_PAID, C.PAYMENT_PARTIALLY_REFUNDED):
        raise BusinessException(message="支付记录状态不允许退款")
    return payment


def _refund_channel(
        order: RentalOrder,
        payment: Payment,
        amount: Decimal,
        reason: str,
        request_no: str,
        settings: Settings,
) -> None:
    if amount <= 0:
        return
    if settings.alipay_enabled and (payment.payment_method or "").lower() == "alipay":
        response = AlipayClient(settings).refund(
            order.order_no, format(amount, "f"), reason, request_no
        )
        try:
            refunded = Decimal(str(response.get("refundFee")))
        except (InvalidOperation, ValueError, TypeError):
            refunded = Decimal("-1")
        if refunded != amount:
            logger.error(
                "Alipay refund failed or amount mismatched: orderNo=%s expected=%s response=%s",
                order.order_no, amount, response,
            )
            raise BusinessException(ResultCode.REFUND_FAILED, "支付宝退款失败或退款金额不一致")


def settle_deposit(
        db: Session,
        order_id: int,
        dto: DepositSettlementDTO,
        current: CurrentUser,
        settings: Settings,
) -> dict[str, Decimal | int]:
    order = get_order_for_update(db, order_id)
    if order.order_status != C.ORDER_RETURN_SHIPPED:
        raise BusinessException(message="只有用户已寄回、待商家收货的订单才能验机并结算押金")
    if order.deposit_status != C.DEPOSIT_PENDING:
        raise BusinessException(message="该订单押金已经结算，不能重复操作")

    deposit = order.deposit_amount or Decimal("0")
    deduction = dto.deduction_amount.quantize(Decimal("0.01"))
    reason = (dto.deduction_reason or "").strip()
    if deduction > deposit:
        raise BusinessException(message="押金扣除金额不能超过订单押金")
    if deduction > 0 and not reason:
        raise BusinessException(message="扣除押金时必须填写扣除原因")

    fault_full_refund = is_same_day_fault_return(db, order)
    if fault_full_refund and deduction > 0:
        raise BusinessException(message="当天因故障退还应全额退款，不允许扣除押金")

    deposit_refund = deposit - deduction
    chargeable_days, unused_days, rental_refund = early_return_rental_refund(
        order, fault_full_refund
    )
    total_refund = deposit_refund + rental_refund
    payment = _paid_payment(db, order)
    if total_refund > 0:
        already_refunded = payment.refund_amount or Decimal("0")
        paid_deposit = max(payment.amount - (order.total_amount or Decimal("0")), Decimal("0"))
        if deposit_refund > paid_deposit:
            raise BusinessException(message="支付单未实收足额押金，不能执行押金退款")
        if already_refunded + total_refund > payment.amount:
            raise BusinessException(message="累计退款金额不能超过实付金额")
        refund_reason = (
            f"设备故障当天退还全额退款：租金{rental_refund:.2f}元、押金{deposit_refund:.2f}元"
            if fault_full_refund else
            f"设备归还结算：押金退还{deposit_refund:.2f}元，提前归还租金退还{rental_refund:.2f}元"
        )
        _refund_channel(order, payment, total_refund, refund_reason,
                        f"RETURN-{order.id}", settings)
        payment.refund_amount = already_refunded + total_refund
        payment.refund_time = datetime.now()
        payment.refund_reason = refund_reason
        payment.payment_status = (C.PAYMENT_REFUNDED if payment.refund_amount == payment.amount
                                  else C.PAYMENT_PARTIALLY_REFUNDED)

    order.deposit_deduction_amount = deduction
    order.deposit_refund_amount = deposit_refund
    order.deposit_deduction_reason = reason or None
    order.deposit_settled_time = datetime.now()
    order.deposit_settled_by = current.user_id
    order.deposit_status = (C.DEPOSIT_REFUNDED if deduction == 0
                            else C.DEPOSIT_FULLY_DEDUCTED if deduction == deposit
    else C.DEPOSIT_PARTIALLY_DEDUCTED)
    before = order.order_status
    order.order_status = C.ORDER_RETURNED
    add_return_log(db, order, "inspect_and_settle", before, order.order_status, current,
                   ("故障当天退还，全额退款；" if fault_full_refund else "")
                   + f"计费{chargeable_days}天，退还{unused_days}天租金{rental_refund:.2f}元；"
                     f"押金退还{deposit_refund:.2f}元，扣除{deduction:.2f}元"
                   + (f"，扣除原因：{reason}" if reason else ""))
    increase_stock(db, order.drone_id, 1, order.id, current.user_id)
    send_notification(
        db, order.user_id, "设备归还及费用结算完成",
        f"您的订单 {order.order_no} 已确认归还，押金退还 {deposit_refund:.2f} 元，"
        f"扣除 {deduction:.2f} 元，提前归还租金退还 {rental_refund:.2f} 元。",
        "payment", order.order_no,
    )
    db.commit()
    invalidate_drone_cache()
    return {"depositAmount": deposit, "deductionAmount": deduction,
            "depositRefundAmount": deposit_refund, "rentalRefundAmount": rental_refund,
            "refundAmount": total_refund, "chargeableRentalDays": chargeable_days,
            "unusedRentalDays": unused_days, "faultFullRefund": fault_full_refund,
            "depositStatus": order.deposit_status}


def refund_order_full(
        db: Session,
        order_id: int,
        reason: str,
        current: CurrentUser,
        settings: Settings,
) -> dict[str, Decimal | str]:
    order = get_order_for_update(db, order_id)
    if order.order_status != C.ORDER_PAID:
        raise BusinessException(message="只有待发货订单可以执行全额退款")
    reason = reason.strip()
    if not reason:
        raise BusinessException(message="退款原因不能为空")
    payment = _paid_payment(db, order)
    if payment.refund_amount and payment.refund_amount > 0:
        raise BusinessException(message="该支付单已发生退款，不能重复执行全额退款")

    _refund_channel(order, payment, payment.amount, reason, f"FULL-{order.id}", settings)
    payment.payment_status = C.PAYMENT_REFUNDED
    payment.refund_time = datetime.now()
    payment.refund_amount = payment.amount
    payment.refund_reason = reason
    order.order_status = C.ORDER_REFUNDED
    order.cancel_reason = reason
    order.cancel_time = datetime.now()
    order.deposit_status = C.DEPOSIT_REFUNDED
    order.deposit_refund_amount = min(
        order.deposit_amount or Decimal("0"),
        max(payment.amount - (order.total_amount or Decimal("0")), Decimal("0")),
    )
    order.deposit_deduction_amount = Decimal("0")
    order.deposit_settled_time = datetime.now()
    order.deposit_settled_by = current.user_id
    increase_stock(db, order.drone_id, 1, order.id, current.user_id)
    send_notification(db, order.user_id, "订单退款成功",
                      f"您的订单 {order.order_no} 已全额退款 {payment.amount:.2f} 元，原因：{reason}",
                      "payment", order.order_no)
    db.commit()
    invalidate_drone_cache()
    return {"mode": "full", "refundAmount": payment.amount}


def change_state(db: Session, order_id: int, action: str, current: CurrentUser,
                 reason: str | None = None, express_company: str | None = None,
                 express_no: str | None = None, settings: Settings | None = None) -> None:
    order = get_order(db, order_id)
    if action == "receive":
        ensure_owner(order, current)
        if order.order_status != C.ORDER_SHIPPED: raise BusinessException(message="订单状态不允许确认收货")
        order.order_status = C.ORDER_RENTING;
        order.receive_time = datetime.now()
    elif action == "apply_return":
        raise BusinessException(message="请使用退租申请专用接口")
    elif action in {"return", "refund"}:
        raise BusinessException(message="请使用押金结算或退款专用接口")
    elif action == "ship":
        if order.order_status != C.ORDER_PAID: raise BusinessException(
            message="订单状态不允许发货，只有已支付的订单才能发货")
        order.order_status = C.ORDER_SHIPPED;
        order.ship_time = datetime.now();
        order.remark = f"快递公司: {express_company}, 快递单号: {express_no}"
        send_notification(db, order.user_id, "订单已发货",
                          f"您的订单 {order.order_no} 已发货，快递公司：{express_company}，快递单号：{express_no}",
                          "order", order.order_no)
    db.commit()
