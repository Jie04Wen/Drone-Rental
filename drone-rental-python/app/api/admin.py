from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..common import BusinessException, C, ResultCode, result, serialize
from ..config import Settings, get_settings
from ..database import get_db
from ..models import (AirspaceRecord, Comment, CreditRecord, Drone, FaultReport,
                      MaintenanceTicket, OrderReturnLog, RentalOrder, User, UserQualification)
from ..schemas import (AuditDTO, DepositSettlementDTO, DroneDTO, MaintenanceTicketDTO,
                       RefundDTO)
from ..security import CurrentUser, require_admin
from ..storage import get_storage
from ..passwords import encode_password
from ..services.drones import add_drone, get_drone, stock_log
from ..services.helpers import paginate
from ..services.files import (sign_payload_field, signed_file_data,
                              validate_drone_keys)
from ..services.orders import (change_state, get_order, order_vo, refund_order_full,
                               settle_deposit)
from ..services.notifications import send_notification
from ..services.support import (audit_fault, comment_vo, complete_ticket, fault_vo,
                                start_ticket, ticket_vo, update_ticket)
from ..services.users import get_user, user_vo
from ..redis import invalidate_drone_cache

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def get_qualification(db: Session, item_id: int) -> UserQualification:
    item = db.scalar(select(UserQualification).where(UserQualification.id == item_id, UserQualification.deleted == 0))
    if item is None: raise BusinessException(ResultCode.QUALIFICATION_NOT_EXIST)
    return item


