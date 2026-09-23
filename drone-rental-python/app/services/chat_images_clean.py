from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..models import AiImageAttachment
from ..storage import get_storage

LOGGER = logging.getLogger(__name__)


def cleanup_expired_ai_images(
        session_factory: sessionmaker[Session],
        settings: Settings,
        batch_size: int = 100,
) -> int:
    # 删除AI对话中超过保存期限的临时图片
    storage = get_storage(settings)
    deleted_count = 0

    with session_factory() as db:
        expired_rows = list(
            db.scalars(
                select(AiImageAttachment)
                .where(
                    AiImageAttachment.deleted == 0,
                    AiImageAttachment.expires_at
                    <= datetime.now(),
                )
                .order_by(
                    AiImageAttachment.expires_at.asc()
                )
                .limit(batch_size)
            ).all()
        )

        for attachment in expired_rows:
            removed = storage.delete(attachment.object_key)

            if not removed:
                LOGGER.warning(
                    "AI临时图片删除失败，等待下一轮重试：%s",
                    attachment.object_key,
                )
                continue

            attachment.deleted = 1
            deleted_count += 1

        db.commit()

    return deleted_count
