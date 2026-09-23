from .admin import router as admin_router
from .public import router as public_router
from .user import router as user_router
from .notifications import router as notification_router
from .ai import router as ai_router
from .payments import router as payment_router

__all__ = [
    "admin_router", "ai_router", "notification_router",
    "payment_router", "public_router", "user_router",
]
