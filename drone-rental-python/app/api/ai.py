from __future__ import annotations

from datetime import datetime
from http.client import responses
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..ai import AiChatService
from ..common import result
from ..config import Settings, get_settings
from ..database import get_db
from ..models import AiChatTrace, AiMemory, AiToolCallLog
from ..request_guards import rate_limit
from ..schemas import AiChatDTO, AiMemoryDTO
from ..security import CurrentUser, get_current_user
from ..services.helpers import paginate

router = APIRouter(prefix="/ai", dependencies=[Depends(get_current_user)])


@router.post("/chat", dependencies=[Depends(rate_limit(2, 5))])
def ai_chat(
        dto: AiChatDTO,
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
        settings: Settings = Depends(get_settings),
):
    return result(AiChatService(settings).chat(db, dto, current.user_id))


@router.post("/chat/stream", dependencies=[Depends(rate_limit(2, 5))])
def ai_chat_stream(
        dto: AiChatDTO,
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
        settings: Settings = Depends(get_settings),
):
    service = AiChatService(settings)
    service.ensure_enabled()

    def events():
        for chunk in service.stream_chat(db, dto, current.user_id):
            payload = chunk.replace("\n", "\ndata:")
            yield f"data:{payload}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/history")
def ai_history(
        sessionId: str,
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
        settings: Settings = Depends(get_settings),
):
    return result(AiChatService(settings).history(db, sessionId, current.user_id))


@router.get("/sessions")
def ai_sessions(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    rows = db.execute(
        select(
            AiChatTrace.session_id,
            func.min(AiChatTrace.created_time),
            func.max(AiChatTrace.created_time).label("last_time"),
            func.count(),
        )
        .where(AiChatTrace.user_id == current.user_id, AiChatTrace.role == "user")
        .group_by(AiChatTrace.session_id)
        .order_by(func.max(AiChatTrace.created_time).desc())
        .limit(20)
    ).all()
    sessions = []
    for session_id, first_time, _, message_count in rows:
        first_message = db.scalar(
            select(AiChatTrace)
            .where(
                AiChatTrace.session_id == session_id,
                AiChatTrace.user_id == current.user_id,
                AiChatTrace.role == "user",
            )
            .order_by(AiChatTrace.created_time.asc())
            .limit(1)
        )
        title_message = db.scalar(
            select(AiChatTrace)
            .where(
                AiChatTrace.session_id == session_id,
                AiChatTrace.user_id == current.user_id,
                AiChatTrace.role == "system",
            )
            .order_by(AiChatTrace.created_time.asc())
            .limit(1)
        )
        title = title_message.content.strip() if title_message else ""
        if not title or title in {"新会话", "新对话"}:
            title = first_message.content.strip() if first_message else "新对话"
        sessions.append(
            {
                "id": session_id,
                "title": title[:30] + "..." if len(title) > 30 else title,
                "createdTime": first_time,
                "messageCount": int(message_count),
            }
        )
    return result(sessions)


@router.post("/sessions")
def ai_session_create(
        body: dict[str, str],
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
):
    session_id = uuid4().hex
    title = body.get("title", "新对话")
    trace = AiChatTrace(
        session_id=session_id, user_id=current.user_id, role="system", content=title
    )
    db.add(trace)
    db.commit()
    return result(
        {"id": session_id, "title": title, "createdTime": trace.created_time, "messageCount": 0}
    )


@router.put("/sessions/{session_id}")
def ai_session_rename(
        session_id: str,
        body: dict[str, str],
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
):
    title = body.get("title")
    if title is None or not title.strip():
        return result(code=500, message="标题不能为空")
    trace = db.scalar(
        select(AiChatTrace)
        .where(
            AiChatTrace.session_id == session_id,
            AiChatTrace.user_id == current.user_id,
            AiChatTrace.role == "system",
        )
        .order_by(AiChatTrace.created_time.asc())
        .limit(1)
    )
    if trace:
        trace.content = title.strip()
    else:
        db.add(
            AiChatTrace(
                session_id=session_id,
                user_id=current.user_id,
                role="system",
                content=title.strip(),
            )
        )
    db.commit()
    return result()


@router.delete("/sessions/{session_id}")
def ai_session_delete(
        session_id: str,
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
):
    db.execute(
        delete(AiChatTrace).where(
            AiChatTrace.session_id == session_id, AiChatTrace.user_id == current.user_id
        )
    )
    db.commit()
    return result()


@router.get("/sessions/{session_id}/history")
def ai_session_history(
        session_id: str,
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
        settings: Settings = Depends(get_settings),
):
    return result(AiChatService(settings).history(db, session_id, current.user_id))


@router.get("/memory/list")
def ai_memories(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    items = db.scalars(
        select(AiMemory)
        .where(AiMemory.user_id == current.user_id)
        .order_by(AiMemory.importance.desc())
    ).all()
    return result(items)


@router.post("/memory/save")
def ai_memory_save(
        dto: AiMemoryDTO,
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
):
    item = db.scalar(
        select(AiMemory).where(
            AiMemory.user_id == current.user_id, AiMemory.memory_key == dto.memory_key
        )
    )
    if item:
        item.memory_value = dto.memory_value
        item.category = dto.category
        item.importance = dto.importance
    else:
        db.add(AiMemory(user_id=current.user_id, **dto.model_dump()))
    db.commit()
    return result()


@router.delete("/memory/{memory_id}")
def ai_memory_delete(
        memory_id: int,
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
):
    db.execute(
        delete(AiMemory).where(AiMemory.id == memory_id, AiMemory.user_id == current.user_id)
    )
    db.commit()
    return result()


@router.get("/tool/logs")
def ai_tool_logs(
        sessionId: str | None = None,
        pageNum: int = 1,
        pageSize: int = 10,
        db: Session = Depends(get_db),
):
    stmt = select(AiToolCallLog)
    if sessionId is not None:
        stmt = stmt.where(AiToolCallLog.session_id == sessionId)
    return result(paginate(db, stmt.order_by(AiToolCallLog.created_time.desc()), pageNum, pageSize))


@router.post("/chat/vision", dependencies=[Depends(rate_limit(2, 5))])
def ai_chat_vision(
        message: str = Form("请识别照片中的无人机型号并给出租赁建议"),
        sessionId: str | None = Form(None),
        image: UploadFile = File(...),
        db: Session = Depends(get_db),
        current: CurrentUser = Depends(get_current_user),
        settings: Settings = Depends(get_settings),
):
    content = image.file.read(
        settings.ai_vision_max_image_bytes + 1
    )

    response = AiChatService(settings).vision_chat(
        db=db,
        session_id=sessionId,
        user_id=current.user_id,
        message=message,
        filename=image.filename or "drone.jpg",
        content_type=image.content_type,
        image_content=content,
    )

    return result(response)
