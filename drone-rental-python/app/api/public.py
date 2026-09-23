from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from ..common import BusinessException, C, ResultCode, result, serialize
from ..config import Settings, get_settings
from ..database import get_db
from ..models import Comment, Drone
from ..request_guards import rate_limit
from ..schemas import LoginDTO, RegisterDTO
from ..services.drones import available_page, get_drone
from ..services.files import sign_payload_field, signed_file_data
from ..services.helpers import paginate
from ..services.support import comment_vo
from ..services.users import login, register
from ..storage import get_storage
from ..redis import DRONE_CACHE_NAMESPACE, RedisSupport, get_redis_support
from ..security import decode_token

router = APIRouter()


@router.post("/auth/register", dependencies=[Depends(rate_limit(1, 3))])
def register_api(dto: RegisterDTO, db: Session = Depends(get_db)):
    register(db, dto);
    return result()


@router.post("/auth/login", dependencies=[Depends(rate_limit(2, 5))])
def login_api(dto: LoginDTO, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
              redis_support: RedisSupport = Depends(get_redis_support)):
    data = login(db, dto, settings)
    _record_login_session(redis_support, data, settings)
    return result(data)


@router.post("/auth/admin/login", dependencies=[Depends(rate_limit(2, 5))])
def admin_login_api(dto: LoginDTO, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
                    redis_support: RedisSupport = Depends(get_redis_support)):
    data = login(db, dto, settings, admin=True)
    _record_login_session(redis_support, data, settings)
    return result(data)


@router.get("/drone/list")
def drones(page: int = 1, pageSize: int = 10, keyword: str | None = None, brand: str | None = None,
           type: str | None = None, status: int | None = None, minPrice: Decimal | None = None,
           maxPrice: Decimal | None = None, sortBy: str | None = None, sortOrder: str = "desc",
           db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
           redis_support: RedisSupport = Depends(get_redis_support)):
    version = redis_support.namespace_version(DRONE_CACHE_NAMESPACE)
    params = {
        "page": page, "pageSize": pageSize, "keyword": keyword, "brand": brand, "type": type,
        "status": status, "minPrice": minPrice, "maxPrice": maxPrice, "sortBy": sortBy, "sortOrder": sortOrder,
    }

    cache_key = None
    data = None
    if version is not None:
        digest = redis_support.params_digest(params)
        cache_key = f"cache:drone:v{version}:list:{digest}"
        data = redis_support.get_json(cache_key)

    if data is None:
        # 缓存稳定的对象 key，不缓存 MinIO 临时签名 URL。
        data = available_page(db, page, pageSize, keyword, brand, type,
                              status, minPrice, maxPrice, sortBy, sortOrder, storage=None, )
        if cache_key is not None:
            redis_support.set_json(cache_key, data, settings.redis_drone_list_cache_ttl_seconds)

    storage = get_storage(settings)
    for record in data.get("records", []):
        sign_payload_field(record, "image", "imageKey", storage)
    return result(data)


@router.get("/drone/detail/{drone_id}")
def drone_detail(drone_id: int,
                 db: Session = Depends(get_db),
                 settings: Settings = Depends(get_settings),
                 redis_support: RedisSupport = Depends(get_redis_support)
                 ):
    version = redis_support.namespace_version(DRONE_CACHE_NAMESPACE)
    cache_key = (
        f"cache:drone:v{version}:detail:{drone_id}"
        if version is not None
        else None
    )
    data = redis_support.get_json(cache_key) if cache_key is not None else None
    if data is None:
        data = serialize(get_drone(db, drone_id))
        if cache_key is not None:
            redis_support.set_json(cache_key,data,settings.redis_drone_detail_cache_ttl_seconds)
    sign_payload_field(data, "image", "imageKey", get_storage(settings))
    return result(data)


@router.get("/drone/{drone_id}/image-urls")
def drone_image_urls(drone_id: int, db: Session = Depends(get_db),
                     settings: Settings = Depends(get_settings)):
    return result(signed_file_data(get_storage(settings), get_drone(db, drone_id).image, settings))


@router.get("/drone/brands")
def brands(db: Session = Depends(get_db)):
    values = db.scalars(select(distinct(Drone.brand)).where(Drone.deleted == 0, Drone.on_shelf == 1,
                                                            Drone.brand.is_not(None), Drone.brand != "")).all()
    return result(list(values))


@router.get("/drone/types")
def types(db: Session = Depends(get_db)):
    values = db.scalars(select(distinct(Drone.type)).where(Drone.deleted == 0, Drone.on_shelf == 1,
                                                           Drone.type.is_not(None), Drone.type != "")).all()
    return result(list(values))


@router.get("/drone/stats")
def drone_stats(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(Drone).where(
        Drone.deleted == 0, Drone.on_shelf == 1)) or 0
    available = db.scalar(select(func.count()).select_from(Drone).where(
        Drone.deleted == 0, Drone.on_shelf == 1, Drone.status == 1)) or 0
    brand_count = db.scalar(select(func.count(distinct(Drone.brand))).where(
        Drone.deleted == 0, Drone.on_shelf == 1, Drone.brand.is_not(None), Drone.brand != "")) or 0
    return result({"totalDrones": total, "availableDrones": available, "brandCount": brand_count})


@router.get("/drone/{drone_id}/comments")
def drone_comments(drone_id: int, pageNum: int = 1, pageSize: int = 10,
                   db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    stmt = select(Comment).where(Comment.drone_id == drone_id,
                                 Comment.status == C.COMMENT_NORMAL, Comment.deleted == 0)
    paged = paginate(db, stmt.order_by(Comment.created_time.desc()), pageNum, pageSize)
    storage = get_storage(settings)
    paged["records"] = [comment_vo(db, item, storage) for item in paged["records"]]
    return result(paged)


@router.get("/comment/{comment_id}/image-urls")
def comment_image_urls(comment_id: int, db: Session = Depends(get_db),
                       settings: Settings = Depends(get_settings)):
    item = db.scalar(select(Comment).where(
        Comment.id == comment_id,
        Comment.status == C.COMMENT_NORMAL,
        Comment.deleted == 0,
    ))
    if item is None:
        raise BusinessException(ResultCode.COMMENT_NOT_EXIST)
    return result(signed_file_data(get_storage(settings), item.images, settings))


@router.get('/actuator/redis')
def redis_health(
        settings: Settings = Depends(get_settings),
        redis_support: RedisSupport = Depends(get_redis_support),
):
    if not settings.redis_enabled:
        return result({"status": "DISABLED", "required": False})
    return result({
        "status": "UP" if redis_support.ping() else "DOWN",
        "required": False,
    })


def _record_login_session(
        redis_support: RedisSupport, data: dict, settings: Settings
) -> None:
    current = decode_token(data["token"], settings)
    remaining = max(current.expires_at - int(datetime.now(timezone.utc).timestamp()), 1)
    redis_support.record_session(
        current.token_id,
        {"userId": current.user_id, "username": current.username, "role": current.role},
        remaining,
    )
