"""Read-only AI tools """

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.orm import Session

from ..common import serialize
from ..models import AirspaceRecord, Drone, RentalOrder, UserQualification

LOGGER = logging.getLogger(__name__)

BRAND_ALIAS_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"dji", "大疆", "dji大疆"}),
    frozenset({"autel", "道通", "autel道通"}),
    frozenset({"xag", "极飞", "xag极飞"}),
    frozenset({"parrot", "派诺特", "parrot派诺特"}),
)

ORDER_STATUS_NAMES = {
    0: "待支付",
    1: "待发货",
    2: "待收货",
    3: "租赁中",
    4: "已归还",
    5: "已取消",
    6: "已退款",
    7: "待归还/待寄回",
    8: "待商家收货",
}


def json_text(value: Any) -> str:
    return json.dumps(serialize(value), ensure_ascii=False, separators=(",", ":"))


def normalize_search_text(value: str) -> str:
    """Normalize user-entered search text for case/spacing-insensitive matching."""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def brand_search_terms(value: str) -> set[str]:
    """Expand a brand query to common Chinese/English aliases."""
    normalized = normalize_search_text(value)
    if not normalized:
        return set()
    for aliases in BRAND_ALIAS_GROUPS:
        if any(alias in normalized or normalized in alias for alias in aliases):
            return set(aliases)
    return {normalized}


def normalized_column(column: ColumnElement[Any]) -> ColumnElement[Any]:
    """Build a portable SQL expression matching normalize_search_text's separators."""
    expression = func.lower(func.coalesce(column, ""))
    for separator in (" ", "-", "_", "/", ".", "·", "(", ")", "（", "）"):
        expression = func.replace(expression, separator, "")
    return expression


def fuzzy_contains(column: ColumnElement[Any], terms: set[str]) -> ColumnElement[bool]:
    """Return a normalized partial-match expression for one or more aliases."""
    if not terms:
        raise ValueError("搜索条件至少需要包含一个字母、数字或汉字")
    expression = normalized_column(column)
    return or_(*(expression.contains(term) for term in sorted(terms)))


def optional_text(params: dict[str, Any], key: str) -> str | None:
    value = params.get(key)
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def decimal_parameter(params: dict[str, Any], key: str) -> Decimal | None:
    value = params.get(key)
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{key} 必须是有效数字") from exc
    if not number.is_finite():
        raise ValueError(f"{key} 必须是有限数字")
    return number


def normalize_model_name(value: str) -> str:
    """Normalize model names and canonicalize common Chinese/English brand aliases."""
    normalized = normalize_search_text(value)
    for aliases in BRAND_ALIAS_GROUPS:
        canonical = sorted(aliases, key=lambda item: (not item.isascii(), len(item)))[0]
        for alias in sorted(aliases, key=len, reverse=True):
            normalized = normalized.replace(alias, canonical)
    return normalized


def resolve_drone_by_model(db: Session, model_query: str) -> tuple[Drone | None, str]:
    """Resolve a model without guessing when a short query matches several products."""
    query = normalize_model_name(model_query)
    if not query:
        return None, "none"
    candidates = list(db.scalars(select(Drone).where(Drone.deleted == 0)).all())
    exact_matches: list[Drone] = []
    models_in_query: list[tuple[int, Drone]] = []
    query_in_models: list[Drone] = []
    fuzzy_matches: list[tuple[float, Drone]] = []
    for drone in candidates:
        model = normalize_model_name(drone.model or "")
        if not model:
            continue
        if model == query:
            exact_matches.append(drone)
        elif model in query:
            models_in_query.append((len(model), drone))
        elif query in model:
            query_in_models.append(drone)
        else:
            fuzzy_matches.append((SequenceMatcher(None, query, model).ratio(), drone))
    if len(exact_matches) == 1:
        return exact_matches[0], "exact_model"
    if len(exact_matches) > 1:
        return None, "ambiguous_model"
    if models_in_query:
        models_in_query.sort(key=lambda item: item[0], reverse=True)
        if len(models_in_query) == 1 or models_in_query[0][0] > models_in_query[1][0]:
            return models_in_query[0][1], "model_in_query"
        return None, "ambiguous_model"
    if len(query_in_models) == 1:
        return query_in_models[0], "query_in_model"
    if len(query_in_models) > 1:
        return None, "ambiguous_model"
    if not fuzzy_matches:
        return None, "none"
    fuzzy_matches.sort(key=lambda item: item[0], reverse=True)
    score, drone = fuzzy_matches[0]
    if score < 0.72:
        return None, "none"
    if len(fuzzy_matches) > 1 and score - fuzzy_matches[1][0] < 0.08:
        return None, "ambiguous_model"
    return drone, "fuzzy_model"


