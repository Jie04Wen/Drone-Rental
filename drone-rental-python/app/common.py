from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import IntEnum
from typing import Any

from sqlalchemy.inspection import inspect


class ResultCode(IntEnum):
    SUCCESS = 200
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    ERROR = 500
    SERVICE_UNAVAILABLE = 503
    USER_NOT_EXIST = 1001
    USER_PASSWORD_ERROR = 1002
    USER_DISABLED = 1003
    USER_ALREADY_EXISTS = 1004
    USER_CREDIT_BAD = 1005
    QUALIFICATION_NOT_EXIST = 1101
    QUALIFICATION_NOT_APPROVED = 1102
    QUALIFICATION_EXPIRED = 1103
    DRONE_NOT_EXIST = 1201
    DRONE_NOT_AVAILABLE = 1202
    DRONE_STOCK_NOT_ENOUGH = 1203
    DRONE_IN_MAINTENANCE = 1204
    DRONE_OFF_SHELF = 1205
    ORDER_NOT_EXIST = 1301
    ORDER_ALREADY_PAID = 1302
    ORDER_ALREADY_CANCELLED = 1303
    ORDER_CANNOT_CANCEL = 1304
    ORDER_CREATE_FAILED = 1305
    PAYMENT_NOT_EXIST = 1401
    PAYMENT_ALREADY_DONE = 1402
    PAYMENT_FAILED = 1403
    REFUND_FAILED = 1404
    AIRSPACE_NOT_EXIST = 1501
    AIRSPACE_NOT_APPROVED = 1502
    AIRSPACE_REQUIRED = 1503
    FAULT_NOT_EXIST = 1601
    FAULT_ALREADY_PROCESSED = 1602
    MAINTENANCE_NOT_EXIST = 1701
    MAINTENANCE_ALREADY_COMPLETED = 1702
    COMMENT_NOT_EXIST = 1801
    COMMENT_BLOCKED = 1802
    PARAM_ERROR = 1901
    PARAM_MISSING = 1902


MESSAGES = {
    ResultCode.SUCCESS: "操作成功", ResultCode.BAD_REQUEST: "请求参数错误",
    ResultCode.UNAUTHORIZED: "未登录或登录已过期", ResultCode.FORBIDDEN: "没有操作权限",
    ResultCode.NOT_FOUND: "资源不存在", ResultCode.METHOD_NOT_ALLOWED: "请求方法不允许",
    ResultCode.ERROR: "服务器内部错误", ResultCode.SERVICE_UNAVAILABLE: "服务不可用",
    ResultCode.USER_NOT_EXIST: "用户不存在", ResultCode.USER_PASSWORD_ERROR: "用户名或密码错误",
    ResultCode.USER_DISABLED: "用户已被禁用", ResultCode.USER_ALREADY_EXISTS: "用户名已存在",
    ResultCode.USER_CREDIT_BAD: "用户诚信状态不良，禁止操作",
    ResultCode.QUALIFICATION_NOT_EXIST: "飞行资质不存在", ResultCode.QUALIFICATION_NOT_APPROVED: "飞行资质未通过审核",
    ResultCode.QUALIFICATION_EXPIRED: "飞行资质已过期", ResultCode.DRONE_NOT_EXIST: "无人机不存在",
    ResultCode.DRONE_NOT_AVAILABLE: "无人机不可租赁", ResultCode.DRONE_STOCK_NOT_ENOUGH: "无人机库存不足",
    ResultCode.DRONE_IN_MAINTENANCE: "无人机正在维修中", ResultCode.DRONE_OFF_SHELF: "无人机已下架",
    ResultCode.ORDER_NOT_EXIST: "订单不存在", ResultCode.ORDER_ALREADY_PAID: "订单已支付",
    ResultCode.ORDER_ALREADY_CANCELLED: "订单已取消", ResultCode.ORDER_CANNOT_CANCEL: "订单状态不允许取消",
    ResultCode.ORDER_CREATE_FAILED: "订单创建失败", ResultCode.PAYMENT_NOT_EXIST: "支付记录不存在",
    ResultCode.PAYMENT_ALREADY_DONE: "已完成支付", ResultCode.PAYMENT_FAILED: "支付失败",
    ResultCode.REFUND_FAILED: "退款失败", ResultCode.AIRSPACE_NOT_EXIST: "空域备案不存在",
    ResultCode.AIRSPACE_NOT_APPROVED: "空域备案未通过审核", ResultCode.AIRSPACE_REQUIRED: "下单必须绑定空域备案",
    ResultCode.FAULT_NOT_EXIST: "故障记录不存在", ResultCode.FAULT_ALREADY_PROCESSED: "故障已处理",
    ResultCode.MAINTENANCE_NOT_EXIST: "维修工单不存在", ResultCode.MAINTENANCE_ALREADY_COMPLETED: "维修工单已完成",
    ResultCode.COMMENT_NOT_EXIST: "评论不存在", ResultCode.COMMENT_BLOCKED: "评论已被屏蔽",
    ResultCode.PARAM_ERROR: "参数校验失败", ResultCode.PARAM_MISSING: "缺少必要参数",
}


