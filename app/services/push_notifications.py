from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import router as auth_router
from app.notifications_api import router as notifications_router
from app.services.notification_activity_scheduler import _cycle as process_activity_cycle
from app.services.notifications import run_notification_cycle

# auth_router is already imported by main.py before live-sync modules are loaded.
# Mount notification preferences under the existing /api/auth router without
# adding another top-level router to main.py.
if not any(getattr(r, 'path', '').startswith('/notifications/preferences') for r in auth_router.routes):
    auth_router.include_router(notifications_router)


async def process_push_notifications(db: AsyncSession) -> dict:
    # Live sync commits match changes immediately before calling us. The new
    # engine owns all notification categories and opens short isolated sessions
    # for delivery, so the live-sync transaction is never held during network IO.
    del db
    activity_error=None;notification_error=None
    try:
        await process_activity_cycle()
    except Exception as exc:
        activity_error=type(exc).__name__
    try:
        await run_notification_cycle()
    except Exception as exc:
        notification_error=type(exc).__name__
    return {
        'configured':True,
        'engine':'notifications-v2',
        'activity_error':activity_error,
        'notification_error':notification_error,
    }
