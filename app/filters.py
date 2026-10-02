import os
import time

from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery


ADMIN_STATUSES = {
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
}
CACHE_TTL_SECONDS = 60

# user_id -> (is_admin, время истечения), чтобы не дёргать Telegram API на каждое нажатие
_admin_cache: dict[int, tuple[bool, float]] = {}


class IsAdmin(BaseFilter):
    """Админ — любой участник чата заказов (GROUP_ID)"""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id
        cached = _admin_cache.get(user_id)
        if cached and cached[1] > time.monotonic():
            return cached[0]

        try:
            member = await event.bot.get_chat_member(int(os.getenv("GROUP_ID")), user_id)
            # restricted — участник с ограничениями, он тоже состоит в группе
            is_admin = member.status in ADMIN_STATUSES or (
                member.status == ChatMemberStatus.RESTRICTED and member.is_member
            )
        except TelegramBadRequest:
            is_admin = False

        _admin_cache[user_id] = (is_admin, time.monotonic() + CACHE_TTL_SECONDS)
        return is_admin
