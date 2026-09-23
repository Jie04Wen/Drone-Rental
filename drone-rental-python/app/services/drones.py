from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from ..common import BusinessException, C, ResultCode, serialize
from ..models import Drone, DroneStockLog, RentalOrder
from ..schemas import DroneDTO
from ..security import CurrentUser
from ..storage import StorageService
from .files import sign_payload_field, validate_drone_keys
from .helpers import paginate
from ..redis import invalidate_drone_cache

def get_drone(db: Session, drone_id: int) -> Drone:
    drone = db.scalar(select(Drone).where(Drone.id == drone_id, Drone.deleted == 0))
    if drone is None:
        raise BusinessException(ResultCode.DRONE_NOT_EXIST)
    return drone


def check_rentable(drone: Drone) -> None:
    if drone.on_shelf != C.ON_SHELF:
        raise BusinessException(ResultCode.DRONE_OFF_SHELF)
    if drone.status != C.DRONE_AVAILABLE:
        raise BusinessException(ResultCode.DRONE_IN_MAINTENANCE if drone.status == C.DRONE_MAINTENANCE else ResultCode.DRONE_NOT_AVAILABLE)
    if drone.stock <= 0:
        raise BusinessException(ResultCode.DRONE_STOCK_NOT_ENOUGH)


def stock_log(db: Session, drone_id: int, change_type: int, amount: int, before: int, after: int,
              order_id: int | None, remark: str, operator_id: int | None) -> None:
    db.add(DroneStockLog(drone_id=drone_id, change_type=change_type, change_amount=amount,
                         before_stock=before, after_stock=after, related_order_id=order_id,
                         remark=remark, operator_id=operator_id))


def decrease_stock(db: Session, drone_id: int, amount: int, order_id: int, operator_id: int | None) -> None:
    drone = get_drone(db, drone_id)
    before = drone.stock
    if before < amount:
        raise BusinessException(ResultCode.DRONE_STOCK_NOT_ENOUGH)
    result = db.execute(update(Drone).where(Drone.id == drone_id, Drone.stock >= amount).values(stock=Drone.stock - amount))
    if result.rowcount == 0:
        raise BusinessException(ResultCode.DRONE_STOCK_NOT_ENOUGH)
    after = before - amount
    if after == 0:
        drone.status = C.DRONE_OUT_OF_STOCK
    stock_log(db, drone_id, C.STOCK_RENT, -amount, before, after, order_id, "订单租赁出库", operator_id)


def increase_stock(db: Session, drone_id: int, amount: int, order_id: int, operator_id: int | None) -> None:
    drone = get_drone(db, drone_id)
    before, after = drone.stock, drone.stock + amount
    drone.stock = after
    if before == 0 and drone.status == C.DRONE_OUT_OF_STOCK:
        drone.status = C.DRONE_AVAILABLE
    stock_log(db, drone_id, C.STOCK_RETURN, amount, before, after, order_id, "订单归还入库", operator_id)


def available_page(db: Session, page: int, page_size: int, keyword: str | None, brand: str | None,
                   drone_type: str | None, status: int | None, min_price: Decimal | None,
    max_price: Decimal | None, sort_by: str | None, sort_order: str,
    storage: StorageService | None = None) -> dict:
    stmt = select(Drone).where(Drone.deleted == 0, Drone.on_shelf == C.ON_SHELF)
    if status == C.DRONE_AVAILABLE:
        stmt = stmt.where(Drone.stock > 0, Drone.status == C.DRONE_AVAILABLE)
    elif status == C.DRONE_OUT_OF_STOCK:
        stmt = stmt.where(or_(Drone.stock <= 0, Drone.status == C.DRONE_OUT_OF_STOCK))
    elif status == C.DRONE_MAINTENANCE:
        stmt = stmt.where(Drone.stock > 0, Drone.status == C.DRONE_MAINTENANCE)
    if keyword: stmt = stmt.where(or_(Drone.model.contains(keyword), Drone.brand.contains(keyword)))
    if brand: stmt = stmt.where(Drone.brand == brand)
    if drone_type: stmt = stmt.where(Drone.type == drone_type)
    if min_price is not None: stmt = stmt.where(Drone.price_per_day >= min_price)
    if max_price is not None: stmt = stmt.where(Drone.price_per_day <= max_price)
    column = Drone.price_per_day if sort_by == "pricePerDay" else Drone.stock if sort_by == "rentCount" else Drone.created_time
    stmt = stmt.order_by(column.asc() if sort_order == "asc" else column.desc())
    paged = paginate(db, stmt, page, page_size)
    drones = paged["records"]
    counts: dict[int, int] = {}
    if drones:
        rows = db.execute(
            select(RentalOrder.drone_id, func.count(RentalOrder.id))
            .where(RentalOrder.drone_id.in_([item.id for item in drones]), RentalOrder.deleted == 0)
            .group_by(RentalOrder.drone_id)
        ).all()
        counts = {drone_id: int(count) for drone_id, count in rows}
    records = [serialize(item) | {"rentCount": counts.get(item.id, 0)} for item in drones]
    if storage is not None:
        for record in records:
            sign_payload_field(record, "image", "imageKey", storage)
    paged["records"] = records
    return paged


def add_drone(db: Session, dto: DroneDTO, operator_id: int) -> None:
    validate_drone_keys(dto.image)
    values = dto.model_dump(); values["status"] = values["status"] if values["status"] is not None else C.DRONE_AVAILABLE
    values["on_shelf"] = values["on_shelf"] if values["on_shelf"] is not None else C.ON_SHELF
    drone = Drone(**values); db.add(drone); db.flush()
    if drone.stock > 0: stock_log(db, drone.id, C.STOCK_IN, drone.stock, 0, drone.stock, None, "新增无人机入库", operator_id)
    db.commit()
    invalidate_drone_cache()