@dataclass
class BusinessException(Exception):
    code: int
    message: str

    def __init__(self, code: ResultCode | int = ResultCode.ERROR, message: str | None = None):
        self.code = int(code)
        self.message = message or MESSAGES.get(ResultCode(code), "服务器内部错误")
        super().__init__(self.message)


def camel(name: str) -> str:
    return re.sub(r"_([a-z])", lambda match: match.group(1).upper(), name)


def serialize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {camel(str(k)): serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    if hasattr(value, "__table__"):
        return {camel(column.key): serialize(getattr(value, column.key)) for column in inspect(value).mapper.column_attrs}
    return value


def result(data: Any = None, message: str = "操作成功", code: int = 200) -> dict[str, Any]:
    return {"code": code, "message": message, "data": serialize(data), "timestamp": int(time.time() * 1000)}


def page_result(records: list[Any], total: int, page: int, page_size: int) -> dict[str, Any]:
    pages = (total + page_size - 1) // page_size if page_size else 0
    return {"records": records, "total": total, "size": page_size, "current": page, "pages": pages}


class C:
    ROLE_USER = 0; ROLE_ADMIN = 1
    USER_STATUS_DISABLED = 0; USER_STATUS_NORMAL = 1
    CREDIT_STATUS_BAD = 0; CREDIT_STATUS_NORMAL = 1
    AUDIT_PENDING = 0; AUDIT_APPROVED = 1; AUDIT_REJECTED = 2
    DRONE_OUT_OF_STOCK = 0; DRONE_AVAILABLE = 1; DRONE_MAINTENANCE = 2
    OFF_SHELF = 0; ON_SHELF = 1
    STOCK_IN = 1; STOCK_RENT = 2; STOCK_RETURN = 3; STOCK_MAINTENANCE = 4; STOCK_MAINTENANCE_RETURN = 5
    ORDER_UNPAID = 0; ORDER_PAID = 1; ORDER_SHIPPED = 2; ORDER_RENTING = 3
    ORDER_RETURNED = 4; ORDER_CANCELLED = 5; ORDER_REFUNDED = 6
    ORDER_RETURN_REQUESTED = 7; ORDER_RETURN_SHIPPED = 8
    PAYMENT_ORDER = 1; PAYMENT_DEPOSIT = 2; PAYMENT_MAINTENANCE = 3
    PAYMENT_UNPAID = 0; PAYMENT_PAID = 1; PAYMENT_REFUNDED = 2; PAYMENT_PARTIALLY_REFUNDED = 3
    DEPOSIT_PENDING = 0; DEPOSIT_REFUNDED = 1; DEPOSIT_PARTIALLY_DEDUCTED = 2; DEPOSIT_FULLY_DEDUCTED = 3
    FAULT_PENDING = 0; FAULT_CONFIRMED = 1; FAULT_NOT_FAULT = 2
    MAINTENANCE_PENDING = 0; MAINTENANCE_IN_PROGRESS = 1; MAINTENANCE_COMPLETED = 2; MAINTENANCE_CANCELLED = 3
    COMMENT_BLOCKED = 0; COMMENT_NORMAL = 1
