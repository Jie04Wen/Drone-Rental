import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import (admin_router, ai_router, notification_router,
                  payment_router, public_router, user_router)
from .ai.mcp import create_mcp_runtime
from .common import BusinessException, ResultCode, result
from .config import Settings, get_settings
from .database import make_session_factory
from .request_guards import IdempotencyStore, RateLimiter, RateLimitExceeded
from .security import decode_token
from .websockets import notification_manager
from .services.orders import close_expired_unpaid_orders
from .services.chat_images_clean import cleanup_expired_ai_images
from .redis import get_redis_support

logger = logging.getLogger(__name__)

def create_app(database_url: str | None = None, settings: Settings | None = None) -> FastAPI:
    """Application factory; tests may supply an isolated database URL."""
    settings = settings or get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                        format="%(asctime)s [%(threadName)s] %(levelname)s %(name)s - %(message)s")
    session_factory = make_session_factory(database_url or settings.database_url)
    redis_support = get_redis_support()
    mcp_runtime = (
        create_mcp_runtime(settings, session_factory)
        if settings.ai_mcp_server_enabled
        else None
    )

    def close_expired_orders_once() -> int:
        with session_factory() as db:
            return close_expired_unpaid_orders(db)

    async def scan_expired_orders() -> None:
        while True:
            try:
                closed = await asyncio.to_thread(close_expired_orders_once)
                if closed:
                    logger.info("已自动取消 %s 个支付超时订单", closed)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("扫描支付超时订单失败")
            await asyncio.sleep(settings.payment_expiry_scan_seconds)

    async def scan_expired_ai_images() -> None:
        while True:
            try:
                deleted = await asyncio.to_thread(
                    cleanup_expired_ai_images,
                    session_factory,
                    settings,
                )
                if deleted:
                    logger.info(
                        "已清理 %s 张过期的AI对话临时图片",
                        deleted,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("清理AI对话临时图片失败")
            await asyncio.sleep(settings.ai_vision_cleanup_interval_seconds)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async with AsyncExitStack() as stack:
            if mcp_runtime is not None:
                await stack.enter_async_context(mcp_runtime.server.session_manager.run())
            order_task = asyncio.create_task(
                scan_expired_orders()
            )

            tasks = [order_task]

            # 开启视觉功能时启动清理定时任务
            if settings.ai_vision_enabled:
                image_cleanup_task = asyncio.create_task(
                    scan_expired_ai_images()
                )
                tasks.append(image_cleanup_task)

            try:
                yield
            finally:
                for task in tasks:
                    task.cancel()

                for task in tasks:
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

    app = FastAPI(
        title="无人机租赁管理与 AI 智能服务系统 API",
        description="面向无人机租赁业务的后端接口。",
        version="3.0.0",
        lifespan=lifespan,
        docs_url="/swagger-ui/index.html" if settings.swagger_enabled else None,
        openapi_url="/v3/api-docs" if settings.swagger_enabled else None,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.rate_limiter = RateLimiter()
    app.state.idempotency_store = IdempotencyStore()
    app.dependency_overrides[get_settings] = lambda: settings
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(BusinessException)
    async def business_handler(_: Request, exc: BusinessException) -> JSONResponse:
        http_status = 401 if exc.code == 401 else 403 if exc.code == 403 else 200
        return JSONResponse(status_code=http_status, content=result(code=exc.code, message=exc.message))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        messages = [f"{'.'.join(map(str, error['loc'][1:]))}: {error['msg']}" for error in exc.errors()]
        return JSONResponse(status_code=400, content=result(code=ResultCode.PARAM_ERROR,
                                                            message="; ".join(messages)))

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(_: Request, __: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(status_code=429, content=result(code=429, message="请求过于频繁，请稍后再试"))

    @app.exception_handler(Exception)
    async def exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).exception("系统异常", exc_info=exc)
        return JSONResponse(status_code=500, content=result(code=500, message="服务器内部错误，请稍后再试"))

    app.include_router(public_router, prefix=settings.api_prefix)
    app.include_router(user_router, prefix=settings.api_prefix)
    app.include_router(admin_router, prefix=settings.api_prefix)
    app.include_router(notification_router, prefix=settings.api_prefix)
    app.include_router(ai_router, prefix=settings.api_prefix)
    app.include_router(payment_router, prefix=settings.api_prefix)
    if mcp_runtime is not None:
        app.mount("/mcp", mcp_runtime.app, name="mcp")

    @app.get(settings.api_prefix + "/actuator/health")
    @app.get("/actuator/health")
    def health():
        return {"status": "UP"}

    @app.websocket("/ws/notifications")
    async def notification_websocket(websocket: WebSocket, token: str | None = None):
        if not token:
            await websocket.close(code=1008)
            return
        try:
            current = decode_token(token, settings)
        except Exception:
            await websocket.close(code=1008)
            return
        await notification_manager.connect(current.user_id, websocket)
        await notification_manager.listen(current.user_id, websocket)

    # Keep the legacy local-upload route available during the MinIO migration.
    # New files are stored privately in MinIO, while existing database values such
    # as /uploads/drone.jpg must remain readable until their data is migrated.
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    app.mount(settings.api_prefix + "/uploads", StaticFiles(directory=settings.upload_path), name="uploads")
    return app


app = create_app()