@router.get("/user/list")
def users(page: int = 1, pageSize: int = 10, keyword: str | None = None, status: int | None = None,
          db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    stmt = select(User).where(User.deleted == 0)
    if keyword: stmt = stmt.where(or_(User.username.contains(keyword), User.nickname.contains(keyword), User.phone.contains(keyword)))
    if status is not None: stmt = stmt.where(User.status == status)
    paged = paginate(db, stmt.order_by(User.created_time.desc()), page, pageSize)
    storage = get_storage(settings)
    paged["records"] = [user_vo(db, item, True, storage) for item in paged["records"]]; return result(paged)


@router.get("/user/qualification/list")
def qualifications(pageNum: int = 1, pageSize: int = 10, auditStatus: int | None = None,
                   db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    stmt = select(UserQualification).where(UserQualification.deleted == 0)
    if auditStatus is not None: stmt = stmt.where(UserQualification.audit_status == auditStatus)
    paged = paginate(db, stmt.order_by(UserQualification.created_time.desc()), pageNum, pageSize)
    records = []
    storage = get_storage(settings)
    for item in paged["records"]:
        data = {key: value for key, value in result(item)["data"].items() if key not in ("deleted", "updatedTime", "auditorId")}
        sign_payload_field(data, "certificateImage", "certificateImageKey", storage)
        user = db.get(User, item.user_id); data["username"] = (user.nickname or user.username) if user else None; records.append(data)
    paged["records"] = records; return result(paged)


@router.get("/user/qualification/stats")
def qualification_stats(db: Session = Depends(get_db)):
    today = datetime.combine(date.today(), time.min)
    count = lambda *conditions: int(db.scalar(select(func.count()).select_from(UserQualification).where(
        UserQualification.deleted == 0, *conditions)) or 0)
    return result({"pending": count(UserQualification.audit_status == 0),
                   "todayApproved": count(UserQualification.audit_status == 1, UserQualification.audit_time >= today),
                   "todayRejected": count(UserQualification.audit_status == 2, UserQualification.audit_time >= today),
                   "total": count(UserQualification.audit_status != 0)})


@router.get("/user/qualification/{item_id}")
def qualification_detail(item_id: int, db: Session = Depends(get_db),
                         settings: Settings = Depends(get_settings)):
    data = serialize(get_qualification(db, item_id))
    sign_payload_field(data, "certificateImage", "certificateImageKey", get_storage(settings))
    return result(data)


@router.get("/user/qualification/{item_id}/certificate-url")
def qualification_certificate_url(item_id: int, db: Session = Depends(get_db),
                                  settings: Settings = Depends(get_settings)):
    item = get_qualification(db, item_id)
    return result(signed_file_data(get_storage(settings), item.certificate_image, settings))


@router.put("/user/qualification/{item_id}/audit")
def qualification_audit(item_id: int, dto: AuditDTO, db: Session = Depends(get_db), current: CurrentUser = Depends(require_admin)):
    item = get_qualification(db, item_id)
    if item.audit_status != C.AUDIT_PENDING: raise BusinessException(message="该资质已审核，不能重复审核")
    item.audit_status = dto.audit_status; item.audit_remark = dto.audit_remark
    item.audit_time = datetime.now(); item.auditor_id = current.user_id
    result_text = "已通过" if dto.audit_status == C.AUDIT_APPROVED else "未通过"
    send_notification(db, item.user_id, "飞行资质审核结果",
                      f"您的飞行资质申请（证书号：{item.certificate_no}）审核{result_text}。",
                      "audit", str(item.id))
    db.commit(); return result()


@router.get("/user/{user_id}")
def user_detail(user_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return result(user_vo(db, get_user(db, user_id), True, get_storage(settings)))


@router.get("/user/{user_id}/avatar-url")
def user_avatar_url(user_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return result(signed_file_data(get_storage(settings), get_user(db, user_id).avatar, settings))


@router.put("/user/{user_id}/status")
def user_status(user_id: int, status: int, db: Session = Depends(get_db)):
    user = get_user(db, user_id)
    if user.role == C.ROLE_ADMIN and status == C.USER_STATUS_DISABLED: raise BusinessException(message="不能禁用管理员账号")
    user.status = status; db.commit(); return result()


@router.put("/user/{user_id}/credit")
def user_credit(user_id: int, creditStatus: int, reason: str | None = None, db: Session = Depends(get_db),
                current: CurrentUser = Depends(require_admin)):
    user, operator = get_user(db, user_id), get_user(db, current.user_id); before = user.credit_status
    user.credit_status = creditStatus
    db.add(CreditRecord(user_id=user_id, change_type=1 if creditStatus == 0 else 2, before_status=before,
        after_status=creditStatus, reason=reason or ("管理员标记为诚信不良" if creditStatus == 0 else "管理员恢复诚信状态"),
        operator_id=current.user_id, operator_name=operator.nickname or "系统管理员"))
    db.commit(); return result()


@router.get("/user/{user_id}/credit-records")
def credit_records(user_id: int, db: Session = Depends(get_db)):
    return result(list(db.scalars(select(CreditRecord).where(CreditRecord.user_id == user_id)
                                  .order_by(CreditRecord.created_time.desc())).all()))


@router.put("/user/{user_id}/reset-password")
def reset_password(user_id: int, db: Session = Depends(get_db)):
    get_user(db, user_id).password = encode_password("123456"); db.commit(); return result()


@router.get("/drone/list")
def drones(page: int = 1, pageSize: int = 10, keyword: str | None = None, type: str | None = None,
           status: int | None = None, onShelf: int | None = None, db: Session = Depends(get_db),
           settings: Settings = Depends(get_settings)):
    stmt = select(Drone).where(Drone.deleted == 0)
    if keyword: stmt = stmt.where(or_(Drone.model.contains(keyword), Drone.brand.contains(keyword)))
    if type: stmt = stmt.where(Drone.type == type)
    if status is not None: stmt = stmt.where(Drone.status == status)
    if onShelf is not None: stmt = stmt.where(Drone.on_shelf == onShelf)
    paged = paginate(db, stmt.order_by(Drone.created_time.desc()), page, pageSize)
    storage = get_storage(settings)
    records = []
    for item in paged["records"]:
        data = serialize(item)
        sign_payload_field(data, "image", "imageKey", storage)
        records.append(data)
    paged["records"] = records
    return result(paged)


@router.get("/drone/{item_id}")
def drone_detail(item_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    data = serialize(get_drone(db, item_id))
    sign_payload_field(data, "image", "imageKey", get_storage(settings))
    return result(data)


@router.post("/drone/add")
def drone_add(dto: DroneDTO, db: Session = Depends(get_db), current: CurrentUser = Depends(require_admin)):
    add_drone(db, dto, current.user_id)
    return result()


@router.put("/drone/{item_id}")
def drone_update(item_id: int, dto: DroneDTO, db: Session = Depends(get_db), current: CurrentUser = Depends(require_admin)):
    drone = get_drone(db, item_id); before = drone.stock
    if dto.image != drone.image:
        validate_drone_keys(dto.image)
    for key, value in dto.model_dump().items(): setattr(drone, key, value)
    if dto.stock != before: stock_log(db, item_id, C.STOCK_IN if dto.stock > before else C.STOCK_RENT,
        dto.stock - before, before, dto.stock, None, "管理员调整库存", current.user_id)
    db.commit()
    invalidate_drone_cache()
    return result()


@router.delete("/drone/{item_id}")
def drone_delete(item_id: int, db: Session = Depends(get_db)):
    get_drone(db, item_id).deleted = 1
    db.commit()
    invalidate_drone_cache()
    return result()


@router.put("/drone/{item_id}/shelf")
def drone_shelf(item_id: int, onShelf: int, db: Session = Depends(get_db)):
    get_drone(db, item_id).on_shelf = onShelf
    db.commit()
    invalidate_drone_cache()
    return result()


@router.put("/drone/{item_id}/status")
def drone_status(item_id: int, status: int, db: Session = Depends(get_db)):
    get_drone(db, item_id).status = status
    db.commit()
    invalidate_drone_cache()
    return result()


@router.put("/drone/{item_id}/stock")
def drone_stock(item_id: int, body: dict[str, int], db: Session = Depends(get_db),
                current: CurrentUser = Depends(require_admin)):
    stock = body.get("stock")
    if stock is None:
        raise BusinessException(ResultCode.PARAM_ERROR)
    drone = get_drone(db, item_id); before = drone.stock; drone.stock = stock
    if stock == 0 and drone.status == C.DRONE_AVAILABLE: drone.status = C.DRONE_OUT_OF_STOCK
    if stock > 0 and drone.status == C.DRONE_OUT_OF_STOCK: drone.status = C.DRONE_AVAILABLE
    if stock != before: stock_log(db, item_id, C.STOCK_IN if stock > before else C.STOCK_RENT,
                                  stock - before, before, stock, None, "管理员调整库存", current.user_id)
    db.commit()
    invalidate_drone_cache()
    return result()


@router.get("/airspace/list")
def airspace_list(pageNum: int = 1, pageSize: int = 10, auditStatus: int | None = None,
                  regionName: str | None = None, db: Session = Depends(get_db)):
    stmt = select(AirspaceRecord).where(AirspaceRecord.deleted == 0)
    if auditStatus is not None: stmt = stmt.where(AirspaceRecord.audit_status == auditStatus)
    if regionName: stmt = stmt.where(AirspaceRecord.region_name.contains(regionName))
    return result(paginate(db, stmt.order_by(AirspaceRecord.created_time.desc()), pageNum, pageSize))


@router.put("/airspace/{item_id}/audit")
def airspace_audit(item_id: int, dto: AuditDTO, db: Session = Depends(get_db), current: CurrentUser = Depends(require_admin)):
    item = db.scalar(select(AirspaceRecord).where(AirspaceRecord.id == item_id, AirspaceRecord.deleted == 0))
    if item is None: raise BusinessException(ResultCode.AIRSPACE_NOT_EXIST)
    if item.audit_status != C.AUDIT_PENDING: raise BusinessException(message="该备案已审核，不能重复审核")
    item.audit_status = dto.audit_status; item.audit_remark = dto.audit_remark; item.audit_time = datetime.now()
    item.auditor_id = current.user_id; db.commit(); return result()


@router.get("/airspace/{item_id}")
def airspace_detail(item_id: int, db: Session = Depends(get_db)):
    return result(db.scalar(select(AirspaceRecord).where(AirspaceRecord.id == item_id, AirspaceRecord.deleted == 0)))


@router.get("/order/list")
def orders(page: int = 1, pageSize: int = 10, orderNo: str | None = None, userPhone: str | None = None,
           orderStatus: int | None = None, startDate: str | None = None, endDate: str | None = None,
           db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    stmt = select(RentalOrder).where(RentalOrder.deleted == 0)
    if orderNo: stmt = stmt.where(RentalOrder.order_no.contains(orderNo))
    if orderStatus is not None: stmt = stmt.where(RentalOrder.order_status == orderStatus)
    if userPhone:
        ids = select(User.id).where(User.phone.contains(userPhone), User.deleted == 0); stmt = stmt.where(RentalOrder.user_id.in_(ids))
    if startDate: stmt = stmt.where(RentalOrder.created_time >= datetime.fromisoformat(startDate + " 00:00:00"))
    if endDate: stmt = stmt.where(RentalOrder.created_time <= datetime.fromisoformat(endDate + " 23:59:59"))
    paged = paginate(db, stmt.order_by(RentalOrder.created_time.desc()), page, pageSize)
    storage = get_storage(settings)
    paged["records"] = [order_vo(db, item, storage) for item in paged["records"]]; return result(paged)


@router.get("/order/{order_id}")
def admin_order_detail(order_id: int, db: Session = Depends(get_db),
                       settings: Settings = Depends(get_settings)):
    return result(order_vo(db, get_order(db, order_id), get_storage(settings)))


@router.get("/order/{order_id}/return-logs")
def admin_return_logs(order_id: int, db: Session = Depends(get_db)):
    get_order(db, order_id)
    return result(list(db.scalars(select(OrderReturnLog).where(
        OrderReturnLog.order_id == order_id
    ).order_by(OrderReturnLog.created_time.asc())).all()))


@router.post("/order/{order_id}/return")
def admin_return(order_id: int, dto: DepositSettlementDTO, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_admin), settings: Settings = Depends(get_settings)):
    return result(settle_deposit(db, order_id, dto, current, settings))


@router.post("/order/{order_id}/refund")
def admin_refund(order_id: int, dto: RefundDTO, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_admin), settings: Settings = Depends(get_settings)):
    if dto.mode == "deposit":
        return result(settle_deposit(db, order_id, DepositSettlementDTO(), current, settings))
    return result(refund_order_full(db, order_id, dto.reason or "", current, settings))


@router.post("/order/{order_id}/ship")
def admin_ship(order_id: int, expressCompany: str, expressNo: str, db: Session = Depends(get_db), current: CurrentUser = Depends(require_admin)):
    change_state(db, order_id, "ship", current, express_company=expressCompany, express_no=expressNo); return result()


@router.get("/maintenance/fault/list")
def fault_list(pageNum: int = 1, pageSize: int = 10, auditStatus: int | None = None,
               db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    stmt = select(FaultReport).where(FaultReport.deleted == 0)
    if auditStatus is not None: stmt = stmt.where(FaultReport.audit_status == auditStatus)
    paged = paginate(db, stmt.order_by(FaultReport.created_time.desc()), pageNum, pageSize)
    storage = get_storage(settings)
    paged["records"] = [fault_vo(db, item, storage) for item in paged["records"]]; return result(paged)


@router.get("/maintenance/fault/{item_id}")
def fault_detail(item_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    item = db.scalar(select(FaultReport).where(FaultReport.id == item_id, FaultReport.deleted == 0))
    if item is None: raise BusinessException(ResultCode.FAULT_NOT_EXIST)
    return result(fault_vo(db, item, get_storage(settings)))


@router.get("/maintenance/fault/{item_id}/image-urls")
def fault_image_urls(item_id: int, db: Session = Depends(get_db),
                     settings: Settings = Depends(get_settings)):
    item = db.scalar(select(FaultReport).where(FaultReport.id == item_id, FaultReport.deleted == 0))
    if item is None: raise BusinessException(ResultCode.FAULT_NOT_EXIST)
    return result(signed_file_data(get_storage(settings), item.fault_images, settings))


@router.put("/maintenance/fault/{item_id}/audit")
def fault_audit(item_id: int, dto: AuditDTO, db: Session = Depends(get_db), current: CurrentUser = Depends(require_admin)):
    item = db.scalar(select(FaultReport).where(FaultReport.id == item_id, FaultReport.deleted == 0))
    if item is None: raise BusinessException(ResultCode.FAULT_NOT_EXIST)
    audit_fault(db, item, dto.audit_status, dto.audit_remark, current.user_id); return result()


@router.get("/maintenance/ticket/list")
def ticket_list(page: int = 1, pageSize: int = 10, status: int | None = None, droneId: int | None = None,
                droneModel: str | None = None, type: str | None = None, db: Session = Depends(get_db)):
    stmt = select(MaintenanceTicket).where(MaintenanceTicket.deleted == 0)
    if status is not None: stmt = stmt.where(MaintenanceTicket.status == status)
    if droneId is not None: stmt = stmt.where(MaintenanceTicket.drone_id == droneId)
    if droneModel: stmt = stmt.where(MaintenanceTicket.drone_id.in_(select(Drone.id).where(Drone.model.contains(droneModel))))
    if type: stmt = stmt.where(MaintenanceTicket.maintenance_type == type)
    paged = paginate(db, stmt.order_by(MaintenanceTicket.created_time.desc()), page, pageSize)
    paged["records"] = [ticket_vo(db, item) for item in paged["records"]]; return result(paged)


def get_ticket(db: Session, item_id: int) -> MaintenanceTicket:
    item = db.scalar(select(MaintenanceTicket).where(MaintenanceTicket.id == item_id, MaintenanceTicket.deleted == 0))
    if item is None: raise BusinessException(ResultCode.MAINTENANCE_NOT_EXIST)
    return item


@router.get("/maintenance/ticket/{item_id}")
def ticket_detail(item_id: int, db: Session = Depends(get_db)): return result(ticket_vo(db, get_ticket(db, item_id)))


@router.put("/maintenance/ticket/{item_id}")
def ticket_update(item_id: int, dto: MaintenanceTicketDTO, db: Session = Depends(get_db)):
    update_ticket(db, get_ticket(db, item_id), dto); return result()


@router.post("/maintenance/ticket/{item_id}/start")
def ticket_start(item_id: int, db: Session = Depends(get_db)):
    start_ticket(db, get_ticket(db, item_id)); return result()


@router.post("/maintenance/ticket/{item_id}/complete")
def ticket_complete(item_id: int, dto: MaintenanceTicketDTO | None = None, db: Session = Depends(get_db)):
    complete_ticket(db, get_ticket(db, item_id), dto); return result()


@router.get("/comment/list")
def comments(page: int = 1, pageSize: int = 10, droneId: int | None = None, status: int | None = None,
             userName: str | None = None, droneModel: str | None = None, rating: int | None = None,
             hasReply: bool | None = None, db: Session = Depends(get_db),
             settings: Settings = Depends(get_settings)):
    stmt = select(Comment).where(Comment.deleted == 0)
    if droneId is not None: stmt = stmt.where(Comment.drone_id == droneId)
    if status is not None: stmt = stmt.where(Comment.status == status)
    if userName: stmt = stmt.where(Comment.user_id.in_(select(User.id).where(User.nickname.contains(userName))))
    if droneModel: stmt = stmt.where(Comment.drone_id.in_(select(Drone.id).where(Drone.model.contains(droneModel))))
    if rating is not None: stmt = stmt.where(Comment.rating <= 2 if rating == 2 else Comment.rating == rating)
    if hasReply is not None: stmt = stmt.where(Comment.reply_content.is_not(None) if hasReply else Comment.reply_content.is_(None))
    paged = paginate(db, stmt.order_by(Comment.created_time.desc()), page, pageSize)
    storage = get_storage(settings)
    paged["records"] = [comment_vo(db, item, storage) for item in paged["records"]]; return result(paged)


@router.put("/comment/{item_id}/status")
def comment_status(item_id: int, status: int, db: Session = Depends(get_db)):
    item = db.scalar(select(Comment).where(Comment.id == item_id, Comment.deleted == 0))
    if item is None: raise BusinessException(ResultCode.COMMENT_NOT_EXIST)
    item.status = status; db.commit(); return result()


@router.post("/comment/{item_id}/reply")
def comment_reply(item_id: int, body: dict[str, str], db: Session = Depends(get_db)):
    item = db.scalar(select(Comment).where(Comment.id == item_id, Comment.deleted == 0))
    if item is None: raise BusinessException(ResultCode.COMMENT_NOT_EXIST)
    reply_content = body.get("replyContent")
    if reply_content is None or not reply_content.strip():
        raise BusinessException(ResultCode.PARAM_MISSING, "replyContent")
    item.reply_content = reply_content; item.reply_time = datetime.now(); db.commit(); return result()


@router.delete("/comment/{item_id}")
def comment_delete(item_id: int, db: Session = Depends(get_db)):
    item = db.scalar(select(Comment).where(Comment.id == item_id, Comment.deleted == 0))
    if item: item.deleted = 1; db.commit()
    return result()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    return datetime.combine(day, time.min), datetime.combine(day, time.max)


def revenue(db: Session, start: datetime, end: datetime) -> Decimal:
    return db.scalar(select(func.coalesce(func.sum(RentalOrder.total_amount), 0)).where(
        RentalOrder.created_time.between(start, end), RentalOrder.order_status.in_([1, 2, 3, 5]),
        RentalOrder.deleted == 0)) or Decimal("0")


@router.get("/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db)):
    today, yesterday = date.today(), date.today() - timedelta(days=1)
    today_start, today_end = day_bounds(today); yesterday_start, yesterday_end = day_bounds(yesterday)
    today_orders = list(db.scalars(select(RentalOrder).where(RentalOrder.created_time.between(today_start, today_end),
        RentalOrder.order_status.in_([1, 2, 3, 5]), RentalOrder.deleted == 0)).all())
    yesterday_orders = list(db.scalars(select(RentalOrder).where(RentalOrder.created_time.between(yesterday_start, yesterday_end),
        RentalOrder.order_status.in_([1, 2, 3, 5]), RentalOrder.deleted == 0)).all())
    tr, yr = sum((x.total_amount for x in today_orders), Decimal(0)), sum((x.total_amount for x in yesterday_orders), Decimal(0))
    revenue_trend = int(((tr - yr) * 100 / yr).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if yr > 0 else (100 if tr > 0 else 0)
    order_trend = int((len(today_orders) - len(yesterday_orders)) * 100 / len(yesterday_orders)) if yesterday_orders else (100 if today_orders else 0)
    return result({"todayRevenue": tr, "todayOrders": len(today_orders), "revenueTrend": revenue_trend,
        "orderTrend": order_trend, "totalUsers": db.scalar(select(func.count()).select_from(User).where(User.role == 0, User.deleted == 0)),
        "totalDrones": db.scalar(select(func.count()).select_from(Drone).where(Drone.deleted == 0))})


@router.get("/dashboard/revenue-trend")
def revenue_trend(period: str = "week", db: Session = Depends(get_db)):
    dates, values, today = [], [], date.today()
    if period == "year":
        for month in range(1, 13):
            start = date(today.year, month, 1); end = date(today.year, month, monthrange(today.year, month)[1])
            dates.append(f"{month}月")
            values.append(revenue(db, datetime.combine(start, time.min), datetime.combine(end, time.max)))
    else:
        for offset in range((7 if period == "week" else 30) - 1, -1, -1):
            day = today - timedelta(days=offset); dates.append(day.strftime("%m-%d")); values.append(revenue(db, *day_bounds(day)))
    return result({"dates": dates, "values": values})


@router.get("/dashboard/order-trend")
def order_trend(period: str = "week", db: Session = Depends(get_db)):
    dates, values, today = [], [], date.today()
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset); dates.append(day.strftime("%m-%d"))
        values.append(db.scalar(select(func.count()).select_from(RentalOrder).where(RentalOrder.created_time.between(*day_bounds(day)), RentalOrder.deleted == 0)) or 0)
    return result({"dates": dates, "values": values})


@router.get("/dashboard/popular-drones")
def popular_drones(limit: int = 5, db: Session = Depends(get_db)):
    drones = list(db.scalars(select(Drone).where(Drone.deleted == 0, Drone.on_shelf == 1).limit(limit)).all())
    data = [{"id": x.id, "model": x.model, "brand": x.brand,
             "rentCount": db.scalar(select(func.count()).select_from(RentalOrder).where(RentalOrder.drone_id == x.id)) or 0} for x in drones]
    return result(sorted(data, key=lambda x: x["rentCount"], reverse=True))


@router.get("/dashboard/recent-orders")
def recent_orders(limit: int = 5, db: Session = Depends(get_db)):
    orders = db.scalars(select(RentalOrder).where(RentalOrder.deleted == 0).order_by(RentalOrder.created_time.desc()).limit(limit)).all()
    return result([{"id": x.id, "orderNo": x.order_no, "status": x.order_status, "totalAmount": x.total_amount,
                    "userName": (db.get(User, x.user_id).nickname if db.get(User, x.user_id) else "未知")} for x in orders])


@router.get("/dashboard/todos")
def todos(db: Session = Depends(get_db)):
    count = lambda model, *where: db.scalar(select(func.count()).select_from(model).where(*where)) or 0
    return result({"audit": count(UserQualification, UserQualification.audit_status == 0, UserQualification.deleted == 0),
        "ship": count(RentalOrder, RentalOrder.order_status == 1, RentalOrder.deleted == 0),
        "return": count(RentalOrder, RentalOrder.order_status.in_([
            C.ORDER_RETURN_REQUESTED, C.ORDER_RETURN_SHIPPED
        ]), RentalOrder.deleted == 0),
        "returnRequested": count(RentalOrder, RentalOrder.order_status == C.ORDER_RETURN_REQUESTED, RentalOrder.deleted == 0),
        "returnShipped": count(RentalOrder, RentalOrder.order_status == C.ORDER_RETURN_SHIPPED, RentalOrder.deleted == 0),
        "maintenance": count(FaultReport, FaultReport.audit_status == 0, FaultReport.deleted == 0)})
