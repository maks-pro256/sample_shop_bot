from datetime import datetime, timedelta, timezone


# Москва без перехода на летнее время, всегда UTC+3
MSK = timezone(timedelta(hours=3), "MSK")


def now_msk() -> datetime:
    return datetime.now(MSK)


def to_msk(moment: datetime) -> datetime:
    """Время из БД в московское. SQLite отдаёт время без часового пояса — там оно хранится в UTC"""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(MSK)