class AiTool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]

    def definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}

    @abstractmethod
    def execute(self, db: Session, params: dict[str, Any], user_id: int) -> str: ...


class DroneQueryTool(AiTool):
    name = "query_drones"
    description = (
        "查询数据库中当前已上架、设备状态正常且库存大于0的可租赁无人机。"
        "当用户询问品牌、型号、类型、库存或日租金时使用；品牌和关键词支持中英文别名、"
        "大小写、空格及部分文本匹配，例如 DJI、大疆、DJI大疆视为同一品牌。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "minLength": 1,
                "description": "型号、品牌、类型或描述关键词，支持模糊匹配",
            },
            "brand": {
                "type": "string",
                "minLength": 1,
                "description": "品牌关键词，支持中英文别名和部分匹配，如 DJI 或大疆",
            },
            "drone_type": {
                "type": "string",
                "minLength": 1,
                "description": "用途/类型关键词，如航拍、测绘、农业，支持部分匹配",
            },
            "maxPrice": {
                "type": "number",
                "minimum": 0,
                "description": "可接受的最高日租金，单位为人民币元",
            },
        },
        "additionalProperties": False,
    }

    def execute(self, db: Session, params: dict[str, Any], user_id: int) -> str:
        try:
            conditions = [
                Drone.on_shelf == 1,
                Drone.status == 1,
                Drone.stock > 0,
                Drone.deleted == 0,
            ]
            applied_filters: dict[str, Any] = {}
            keyword = optional_text(params, "keyword")
            if keyword:
                terms = brand_search_terms(keyword)
                conditions.append(
                    or_(
                        fuzzy_contains(Drone.model, terms),
                        fuzzy_contains(Drone.brand, terms),
                        fuzzy_contains(Drone.type, terms),
                        fuzzy_contains(Drone.description, terms),
                    )
                )
                applied_filters["keyword"] = keyword
            brand = optional_text(params, "brand")
            if brand:
                conditions.append(fuzzy_contains(Drone.brand, brand_search_terms(brand)))
                applied_filters["brand"] = brand
            drone_type = optional_text(params, "drone_type")
            if drone_type:
                type_term = normalize_search_text(drone_type)
                conditions.append(
                    fuzzy_contains(Drone.type, {type_term} if type_term else set())
                )
                applied_filters["droneType"] = drone_type
            max_price = decimal_parameter(params, "maxPrice")
            if max_price is not None:
                if max_price < 0:
                    return json_text({"error": "最高日租金 maxPrice 不能小于0"})
                conditions.append(Drone.price_per_day <= max_price)
                applied_filters["maxPrice"] = max_price
            total = db.scalar(select(func.count()).select_from(Drone).where(*conditions)) or 0
            drones = db.scalars(
                select(Drone)
                .where(*conditions)
                .order_by(Drone.price_per_day.asc(), Drone.created_time.desc(), Drone.id.desc())
                .limit(5)
            ).all()
            return json_text(
                {
                    "filters": applied_filters,
                    "totalAvailable": total,
                    "displayedCount": len(drones),
                    "displayLimit": 5,
                    "isTruncated": total > len(drones),
                    "items": [
                        {
                            "id": item.id,
                            "model": (item.model or "").strip(),
                            "brand": (item.brand or "").strip(),
                            "type": (item.type or "").strip(),
                            "pricePerDay": item.price_per_day,
                            "stock": item.stock,
                            "available": item.stock > 0,
                        }
                        for item in drones
                    ],
                }
            )
        except ValueError as exc:
            return json_text({"error": str(exc)})
        except Exception:
            LOGGER.exception("query_drones failed")
            return '{"error":"无人机查询失败，请稍后重试"}'


