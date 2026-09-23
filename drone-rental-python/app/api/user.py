from fastapi import APIRouter, Depends, File, Header, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from ..common import BusinessException, C, ResultCode, page_result, result, serialize
from ..config import Settings, get_settings
from ..database import get_db
from ..models import (AirspaceRecord, Comment, CreditRecord, FaultReport,
                      MaintenanceTicket, RentalOrder, UserQualification)
from ..request_guards import rate_limit
from ..schemas import (AirspaceRecordDTO, CommentDTO, FaultReportDTO, OrderCreateDTO,
                       QualificationDTO, ReturnApplyDTO, ReturnShipmentDTO, UserUpdateDTO)
from ..security import CurrentUser, get_current_user
from ..storage import get_storage
from ..services.files import (sign_payload_field, signed_file_data,
                              upload_prefix)
from ..services.helpers import paginate
from ..services.orders import (apply_return, cancel, change_state, create_order, get_order,
                               order_vo, pay, submit_return_shipment)
from ..services.support import add_comment, comment_vo, fault_vo, report_fault
from ..passwords import encode_password, verify_password
from ..services.users import get_user, submit_qualification, update_user, user_vo

from ..redis import RedisSupport, get_redis_support

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/auth/logout")
# WebSocket 握手时自动调用 decode_token() 新建时自动检查黑名单
def logout(
        current: CurrentUser = Depends(get_current_user),
        settings: Settings = Depends(get_settings),
        redis_support: RedisSupport = Depends(get_redis_support)
):
    remaining = max(current.expires_at - int(datetime.now(timezone.utc).timestamp()), 0)
    ttl = min(remaining, settings.redis_jwt_blacklist_ttl_cap_seconds)
    redis_support.revoke(current.token_id, ttl)
    return result()


@router.get("/user/info")
def user_info(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user),
              settings: Settings = Depends(get_settings)):
    return result(user_vo(db, get_user(db, current.user_id), storage=get_storage(settings)))


@router.put("/user/info")
def user_update(dto: UserUpdateDTO, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    update_user(db, current.user_id, dto);
    return result()


@router.put("/user/password")
def password(oldPassword: str, newPassword: str, db: Session = Depends(get_db),
             current: CurrentUser = Depends(get_current_user)):
    user = get_user(db, current.user_id)
    if not verify_password(oldPassword, user.password)[0]: raise BusinessException(message="原密码错误")
    user.password = encode_password(newPassword);
    db.commit();
    return result()


@router.post("/user/qualification")
def qualification_submit(dto: QualificationDTO, db: Session = Depends(get_db),
                         current: CurrentUser = Depends(get_current_user)):
    submit_qualification(db, current.user_id, dto);
    return result()


@router.get("/user/qualification")
def qualification_get(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user),
                      settings: Settings = Depends(get_settings)):
    item = db.scalar(select(UserQualification).where(UserQualification.user_id == current.user_id,
                                                     UserQualification.deleted == 0).order_by(
        UserQualification.created_time.desc()).limit(1))
    if item is None:
        return result(None)
    data = serialize(item)
    sign_payload_field(data, "certificateImage", "certificateImageKey", get_storage(settings))
    return result(data)


@router.get("/user/avatar-url")
def avatar_url(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user),
               settings: Settings = Depends(get_settings)):
    user = get_user(db, current.user_id)
    return result(signed_file_data(get_storage(settings), user.avatar, settings))


@router.get("/user/qualification/certificate-url")
def qualification_certificate_url(
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
        settings: Settings = Depends(get_settings),
):
    item = db.scalar(select(UserQualification).where(
        UserQualification.user_id == current.user_id,
        UserQualification.deleted == 0,
    ).order_by(UserQualification.created_time.desc()).limit(1))
    if item is None:
        raise BusinessException(ResultCode.QUALIFICATION_NOT_EXIST)
    return result(signed_file_data(get_storage(settings), item.certificate_image, settings))


@router.get("/user/orders")
def my_orders(pageNum: int = 1, pageSize: int = 10, orderStatus: int | None = None,
              db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user),
              settings: Settings = Depends(get_settings)):
    stmt = select(RentalOrder).where(RentalOrder.user_id == current.user_id, RentalOrder.deleted == 0)
    if orderStatus is not None: stmt = stmt.where(RentalOrder.order_status == orderStatus)
    paged = paginate(db, stmt.order_by(RentalOrder.created_time.desc()), pageNum, pageSize)
    storage = get_storage(settings)
    paged["records"] = [order_vo(db, item, storage) for item in paged["records"]];
    return result(paged)


