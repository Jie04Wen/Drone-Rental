"""Persistent notifications and real-time delivery."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..common import page_result
from ..models import Notification, User
from ..websockets import notification_manager
from .helpers import paginate


def send_notification(
    db: Session,
    user_id: int,
    title: str,
    content: str,
    notification_type: str | None,
    related_id: str | None,
) -> Notification:
    """对应 Java：NotificationServiceImpl.send。"""
    item = Notification(
        user_id=user_id,
        title=title,
        content=content,
        type=notification_type or "system",
        related_id=related_id,
        is_read=0,
    )
    db.add(item)
    db.flush()
    notification_manager.send_to_user(
        user_id,
        {
            "id": item.id,
            "title": title,
            "content": content,
            "type": item.type,
            "relatedId": related_id,
            "createdTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    return item


def send_system_notification(db: Session, title: str, content: str) -> None:
    users = db.scalars(select(User).where(User.status == 1, User.deleted == 0)).all()
    for user in users:
        send_notification(db, user.id, title, content, "system", None)


def notification_page(
    db: Session, user_id: int, page: int, page_size: int, notification_type: str | None
) -> dict:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if notification_type:
        stmt = stmt.where(Notification.type == notification_type)
    return paginate(db, stmt.order_by(Notification.created_time.desc()), page, page_size)


def unread_count(db: Session, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == user_id, Notification.is_read == 0
            )
        )
        or 0
    )


def mark_read(db: Session, user_id: int, notification_id: int) -> None:
    item = db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
    )
    if item is not None and item.is_read == 0:
        item.is_read = 1
        item.read_time = datetime.now()
        db.commit()


def mark_all_read(db: Session, user_id: int) -> None:
    items = db.scalars(
        select(Notification).where(Notification.user_id == user_id, Notification.is_read == 0)
    ).all()
    now = datetime.now()
    for item in items:
        item.is_read = 1
        item.read_time = now
    db.commit()


def delete_notification(db: Session, user_id: int, notification_id: int) -> None:
    item = db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
    )
    if item is not None:
        db.delete(item)
        db.commit()