class OrderQueryTool(AiTool):
    name = "query_orders"
    description = (
        "查询当前登录用户最近的无人机租赁订单及其状态。"
        "用户询问‘我的订单’、待支付、租赁中、待归还等个人订单信息时使用；"
        "不得用于查询其他用户。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "status": {
                "type": "integer",
                "enum": list(ORDER_STATUS_NAMES),
                "description": "订单状态筛选: 0-待支付, 1-待发货, 2-待收货, 3-租赁中, 4-已归还, 5-已取消, 6-已退款, 7-待归还/待寄回, 8-待商家收货",
            }
        },
        "additionalProperties": False,
    }

    def execute(self, db: Session, params: dict[str, Any], user_id: int) -> str:
        try:
            stmt = select(RentalOrder).where(RentalOrder.user_id == user_id, RentalOrder.deleted == 0)
            status = params.get("status")
            if status is not None:
                status = int(status)
                if status not in ORDER_STATUS_NAMES:
                    return json_text({"error": "订单状态 status 必须是0到8之间的整数"})
                stmt = stmt.where(RentalOrder.order_status == status)
            orders = db.scalars(stmt.order_by(RentalOrder.created_time.desc()).limit(5)).all()
            if not orders:
                return json_text(
                    {
                        "count": 0,
                        "statusFilter": ORDER_STATUS_NAMES.get(status) if status is not None else None,
                        "items": [],
                        "message": "当前没有符合条件的订单记录",
                    }
                )
            return json_text(
                {
                    "count": len(orders),
                    "statusFilter": ORDER_STATUS_NAMES.get(status) if status is not None else None,
                    "items": [
                        {
                            "id": item.id,
                            "orderNo": item.order_no,
                            "status": item.order_status,
                            "statusText": ORDER_STATUS_NAMES.get(item.order_status, "未知状态"),
                            "totalAmount": item.total_amount,
                            "startDate": item.rental_start_time,
                            "endDate": item.rental_end_time,
                        }
                        for item in orders
                    ],
                }
            )
        except (TypeError, ValueError):
            return json_text({"error": "订单状态 status 必须是0到8之间的整数"})
        except Exception:
            LOGGER.exception("query_orders failed")
            return '{"error":"订单查询失败，请稍后重试"}'


class QualificationCheckTool(AiTool):
    name = "check_qualification"
    description = (
        "查询当前登录用户最新一条飞行资质申请的审核状态、证书类型、有效期和审核意见。"
        "用户询问本人是否已提交资质、是否审核通过或资质有效期时使用。"
    )
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}

    def execute(self, db: Session, params: dict[str, Any], user_id: int) -> str:
        try:
            item = db.scalar(
                select(UserQualification)
                .where(UserQualification.user_id == user_id, UserQualification.deleted == 0)
                .order_by(UserQualification.created_time.desc())
                .limit(1)
            )
            if item is None:
                return '{"status":"未提交","message":"您还未提交飞行资质，请先在个人中心提交资质审核"}'
            status_names = {0: "待审核", 1: "审核通过", 2: "审核拒绝"}
            return json_text(
                {
                    "certificateNo": item.certificate_no,
                    "certificateType": item.certificate_type,
                    "validStartDate": item.valid_start_date,
                    "validEndDate": item.valid_end_date,
                    "auditStatusCode": item.audit_status,
                    "auditStatus": status_names.get(item.audit_status, "未知状态"),
                    "auditRemark": item.audit_remark,
                }
            )
        except Exception:
            LOGGER.exception("check_qualification failed")
            return '{"error":"飞行资质查询失败，请稍后重试"}'


