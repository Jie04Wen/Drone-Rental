from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class AuditMixin:
    created_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
    updated_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now,
                                                   server_default=func.now())
    deleted: Mapped[int] = mapped_column(Integer, default=0)


class User(Base, AuditMixin):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    nickname: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(100))
    avatar: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=1)
    credit_status: Mapped[int] = mapped_column(Integer, default=1)


class UserQualification(Base, AuditMixin):
    __tablename__ = "user_qualification"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    certificate_no: Mapped[str] = mapped_column(String(50))
    certificate_type: Mapped[str | None] = mapped_column(String(50))
    certificate_image: Mapped[str | None] = mapped_column(String(255))
    valid_start_date: Mapped[date | None] = mapped_column(Date)
    valid_end_date: Mapped[date | None] = mapped_column(Date)
    audit_status: Mapped[int] = mapped_column(Integer, default=0)
    audit_remark: Mapped[str | None] = mapped_column(String(255))
    audit_time: Mapped[datetime | None] = mapped_column(DateTime)
    auditor_id: Mapped[int | None]


class Drone(Base, AuditMixin):
    __tablename__ = "drone"
    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(String(100))
    brand: Mapped[str | None] = mapped_column(String(50))
    type: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(String(255))
    price_per_day: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    deposit: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    flight_time: Mapped[int | None]
    max_payload: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    max_speed: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    max_range: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    status: Mapped[int] = mapped_column(Integer, default=1)
    on_shelf: Mapped[int] = mapped_column(Integer, default=1)


class DroneStockLog(Base):
    __tablename__ = "drone_stock_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    drone_id: Mapped[int]
    change_type: Mapped[int]
    change_amount: Mapped[int]
    before_stock: Mapped[int]
    after_stock: Mapped[int]
    related_order_id: Mapped[int | None]
    remark: Mapped[str | None] = mapped_column(String(255))
    operator_id: Mapped[int | None]
    created_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class AirspaceRecord(Base, AuditMixin):
    __tablename__ = "airspace_record"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int]
    region_name: Mapped[str] = mapped_column(String(100))
    region_address: Mapped[str | None] = mapped_column(String(255))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    radius: Mapped[int | None]
    max_altitude: Mapped[int | None]
    planned_start_time: Mapped[datetime | None]
    planned_end_time: Mapped[datetime | None]
    purpose: Mapped[str | None] = mapped_column(String(255))
    audit_status: Mapped[int] = mapped_column(Integer, default=0)
    audit_remark: Mapped[str | None] = mapped_column(String(255))
    audit_time: Mapped[datetime | None]
    auditor_id: Mapped[int | None]


class RentalOrder(Base, AuditMixin):
    __tablename__ = "rental_order"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True)
    user_id: Mapped[int]
    drone_id: Mapped[int]
    airspace_record_id: Mapped[int | None]
    rental_start_time: Mapped[datetime]
    rental_end_time: Mapped[datetime]
    rental_days: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    deposit_status: Mapped[int] = mapped_column(Integer, default=0)
    deposit_deduction_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    deposit_refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    deposit_deduction_reason: Mapped[str | None] = mapped_column(String(255))
    deposit_settled_time: Mapped[datetime | None] = mapped_column(DateTime)
    deposit_settled_by: Mapped[int | None]
    delivery_address: Mapped[str | None] = mapped_column(String(500))
    return_applied_time: Mapped[datetime | None] = mapped_column(DateTime)
    return_apply_reason: Mapped[str | None] = mapped_column(String(255))
    return_express_company: Mapped[str | None] = mapped_column(String(100))
    return_express_no: Mapped[str | None] = mapped_column(String(100))
    return_shipped_time: Mapped[datetime | None] = mapped_column(DateTime)
    ship_time: Mapped[datetime | None] = mapped_column(DateTime)
    receive_time: Mapped[datetime | None] = mapped_column(DateTime)
    order_status: Mapped[int] = mapped_column(Integer, default=0)
    remark: Mapped[str | None] = mapped_column(String(255))
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    cancel_time: Mapped[datetime | None]


