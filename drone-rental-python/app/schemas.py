from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_snake(name: str) -> str:
    import re
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class Schema(BaseModel):
    model_config = ConfigDict(alias_generator=lambda value: "".join(
        word if index == 0 else word.capitalize() for index, word in enumerate(value.split("_"))
    ), populate_by_name=True, extra="ignore")


class LoginDTO(Schema):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RegisterDTO(Schema):
    username: str = Field(min_length=4, max_length=20)
    password: str = Field(min_length=6, max_length=20)
    nickname: str | None = None
    phone: str | None = Field(default=None, pattern=r"^1[3-9]\d{9}$")
    email: str | None = None


class UserUpdateDTO(Schema):
    nickname: str | None = None
    phone: str | None = Field(default=None, pattern=r"^1[3-9]\d{9}$")
    email: str | None = None
    avatar: str | None = None
    address: str | None = None


class QualificationDTO(Schema):
    certificate_no: str = Field(min_length=1)
    certificate_type: str | None = None
    certificate_image: str | None = None
    valid_start_date: date
    valid_end_date: date


class AuditDTO(Schema):
    audit_status: int
    audit_remark: str | None = None


class AirspaceRecordDTO(Schema):
    region_name: str = Field(min_length=1)
    region_address: str | None = None
    longitude: Decimal | None = None
    latitude: Decimal | None = None
    radius: int | None = None
    max_altitude: int | None = None
    planned_start_time: datetime | None = None
    planned_end_time: datetime | None = None
    purpose: str | None = None


class DroneDTO(Schema):
    model: str = Field(min_length=1)
    brand: str | None = None
    type: str | None = None
    description: str | None = None
    image: str | None = None
    price_per_day: Decimal = Field(gt=0)
    deposit: Decimal = Field(default=Decimal("0"), ge=0)
    stock: int = Field(ge=0)
    flight_time: int | None = None
    max_payload: Decimal | None = None
    max_speed: Decimal | None = None
    max_range: Decimal | None = None
    status: int | None = None
    on_shelf: int | None = None


class OrderCreateDTO(Schema):
    drone_id: int
    airspace_record_id: int | None = None
    start_date: date
    end_date: date
    delivery_address: str | None = None
    remark: str | None = None


class ReturnApplyDTO(Schema):
    reason: str | None = Field(default=None, max_length=255)


class ReturnShipmentDTO(Schema):
    express_company: str = Field(min_length=1, max_length=100)
    express_no: str = Field(min_length=1, max_length=100)


class DepositSettlementDTO(Schema):
    deduction_amount: Decimal = Field(default=Decimal("0"), ge=0)
    deduction_reason: str | None = Field(default=None, max_length=255)


class RefundDTO(Schema):
    mode: Literal["full", "deposit"] = "full"
    reason: str | None = Field(default=None, max_length=255)


class CommentDTO(Schema):
    drone_id: int
    order_id: int | None = None
    content: str = Field(min_length=1)
    rating: int | None = Field(default=None, ge=1, le=5)
    images: str | None = None


class FaultReportDTO(Schema):
    drone_id: int
    order_id: int | None = None
    fault_type: str | None = None
    fault_description: str = Field(min_length=1)
    fault_images: str | None = None
    fault_time: datetime | None = None


class MaintenanceTicketDTO(Schema):
    maintenance_type: str | None = None
    maintenance_description: str | None = None
    status: int | None = None
    estimated_cost: Decimal | None = None
    actual_cost: Decimal | None = None
    estimated_days: int | None = None
    actual_days: int | None = None
    assignee_name: str | None = None
    progress_note: str | None = None


class AiChatDTO(Schema):
    message: str = Field(min_length=1)
    session_id: str | None = None


class AiMemoryDTO(Schema):
    memory_key: str = Field(min_length=1)
    memory_value: str = Field(min_length=1)
    category: str = "general"
    importance: int = Field(default=5, ge=1, le=10)