class FaultReportTool(AiTool):
    name = "guide_fault_report"
    description = (
        "生成无人机故障报修操作指引。用户描述设备硬件、软件、飞行、电池、云台或其他故障，"
        "并询问如何报修时使用；本工具只提供流程，不会直接创建报修单。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "droneModel": {
                "type": "string",
                "minLength": 1,
                "description": "用户提到的故障无人机型号，可省略品牌、空格和大小写差异",
            },
            "faultType": {
                "type": "string",
                "enum": ["hardware", "software", "battery", "gimbal", "flight", "other"],
                "description": "故障类型：hardware硬件、software软件、battery电池、gimbal云台、flight飞行或other其他",
            },
        },
        "additionalProperties": False,
    }

    def execute(self, db: Session, params: dict[str, Any], user_id: int) -> str:
        model = optional_text(params, "droneModel") or "未指定设备"
        matched_by = "not_provided"
        if model != "未指定设备":
            matched_drone, matched_by = resolve_drone_by_model(db, model)
            if matched_drone is not None:
                model = matched_drone.model
        raw_fault_type = (optional_text(params, "faultType") or "other").casefold()
        fault_aliases = {
            "硬件": "hardware",
            "软件": "software",
            "电池": "battery",
            "云台": "gimbal",
            "飞行": "flight",
            "其他": "other",
        }
        fault_type = fault_aliases.get(raw_fault_type, raw_fault_type)
        fault_names = {
            "hardware": "硬件故障",
            "software": "软件故障",
            "battery": "电池故障",
            "gimbal": "云台故障",
            "flight": "飞行异常",
            "other": "其他故障",
        }
        if fault_type not in fault_names:
            return json_text({"error": "不支持的 faultType，请使用 hardware、software、battery、gimbal、flight 或 other"})
        return json_text(
            {
                "droneModel": model,
                "modelMatchedBy": matched_by,
                "faultType": fault_type,
                "faultTypeText": fault_names[fault_type],
                "steps": [
                    "1. 进入故障报修页面",
                    f"2. 选择故障设备: {model}",
                    f"3. 选择故障类型: {fault_names[fault_type]}",
                    "4. 详细描述故障现象",
                    "5. 上传故障照片",
                    "6. 提交报修申请",
                    "7. 等待管理员审核",
                ],
                "tips": "发生炸机、冒烟、鼓包或失控时请立即停止使用并远离设备，再联系管理员处理。",
            }
        )