@router.get("/user/credit-records")
def my_credit_records(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    items = db.scalars(select(CreditRecord).where(CreditRecord.user_id == current.user_id)
                       .order_by(CreditRecord.created_time.desc())).all()
    return result(list(items))


@router.post("/airspace/submit")
def airspace_submit(dto: AirspaceRecordDTO, db: Session = Depends(get_db),
                    current: CurrentUser = Depends(get_current_user)):
    db.add(AirspaceRecord(user_id=current.user_id, audit_status=C.AUDIT_PENDING, **dto.model_dump()));
    db.commit();
    return result()


@router.get("/airspace/list")
def airspaces(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    items = db.scalars(select(AirspaceRecord).where(AirspaceRecord.user_id == current.user_id,
                                                    AirspaceRecord.deleted == 0).order_by(
        AirspaceRecord.created_time.desc())).all();
    return result(list(items))


@router.get("/airspace/approved")
def approved_airspaces(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    items = db.scalars(select(AirspaceRecord).where(AirspaceRecord.user_id == current.user_id,
                                                    AirspaceRecord.audit_status == C.AUDIT_APPROVED,
                                                    AirspaceRecord.deleted == 0)
                       .order_by(AirspaceRecord.created_time.desc())).all();
    return result(list(items))


@router.post("/order/create", dependencies=[Depends(rate_limit(2, 5))])
def order_create(
        dto: OrderCreateDTO,
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
        redis_support: RedisSupport = Depends(get_redis_support)
):
    guard_key: str | None = None
    lease: str | None = None

    if idempotency_key:
        guard_key = f"order:create:{current.user_id}:{idempotency_key}"
        lease = request.app.state.idempotency_store.acquire(guard_key)
        if lease is None:
            raise BusinessException(message="请勿重复提交订单")

    try:
        with redis_support.optional_lock(
                f"drone:stock:{dto.drone_id}"
        ) as locked:
            if not locked:
                raise BusinessException(message="当前下单人数较多，请稍后重试")
            order = create_order(db, dto, current)
        return result(order)
    except Exception:
        if guard_key and lease:
            request.app.state.idempotency_store.release(guard_key, lease)
        raise


@router.get("/order/{order_id}")
def order_detail(order_id: int, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user),
                 settings: Settings = Depends(get_settings)):
    order = get_order(db, order_id)
    if current.role != C.ROLE_ADMIN and order.user_id != current.user_id: raise BusinessException(ResultCode.FORBIDDEN)
    return result(order_vo(db, order, get_storage(settings)))


@router.post("/order/{order_id}/pay")
def order_pay(
        order_id: int,
        body: dict[str, str] | None = None,
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
        settings: Settings = Depends(get_settings),
):
    body = body or {}
    return result(pay(db, order_id, body.get("deliveryAddress"), body.get("paymentMethod"), current, settings))


@router.post("/order/{order_id}/cancel")
def order_cancel(order_id: int, reason: str | None = None, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(get_current_user)):
    cancel(db, order_id, reason, current);
    return result()


@router.post("/order/{order_id}/receive")
def order_receive(order_id: int, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    change_state(db, order_id, "receive", current);
    return result()


@router.post("/order/{order_id}/return")
def order_return(order_id: int, dto: ReturnApplyDTO | None = None, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(get_current_user)):
    return result(apply_return(db, order_id, dto or ReturnApplyDTO(), current))


@router.post("/order/{order_id}/return-shipment")
def order_return_shipment(order_id: int, dto: ReturnShipmentDTO, db: Session = Depends(get_db),
                          current: CurrentUser = Depends(get_current_user)):
    return result(submit_return_shipment(db, order_id, dto, current))


@router.post("/comment/add")
def comment_add(dto: CommentDTO, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    add_comment(db, dto, current);
    return result()


@router.get("/comment/my")
def comments_my(pageNum: int = 1, pageSize: int = 10, db: Session = Depends(get_db),
                current: CurrentUser = Depends(get_current_user), settings: Settings = Depends(get_settings)):
    paged = paginate(db, select(Comment).where(Comment.user_id == current.user_id, Comment.deleted == 0)
                     .order_by(Comment.created_time.desc()), pageNum, pageSize)
    storage = get_storage(settings)
    paged["records"] = [comment_vo(db, item, storage) for item in paged["records"]]
    return result(paged)


@router.delete("/comment/{comment_id}")
def comment_delete(comment_id: int, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    item = db.scalar(select(Comment).where(Comment.id == comment_id, Comment.deleted == 0))
    if item is None: raise BusinessException(ResultCode.COMMENT_NOT_EXIST)
    if item.user_id != current.user_id: raise BusinessException(ResultCode.FORBIDDEN)
    item.deleted = 1;
    db.commit();
    return result()


@router.post("/fault/report")
def fault_report(dto: FaultReportDTO, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    report_fault(db, dto, current);
    return result()


@router.get("/fault/my")
def faults_my(pageNum: int = 1, pageSize: int = 10, db: Session = Depends(get_db),
              current: CurrentUser = Depends(get_current_user), settings: Settings = Depends(get_settings)):
    paged = paginate(db, select(FaultReport).where(FaultReport.user_id == current.user_id, FaultReport.deleted == 0)
                     .order_by(FaultReport.created_time.desc()), pageNum, pageSize)
    storage = get_storage(settings)
    paged["records"] = [fault_vo(db, item, storage) for item in paged["records"]];
    return result(paged)


@router.get("/fault/order/{order_id}")
def faults_order(order_id: int, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user),
                 settings: Settings = Depends(get_settings)):
    order = get_order(db, order_id)
    if order.user_id != current.user_id:
        raise BusinessException(ResultCode.FORBIDDEN)
    items = db.scalars(select(FaultReport).where(FaultReport.order_id == order_id, FaultReport.deleted == 0)
                       .order_by(FaultReport.created_time.desc())).all()
    storage = get_storage(settings)
    return result([fault_vo(db, item, storage) for item in items])


@router.get("/fault/{fault_id}")
def fault_detail(fault_id: int, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user),
                 settings: Settings = Depends(get_settings)):
    item = db.scalar(select(FaultReport).where(FaultReport.id == fault_id, FaultReport.deleted == 0))
    if item is None: raise BusinessException(ResultCode.FAULT_NOT_EXIST)
    if item.user_id != current.user_id: raise BusinessException(ResultCode.FORBIDDEN)
    return result(fault_vo(db, item, get_storage(settings)))


@router.get("/fault/{fault_id}/image-urls")
def fault_image_urls(fault_id: int, db: Session = Depends(get_db),
                     current: CurrentUser = Depends(get_current_user),
                     settings: Settings = Depends(get_settings)):
    item = db.scalar(select(FaultReport).where(FaultReport.id == fault_id, FaultReport.deleted == 0))
    if item is None: raise BusinessException(ResultCode.FAULT_NOT_EXIST)
    if item.user_id != current.user_id: raise BusinessException(ResultCode.FORBIDDEN)
    return result(signed_file_data(get_storage(settings), item.fault_images, settings))


@router.get("/fault/{fault_id}/maintenance")
def fault_maintenance(fault_id: int, db: Session = Depends(get_db)):
    return result(db.scalar(select(MaintenanceTicket).where(MaintenanceTicket.fault_report_id == fault_id,
                                                            MaintenanceTicket.deleted == 0).limit(1)))


@router.post("/common/upload")
async def upload(category: str, file: UploadFile = File(...),
                 settings: Settings = Depends(get_settings),
                 current: CurrentUser = Depends(get_current_user)):
    content = await file.read(settings.max_upload_bytes + 1)
    if not content: return result(message="请选择要上传的文件", code=500)
    if len(content) > settings.max_upload_bytes: return result(message="文件超过10MB限制", code=500)
    if not file.filename: return result(message="文件名不能为空", code=500)
    prefix = upload_prefix(category, current)
    storage = get_storage(settings)
    object_key = storage.upload(file.filename, content, file.content_type, prefix)
    return result({
        "objectKey": object_key,
        "url": storage.get_access_url(object_key),
        "expiresIn": settings.minio_presigned_expiry_seconds
        if settings.storage_type.lower() == "minio"
        else None,
    })
