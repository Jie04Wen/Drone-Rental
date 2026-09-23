from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..common import BusinessException, C, ResultCode, page_result, serialize
from ..config import Settings
from ..models import CreditRecord, RentalOrder, User, UserQualification
from ..passwords import encode_password, md5_password, verify_password
from ..schemas import LoginDTO, QualificationDTO, RegisterDTO, UserUpdateDTO
from ..security import CurrentUser, create_token
from ..storage import StorageService
from .files import sign_payload_field, validate_owned_keys
from .helpers import paginate


def register(db: Session, dto: RegisterDTO) -> None:
    if db.scalar(select(User).where(User.username == dto.username, User.deleted == 0)):
        raise BusinessException(ResultCode.USER_ALREADY_EXISTS)
    db.add(User(username=dto.username, password=encode_password(dto.password), nickname=dto.nickname or dto.username,
                phone=dto.phone, email=dto.email, role=C.ROLE_USER, status=C.USER_STATUS_NORMAL,
                credit_status=C.CREDIT_STATUS_NORMAL))
    db.commit()


def login(db: Session, dto: LoginDTO, settings: Settings, admin: bool = False) -> dict:
    user = db.scalar(select(User).where(User.username == dto.username, User.deleted == 0))
    if user is None:
        raise BusinessException(ResultCode.USER_PASSWORD_ERROR)
    valid, needs_upgrade = verify_password(dto.password, user.password)
    if not valid:
        raise BusinessException(ResultCode.USER_PASSWORD_ERROR)
    if needs_upgrade:
        user.password = encode_password(dto.password)
        db.commit()
    if admin and user.role != C.ROLE_ADMIN:
        raise BusinessException(message="无管理员权限")
    if user.status == C.USER_STATUS_DISABLED:
        raise BusinessException(ResultCode.USER_DISABLED)
    return {"userId": user.id, "username": user.username, "nickname": user.nickname, "role": user.role,
            "token": create_token(user.id, user.username, user.role, settings)}


def get_user(db: Session, user_id: int) -> User:
    user = db.scalar(select(User).where(User.id == user_id, User.deleted == 0))
    if user is None:
        raise BusinessException(ResultCode.USER_NOT_EXIST)
    return user


def check_operable(db: Session, user_id: int) -> User:
    user = get_user(db, user_id)
    if user.status == C.USER_STATUS_DISABLED:
        raise BusinessException(ResultCode.USER_DISABLED)
    if user.credit_status == C.CREDIT_STATUS_BAD:
        raise BusinessException(ResultCode.USER_CREDIT_BAD)
    return user


def user_vo(
    db: Session,
    user: User,
    include_stats: bool = False,
    storage: StorageService | None = None,
) -> dict:
    data = serialize(user)
    data.pop("password", None); data.pop("deleted", None); data.pop("updatedTime", None)
    if storage is not None:
        sign_payload_field(data, "avatar", "avatarKey", storage)
    if include_stats:
        qualification = db.scalar(select(UserQualification).where(
            UserQualification.user_id == user.id, UserQualification.deleted == 0
        ).order_by(UserQualification.created_time.desc()).limit(1))
        data["verificationStatus"] = 0 if qualification is None else {0: 1, 1: 2, 2: 3}.get(qualification.audit_status, 3)
        data["idCard"] = qualification.certificate_no if qualification else None
        data["realName"] = None
        data["lastLoginTime"] = None
        data["orderCount"] = int(db.scalar(select(func.count()).select_from(RentalOrder).where(
            RentalOrder.user_id == user.id, RentalOrder.deleted == 0)) or 0)
        # Java includes all status >= 1, including cancelled/refunded orders.
        data["totalSpent"] = db.scalar(select(func.coalesce(func.sum(RentalOrder.total_amount), 0)).where(
            RentalOrder.user_id == user.id, RentalOrder.order_status >= 1, RentalOrder.deleted == 0)) or Decimal("0")
    return data


def update_user(db: Session, user_id: int, dto: UserUpdateDTO) -> None:
    user = get_user(db, user_id)
    validate_owned_keys(dto.avatar, user_id, "avatar")
    for field in ("nickname", "phone", "email", "avatar", "address"):
        value = getattr(dto, field)
        if value is not None and value.strip():
            setattr(user, field, value)
    db.commit()


def submit_qualification(db: Session, user_id: int, dto: QualificationDTO) -> None:
    validate_owned_keys(dto.certificate_image, user_id, "qualification")
    existing = db.scalar(select(UserQualification).where(
        UserQualification.user_id == user_id, UserQualification.deleted == 0
    ).order_by(UserQualification.created_time.desc()).limit(1))
    if existing and existing.audit_status == C.AUDIT_PENDING:
        raise BusinessException(message="您已有待审核的资质申请，请等待审核结果")
    db.add(UserQualification(user_id=user_id, audit_status=C.AUDIT_PENDING, **dto.model_dump()))
    db.commit()


def check_qualification(db: Session, user_id: int) -> UserQualification:
    qualification = db.scalar(select(UserQualification).where(
        UserQualification.user_id == user_id, UserQualification.audit_status == C.AUDIT_APPROVED,
        UserQualification.deleted == 0).order_by(UserQualification.created_time.desc()).limit(1))
    if qualification is None:
        raise BusinessException(ResultCode.QUALIFICATION_NOT_APPROVED)
    if qualification.valid_end_date and qualification.valid_end_date < date.today():
        raise BusinessException(ResultCode.QUALIFICATION_EXPIRED)
    return qualification
