import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from cachetools import TTLCache


class ThrottlingMiddleware(BaseMiddleware):
    """Антиспам по алгоритму token bucket: до `burst` действий подряд, дальше не чаще `rate` в секунду.

    Подключается как outer-middleware, чтобы спам отсекался до фильтров (IsAdmin ходит в Telegram API).
    """

    def __init__(self, rate: float = 2.0, burst: int = 5, warning_interval: float = 3.0):
        self.rate = rate
        self.burst = burst
        # user_id -> (жетоны, время последнего действия). Неактивные пользователи удаляются сами
        self._buckets: TTLCache = TTLCache(maxsize=10_000, ttl=60)
        # Кому уже показали предупреждение: не чаще раза в warning_interval, иначе бот сам заспамит в ответ
        self._warned: TTLCache = TTLCache(maxsize=10_000, ttl=warning_interval)
        # Альбомы, за которые уже списан жетон: альбом из 10 фото — одно действие, а не десять
        self._seen_albums: TTLCache = TTLCache(maxsize=10_000, ttl=10)

    def _take_token(self, user_id: int) -> bool:
        now = time.monotonic()
        tokens, last_time = self._buckets.get(user_id, (self.burst, now))
        tokens = min(self.burst, tokens + (now - last_time) * self.rate)
        is_allowed = tokens >= 1
        self._buckets[user_id] = (tokens - 1 if is_allowed else tokens, now)
        return is_allowed

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        user = event.from_user
        if user is None:
            return await handler(event, data)

        album_id = event.media_group_id if isinstance(event, Message) else None
        if album_id and album_id in self._seen_albums:
            return await handler(event, data)
        if self._take_token(user.id):
            if album_id:
                self._seen_albums[album_id] = True
            return await handler(event, data)

        if user.id not in self._warned:
            self._warned[user.id] = True
            if isinstance(event, CallbackQuery):
                await event.answer("⏳ Не так быстро")
            else:
                await event.answer("⏳ Слишком часто, подождите секунду")
        return None
