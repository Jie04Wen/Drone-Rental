from __future__ import annotations

import time
import uuid
from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..common import page_result

T = TypeVar("T")


def make_no(prefix: str) -> str:
    """Equivalent to timestamp + Hutool fastSimpleUUID suffix."""
    return f"{prefix}{int(time.time() * 1000)}{uuid.uuid4().hex[:6].upper()}"


def paginate(db: Session, statement: Select[Any], page: int, page_size: int) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    count_stmt = select(func.count()).select_from(statement.order_by(None).subquery())
    total = int(db.scalar(count_stmt) or 0)
    records = list(db.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all())
    return page_result(records, total, page, page_size)


def active(model: type[T]) -> Select[tuple[T]]:
    statement = select(model)
    if hasattr(model, "deleted"):
        statement = statement.where(model.deleted == 0)
    return statement
