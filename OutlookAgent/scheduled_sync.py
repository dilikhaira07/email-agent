"""
scheduled_sync.py
-----------------
Cron entrypoint that gates sync execution by local time so DST changes do not
require updating the Render cron expression.
"""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .app_logging import get_logger
from .fetch_tasks import main as run_sync

logger = get_logger("email_agent.scheduled_sync")
LOCAL_TZ_NAME = "America/Winnipeg"
ALLOWED_HOURS = {8, 9, 10, 11, 12, 13}
ALLOWED_MINUTE = 45


def _local_zone():
    try:
        return ZoneInfo(LOCAL_TZ_NAME)
    except ZoneInfoNotFoundError:
        fallback = datetime.now().astimezone().tzinfo
        logger.warning("Falling back to system local timezone because %s is unavailable.", LOCAL_TZ_NAME)
        return fallback


def should_run_now(now: datetime | None = None) -> bool:
    current = now or datetime.now(_local_zone())
    if current.tzinfo is None:
        current = current.replace(tzinfo=_local_zone())
    else:
        current = current.astimezone(_local_zone())
    return current.minute == ALLOWED_MINUTE and current.hour in ALLOWED_HOURS


def main():
    now = datetime.now(_local_zone())
    if not should_run_now(now):
        logger.info("Skipping scheduled sync outside local window local_time=%s", now.isoformat(timespec="minutes"))
        return

    logger.info("Running scheduled sync local_time=%s", now.isoformat(timespec="minutes"))
    run_sync()


if __name__ == "__main__":
    main()