class OrderReturnLog(Base):
    __tablename__ = "order_return_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(index=True)
    order_no: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(30))
    from_status: Mapped[int]
    to_status: Mapped[int]
    operator_id: Mapped[int]
    operator_role: Mapped[int]
    express_company: Mapped[str | None] = mapped_column(String(100))
    express_no: Mapped[str | None] = mapped_column(String(100))
    remark: Mapped[str | None] = mapped_column(String(255))
    created_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class Payment(Base, AuditMixin):
    __tablename__ = "payment"
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_no: Mapped[str] = mapped_column(String(32), unique=True)
    order_id: Mapped[int]
    order_no: Mapped[str] = mapped_column(String(32))
    user_id: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    payment_type: Mapped[int] = mapped_column(Integer, default=1)
    payment_method: Mapped[str | None] = mapped_column(String(20), default="SIMULATED")
    payment_status: Mapped[int] = mapped_column(Integer, default=0)
    payment_time: Mapped[datetime | None]
    refund_time: Mapped[datetime | None]
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    refund_reason: Mapped[str | None] = mapped_column(String(255))


class Comment(Base, AuditMixin):
    __tablename__ = "comment"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int]
    drone_id: Mapped[int]
    order_id: Mapped[int | None]
    content: Mapped[str] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(Integer, default=5)
    images: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[int] = mapped_column(Integer, default=1)
    reply_content: Mapped[str | None] = mapped_column(Text)
    reply_time: Mapped[datetime | None]


class FaultReport(Base, AuditMixin):
    __tablename__ = "fault_report"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_no: Mapped[str] = mapped_column(String(32), unique=True)
    user_id: Mapped[int]
    drone_id: Mapped[int]
    order_id: Mapped[int | None]
    fault_type: Mapped[str | None] = mapped_column(String(50))
    fault_description: Mapped[str] = mapped_column(Text)
    fault_images: Mapped[str | None] = mapped_column(String(1000))
    fault_time: Mapped[datetime | None]
    audit_status: Mapped[int] = mapped_column(Integer, default=0)
    audit_remark: Mapped[str | None] = mapped_column(String(255))
    audit_time: Mapped[datetime | None]
    auditor_id: Mapped[int | None]


class MaintenanceTicket(Base, AuditMixin):
    __tablename__ = "maintenance_ticket"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_no: Mapped[str] = mapped_column(String(32), unique=True)
    fault_report_id: Mapped[int]
    drone_id: Mapped[int]
    user_id: Mapped[int | None]
    maintenance_type: Mapped[str | None] = mapped_column(String(50))
    maintenance_description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    estimated_days: Mapped[int | None]
    actual_days: Mapped[int | None]
    start_time: Mapped[datetime | None]
    complete_time: Mapped[datetime | None]
    progress_notes: Mapped[str | None] = mapped_column(Text)
    assignee_name: Mapped[str | None] = mapped_column(String(50))


class CreditRecord(Base):
    __tablename__ = "credit_record"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int]
    change_type: Mapped[int]
    before_status: Mapped[int]
    after_status: Mapped[int]
    reason: Mapped[str | None] = mapped_column(String(255))
    operator_id: Mapped[int | None]
    operator_name: Mapped[str | None] = mapped_column(String(50))
    created_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class Notification(Base):
    __tablename__ = "notification"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(50), default="system", index=True)
    related_id: Mapped[str | None] = mapped_column(String(64))
    is_read: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(),
                                                   index=True)
    read_time: Mapped[datetime | None] = mapped_column(DateTime)


class AiChatTrace(Base):
    __tablename__ = "ai_chat_trace"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(100))
    token_usage: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(),
                                                   index=True)


class AiToolCallLog(Base):
    __tablename__ = "ai_tool_call_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    tool_name: Mapped[str] = mapped_column(String(100), index=True)
    tool_input: Mapped[str | None] = mapped_column(Text)
    tool_output: Mapped[str | None] = mapped_column(Text)
    status: Mapped[int] = mapped_column(Integer, default=1)
    error_msg: Mapped[str | None] = mapped_column(String(500))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class AiMemory(Base):
    __tablename__ = "ai_memory"
    __table_args__ = (
        UniqueConstraint("user_id", "memory_key", name="uk_user_key"),
        Index("idx_ai_memory_category", "category"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    memory_key: Mapped[str] = mapped_column(String(100))
    memory_value: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), default="general")
    importance: Mapped[int] = mapped_column(Integer, default=5)
    created_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, server_default=func.now()
    )


class AiImageAttachment(Base):
    __tablename__ = "ai_image_attachment"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    trace_id: Mapped[int | None]
    object_key: Mapped[str] = mapped_column(String(255))
    original_name: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_time: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        server_default=func.now(),
    )
    deleted: Mapped[int] = mapped_column(Integer, default=0)