class RecommendDroneTool(AiTool):
    name = "recommend_drone"
    description = (
        "根据使用场景、品牌偏好和每日预算，从当前已上架、状态正常且有库存的设备中推荐无人机。"
        "适用于航拍、测绘、农业、巡检、旅行、短视频等场景；品牌支持 DJI/大疆等中英文模糊匹配。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "purpose": {
                "type": "string",
                "minLength": 1,
                "description": "使用场景或需求关键词，如航拍、测绘、农业、巡检、旅行或短视频",
            },
            "brand": {
                "type": "string",
                "minLength": 1,
                "description": "可选品牌偏好，支持中英文别名和部分匹配，如 DJI 或大疆",
            },
            "budget": {
                "type": "number",
                "minimum": 0,
                "description": "每日预算上限，单位为人民币元；0或不传表示不限",
            },
        },
        "additionalProperties": False,
    }

    def execute(self, db: Session, params: dict[str, Any], user_id: int) -> str:
        try:
            conditions = [
                Drone.on_shelf == 1,
                Drone.status == 1,
                Drone.stock > 0,
                Drone.deleted == 0,
            ]
            purpose = optional_text(params, "purpose")
            if purpose:
                purpose_term = normalize_search_text(purpose)
                terms = {purpose_term} if purpose_term else set()
                conditions.append(
                    or_(
                        fuzzy_contains(Drone.type, terms),
                        fuzzy_contains(Drone.model, terms),
                        fuzzy_contains(Drone.description, terms),
                    )
                )
            brand = optional_text(params, "brand")
            if brand:
                conditions.append(fuzzy_contains(Drone.brand, brand_search_terms(brand)))
            budget = decimal_parameter(params, "budget")
            if budget is not None:
                if budget < 0:
                    return json_text({"error": "每日预算 budget 不能小于0"})
                if budget > 0:
                    conditions.append(Drone.price_per_day <= budget)
            drones = list(
                db.scalars(
                    select(Drone)
                    .where(*conditions)
                    .order_by(Drone.price_per_day.asc(), Drone.stock.desc(), Drone.id.asc())
                    .limit(5)
                ).all()
            )
            if not drones:
                return json_text(
                    {
                        "count": 0,
                        "items": [],
                        "message": "暂无同时满足场景、品牌和预算条件的可租赁设备",
                    }
                )
            return json_text(
                {
                    "count": len(drones),
                    "criteria": {"purpose": purpose, "brand": brand, "budget": budget},
                    "items": [
                        {
                            "rank": index,
                            "id": item.id,
                            "model": item.model,
                            "brand": item.brand,
                            "type": item.type,
                            "pricePerDay": item.price_per_day,
                            "stock": item.stock,
                        }
                        for index, item in enumerate(drones, 1)
                    ],
                }
            )
        except ValueError as exc:
            return json_text({"error": str(exc)})
        except Exception:
            LOGGER.exception("recommend_drone failed")
            return '{"error":"无人机推荐失败，请稍后重试"}'


class AirspaceCheckTool(AiTool):
    name = "check_airspace"
    description = (
        "查询当前登录用户最新一条空域备案申请的区域、计划时间、限高和审核状态。"
        "用户询问本人是否已备案、备案是否通过或允许飞行的区域/高度时使用。"
    )
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}

    def execute(self, db: Session, params: dict[str, Any], user_id: int) -> str:
        try:
            item = db.scalar(
                select(AirspaceRecord)
                .where(AirspaceRecord.user_id == user_id, AirspaceRecord.deleted == 0)
                .order_by(AirspaceRecord.created_time.desc())
                .limit(1)
            )
            if item is None:
                return '{"status":"未备案","message":"您还未提交空域备案申请。部分飞行区域需要提前进行空域备案。"}'
            status_names = {0: "待审核", 1: "已通过", 2: "已拒绝"}
            return json_text(
                {
                    "regionName": item.region_name,
                    "regionAddress": item.region_address,
                    "maxAltitude": item.max_altitude,
                    "plannedStartTime": item.planned_start_time,
                    "plannedEndTime": item.planned_end_time,
                    "auditStatusCode": item.audit_status,
                    "auditStatus": status_names.get(item.audit_status, "未知状态"),
                    "remark": item.audit_remark,
                }
            )
        except Exception:
            LOGGER.exception("check_airspace failed")
            return '{"error":"空域备案查询失败，请稍后重试"}'


