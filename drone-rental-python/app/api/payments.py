from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..alipay import AlipayClient
from ..config import Settings, get_settings
from ..database import get_db
from ..models import Payment, RentalOrder
from ..security import CurrentUser, get_current_user
from ..services.orders import (confirm_paid_callback, ensure_payment_open,
                               get_order_for_update, payment_amount,
                               payment_deadline)

import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payment")

@router.post("/alipay/notify", response_class=PlainTextResponse)
async def alipay_notify(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    form = await request.form()
    params = {key: str(value) for key, value in form.multi_items()}
    order_no = params.get("out_trade_no")
    trade_status = params.get("trade_status")

    logger.info(
        "收到支付宝通知：order_no=%s trade_status=%s",
        order_no,
        trade_status,
    )

    # 异步通知校验
    client = AlipayClient(settings)
    if not client.verify_notify(params):
        logger.warning("支付宝通知验签失败：order_no=%s", order_no)
        return "failure"

    if params.get("app_id") != settings.alipay_app_id:
        logger.warning("支付宝通知 app_id 不匹配：order_no=%s", order_no)
        return "failure"

    if params.get("trade_status") in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
        order = db.scalar(
            select(RentalOrder).where(RentalOrder.order_no == params.get("out_trade_no")).limit(1)
        )
        if order is None:
            logger.warning("支付宝通知对应的本地订单不存在：order_no=%s", order_no)
            return "failure"
        try:
            notified_amount = Decimal(params.get("total_amount", ""))
        except (InvalidOperation, ValueError, TypeError):
            return "failure"

        payment = db.scalar(select(Payment).where(Payment.order_id == order.id, Payment.deleted == 0).limit(1))
        expected_amount = payment.amount if payment else payment_amount(order)
        if notified_amount != expected_amount:
            logger.warning(
                "支付宝通知金额不匹配：order_no=%s local=%s notified=%s",
                order_no,
                expected_amount,
                notified_amount,
            )
            return "failure"

        try:
            confirm_paid_callback(db, order.id, "alipay")
        except Exception:
            db.rollback()
            logger.exception("支付宝通知落库失败：order_no=%s", order_no)
            return "failure"
    return "success"


@router.get("/alipay/return", response_class=PlainTextResponse)
def alipay_return(out_trade_no: str | None = None):
    return f"redirect:/orders?paid=1&orderNo={out_trade_no}" if out_trade_no else "redirect:/orders"


@router.post("/alipay/create")
def alipay_create(
    body: dict[str, str],
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    order = db.scalar(select(RentalOrder).where(
        RentalOrder.order_no == body.get("orderNo"), RentalOrder.deleted == 0
    ).limit(1))
    if order is None:
        return {"status": "error", "message": "订单不存在"}
    order = get_order_for_update(db, order.id)
    if order.user_id != current.user_id:
        return {"status": "error", "message": "无权操作该订单"}
    if order.order_status != 0:
        return {"status": "error", "message": "订单状态不允许支付"}
    ensure_payment_open(db, order)
    try:
        requested_amount = Decimal(body.get("totalAmount", ""))
    except (InvalidOperation, ValueError, TypeError):
        return {"status": "error", "message": "支付金额格式错误"}
    if requested_amount != payment_amount(order):
        return {"status": "error", "message": "支付金额与订单金额不一致"}
    form = AlipayClient(settings).create_page_pay(
        order.order_no,
        body.get("subject", "无人机租赁"),
        format(payment_amount(order), "f"),
        body.get("returnUrl"),
        payment_deadline(order),
    )
    if form is None:
        return {"status": "error", "message": "支付宝未配置或创建失败"}
    return {"status": "ok", "form": form}


@router.get("/alipay/query")
def alipay_query(orderNo: str, settings: Settings = Depends(get_settings)):
    data = AlipayClient(settings).query_trade(orderNo)
    if not data:
        return {"status": "error", "message": "查询失败或未配置支付宝"}
    return {"status": "ok", "data": data}
