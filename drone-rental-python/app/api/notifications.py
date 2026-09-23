from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..common import result
from ..database import get_db
from ..security import CurrentUser, get_current_user
from ..services.notifications import (
    delete_notification,
    mark_all_read,
    mark_read,
    notification_page,
    unread_count,
)

router = APIRouter(prefix="/notification", dependencies=[Depends(get_current_user)])


@router.get("/list")
def notifications(
    pageNum: int = 1,
    pageSize: int = 10,
    type: str | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    return result(notification_page(db, current.user_id, pageNum, pageSize, type))


@router.get("/unread-count")
def notifications_unread(
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)
):
    return result(unread_count(db, current.user_id))


@router.put("/{notification_id}/read")
def notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    mark_read(db, current.user_id, notification_id)
    return result()


@router.put("/read-all")
def notifications_read_all(
    db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)
):
    mark_all_read(db, current.user_id)
    return result()


@router.delete("/{notification_id}")
def notification_delete(
    notification_id: int,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    delete_notification(db, current.user_id, notification_id)
    return result()