class CalculateRentalPriceTool(AiTool):
    name = "calculate_rental_price"
    description = (
        "根据明确的无人机产品型号或数据库ID及租赁天数，读取真实日租金和押金，"
        "计算租金与含押金总计。型号匹配忽略品牌中英文写法、大小写、空格和常见分隔符；"
        "若只提供 DJI/大疆等品牌而无法唯一确定型号，必须要求用户补充型号，不得猜测。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "droneId": {
                "type": "integer",
                "minimum": 1,
                "description": "数据库无人机ID；仅在用户明确说出ID/编号时使用，不得自行猜测",
            },
            "droneModel": {
                "type": "string",
                "minLength": 1,
                "description": "完整或可唯一识别的产品型号，如 DJI Mini 3 Pro 或大疆 Mini3Pro",
            },
            "rentalDays": {
                "type": "integer",
                "minimum": 1,
                "description": "租赁天数，必须是大于0的整数",
            },
        },
        "required": ["rentalDays"],
        "anyOf": [{"required": ["droneId"]}, {"required": ["droneModel"]}],
        "additionalProperties": False,
    }

    def execute(self, db: Session, params: dict[str, Any], user_id: int) -> str:
        try:
            days_value = params.get("rentalDays", params.get("rental_days", params.get("days")))
            if days_value is None:
                return '{"error":"缺少租赁天数 rentalDays"}'
            if isinstance(days_value, bool):
                return '{"error":"租赁天数必须是大于0的整数"}'
            days = int(days_value)
            if Decimal(str(days_value)) != Decimal(days):
                return '{"error":"租赁天数必须是大于0的整数"}'
            if days <= 0:
                return '{"error":"租赁天数必须大于0"}'

            model_query = (
                optional_text(params, "droneModel")
                or optional_text(params, "model")
                or optional_text(params, "productModel")
            )
            drone_id = params.get("droneId", params.get("drone_id", params.get("equipmentId")))
            matched_by = "id"
            if model_query:
                drone, matched_by = resolve_drone_by_model(db, str(model_query))
            elif drone_id is not None:
                if isinstance(drone_id, bool) or int(drone_id) <= 0:
                    return '{"error":"无人机ID droneId 必须是大于0的整数"}'
                drone = db.scalar(
                    select(Drone).where(Drone.id == int(drone_id), Drone.deleted == 0)
                )
            else:
                return '{"error":"请提供无人机产品型号 droneModel 或无人机ID droneId"}'
            if drone is None and matched_by == "ambiguous_model":
                return json_text(
                    {
                        "error": "提供的品牌或型号可匹配多款设备，请补充完整产品型号",
                        "query": model_query,
                    }
                )
            if drone is None:
                return json_text(
                    {"error": "未找到与产品型号或ID匹配的无人机设备", "query": model_query or drone_id}
                )
            price = drone.price_per_day or Decimal("0")
            deposit = drone.deposit or Decimal("0")
            rental_fee = price * days
            total_amount = rental_fee + deposit
            return json_text(
                {
                    "droneId": drone.id,
                    "model": drone.model,
                    "brand": drone.brand,
                    "matchedBy": matched_by,
                    "rentalDays": days,
                    "pricePerDay": price,
                    "rentalFee": rental_fee,
                    "deposit": deposit,
                    "totalAmount": total_amount,
                    "totalIncludesDeposit": True,
                    "formula": f"{price} × {days} + {deposit} = {total_amount}",
                    "stock": drone.stock,
                    "available": bool(drone.on_shelf == 1 and drone.status == 1 and drone.stock > 0),
                }
            )
        except (InvalidOperation, TypeError, ValueError):
            return '{"error":"无人机ID和租赁天数必须是有效整数"}'
        except Exception:
            LOGGER.exception("calculate_rental_price failed")
            return '{"error":"价格计算失败，请稍后重试"}'


TOOLS: list[AiTool] = [
    DroneQueryTool(),
    OrderQueryTool(),
    QualificationCheckTool(),
    FaultReportTool(),
    RecommendDroneTool(),
    AirspaceCheckTool(),
    CalculateRentalPriceTool(),
]
TOOL_REGISTRY: dict[str, AiTool] = {tool.name: tool for tool in TOOLS}


def tool_definitions(openai_format: bool = False) -> list[dict[str, Any]]:
    definitions = [tool.definition() for tool in TOOLS]
    if not openai_format:
        return definitions
    return [{"type": "function", "function": definition} for definition in definitions]
