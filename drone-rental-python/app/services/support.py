from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..common import BusinessException, C, ResultCode, serialize
from ..models import Comment, Drone, FaultReport, MaintenanceTicket, RentalOrder, User
from ..schemas import CommentDTO, FaultReportDTO, MaintenanceTicketDTO
from ..security import CurrentUser
from ..storage import StorageService
from .drones import get_drone
from .files import sign_payload_field, validate_owned_keys
from .helpers import make_no, paginate
from .notifications import send_notification
from .users import check_operable
from ..redis import invalidate_drone_cache


def add_comment(db: Session, dto: CommentDTO, current: CurrentUser) -> None:
    check_operable(db, current.user_id)
    validate_owned_keys(dto.images, current.user_id, "comment")
    db.add(Comment(user_id=current.user_id, drone_id=dto.drone_id, order_id=dto.order_id,
                   content=dto.content, rating=dto.rating or 5, images=dto.images, status=C.COMMENT_NORMAL))
    db.commit()


def comment_vo(db: Session, comment: Comment, storage: StorageService | None = None) -> dict:
    user, drone = db.get(User, comment.user_id), db.get(Drone, comment.drone_id)
    data = {"id": comment.id, "userId": comment.user_id,
            "userNickname": (user.nickname or user.username) if user else None,
            "userAvatar": user.avatar if user else None, "droneId": comment.drone_id,
            "droneModel": drone.model if drone else None, "orderId": comment.order_id,
            "content": comment.content, "rating": comment.rating, "images": comment.images,
            "status": comment.status, "reply": comment.reply_content,
            "replyTime": comment.reply_time, "createTime": comment.created_time}
    if storage is not None:
        sign_payload_field(data, "images", "imageKeys", storage)
        sign_payload_field(data, "userAvatar", "userAvatarKey", storage)
    return data


def report_fault(db: Session, dto: FaultReportDTO, current: CurrentUser) -> None:
    check_operable(db, current.user_id)
    validate_owned_keys(dto.fault_images, current.user_id, "fault")
    db.add(FaultReport(report_no=make_no("FLT"), user_id=current.user_id, drone_id=dto.drone_id,
                       order_id=dto.order_id, fault_type=dto.fault_type, fault_description=dto.fault_description,
                       fault_images=dto.fault_images, fault_time=dto.fault_time or datetime.now(),
                       audit_status=C.FAULT_PENDING))
    db.commit()


def fault_vo(db: Session, report: FaultReport, storage: StorageService | None = None) -> dict:
    data = serialize(report);
    data.pop("deleted", None);
    data.pop("updatedTime", None);
    data.pop("auditorId", None)
    user, drone = db.get(User, report.user_id), db.get(Drone, report.drone_id)
    order = db.get(RentalOrder, report.order_id) if report.order_id else None
    data.update({"userName": (user.nickname or user.username) if user else None,
                 "contactPhone": user.phone if user else None, "droneModel": drone.model if drone else None,
                 "droneBrand": drone.brand if drone else None, "orderNo": order.order_no if order else None})
    if storage is not None:
        sign_payload_field(data, "faultImages", "faultImageKeys", storage)
    return data


def audit_fault(db: Session, report: FaultReport, audit_status: int, remark: str | None, admin_id: int) -> None:
    if report.audit_status != C.FAULT_PENDING:
        raise BusinessException(ResultCode.FAULT_ALREADY_PROCESSED)

    report.audit_status = audit_status
    report.audit_remark = remark
    report.audit_time = datetime.now()
    report.auditor_id = admin_id

    result_text = "已确认" if audit_status == C.FAULT_CONFIRMED else "已驳回"
    send_notification(db, report.user_id, "故障报告审核结果",
                      f"您的故障报告 {report.report_no} 审核{result_text}。", "audit", report.report_no)
    drone_changed = audit_status == C.FAULT_CONFIRMED
    if drone_changed:
        db.add(MaintenanceTicket(ticket_no=make_no("MNT"), fault_report_id=report.id,
                                 drone_id=report.drone_id, user_id=report.user_id,
                                 maintenance_description=report.fault_description,
                                 status=C.MAINTENANCE_PENDING))
        drone = get_drone(db, report.drone_id);
        drone.status = C.DRONE_MAINTENANCE
    db.commit()
    if drone_changed:
        invalidate_drone_cache()


def ticket_vo(db: Session, ticket: MaintenanceTicket) -> dict:
    data = serialize(ticket);
    data.pop("deleted", None)
    drone, user, fault = db.get(Drone, ticket.drone_id), db.get(User, ticket.user_id), db.get(FaultReport,
                                                                                              ticket.fault_report_id)
    data.update({"droneModel": drone.model if drone else None, "droneBrand": drone.brand if drone else None,
                 "userName": user.username if user else None, "faultType": fault.fault_type if fault else None})
    return data


def update_ticket(db: Session, ticket: MaintenanceTicket, dto: MaintenanceTicketDTO) -> None:
    for field in ("maintenance_type", "maintenance_description", "status", "estimated_cost", "actual_cost",
                  "estimated_days", "actual_days", "assignee_name"):
        value = getattr(dto, field)
        if value is not None and (not isinstance(value, str) or value.strip()): setattr(ticket, field, value)
    if dto.progress_note and dto.progress_note.strip():
        note = f"{datetime.now().isoformat()}: {dto.progress_note}"
        ticket.progress_notes = f"{ticket.progress_notes}\n{note}" if ticket.progress_notes else note
    db.commit()


def start_ticket(db: Session, ticket: MaintenanceTicket) -> None:
    if ticket.status != C.MAINTENANCE_PENDING: raise BusinessException(message="只能开始待维修的工单")
    now = datetime.now();
    ticket.status = C.MAINTENANCE_IN_PROGRESS;
    ticket.start_time = now
    ticket.progress_notes = f"{now.isoformat()}: 开始维修"
    if ticket.user_id is not None:
        send_notification(db, ticket.user_id, "维修工单已开始",
                          f"您的维修工单 {ticket.ticket_no} 已开始维修。", "maintenance", ticket.ticket_no)
    db.commit()


def complete_ticket(db: Session, ticket: MaintenanceTicket, dto: MaintenanceTicketDTO | None) -> None:
    if ticket.status == C.MAINTENANCE_COMPLETED: raise BusinessException(ResultCode.MAINTENANCE_ALREADY_COMPLETED)
    now = datetime.now();
    ticket.status = C.MAINTENANCE_COMPLETED
    ticket.complete_time = now
    if ticket.start_time: ticket.actual_days = (now.date() - ticket.start_time.date()).days + 1
    if dto and dto.actual_cost is not None: ticket.actual_cost = dto.actual_cost
    note = f"{now.isoformat()}: 维修完成"
    ticket.progress_notes = f"{ticket.progress_notes}\n{note}" if ticket.progress_notes else note
    get_drone(db, ticket.drone_id).status = C.DRONE_AVAILABLE
    if ticket.user_id is not None:
        send_notification(db, ticket.user_id, "维修工单已完成",
                          f"您的维修工单 {ticket.ticket_no} 已完成维修。", "maintenance", ticket.ticket_no)
    db.commit()
    invalidate_drone_cache()
