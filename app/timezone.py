from datetime import datetime, timedelta, timezone


# Москва без перехода на летнее время, всегда UTC+3
MSK = timezone(timedelta(hours=3), "MSK")


def now_msk() -> datetime:
    return datetime.now(MSK)
