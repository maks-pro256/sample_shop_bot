"""Кнопки статусов под заказами в чате менеджеров (группа GROUP_ID)"""
import logging
from contextlib import suppress

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery

import app.database.requests_orders as rqo
from app.filters import IsAdmin
from app.orders import (
    OrderStatus, CANCELLABLE_BY_MANAGER, customer_notification, manager_cancel_confirm_keyboard,
    manager_order_keyboard, manager_order_text, status_label,
)


manager = Router()
manager.callback_query.filter(IsAdmin())

logger = logging.getLogger(__name__)


def manager_display_name(callback: CallbackQuery) -> str:
    user = callback.from_user
    return f"{user.full_name} (@{user.username})" if user.username else user.full_name


async def refresh_manager_message(callback: CallbackQuery, order):
    # «message is not modified», если сообщение уже показывает актуальный статус
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(manager_order_text(order), reply_markup=manager_order_keyboard(order))


async def notify_customer(bot: Bot, order) -> bool:
    try:
        await bot.send_message(order.user_id, customer_notification(order))
        return True
    except TelegramAPIError:
        logger.warning("Не удалось уведомить покупателя %s о заказе №%s", order.user_id, order.id, exc_info=True)
        return False


async def apply_status(callback: CallbackQuery, order_id: int, new_status: OrderStatus):
    is_changed, order = await rqo.change_order_status(order_id, new_status, manager_display_name(callback))
    if order is None:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if not is_changed:
        # Другой менеджер успел изменить статус раньше — показываем актуальное состояние
        await callback.answer(f"Статус уже изменён: {status_label(order.status, order.is_pickup)}", show_alert=True)
        await refresh_manager_message(callback, order)
        return

    await callback.answer(status_label(order.status, order.is_pickup))
    await refresh_manager_message(callback, order)
    logger.info("Заказ №%s: статус %s (%s)", order.id, order.status, manager_display_name(callback))
    if not await notify_customer(callback.bot, order):
        await callback.message.reply("⚠️ Не удалось уведомить покупателя: возможно, он заблокировал бота.")


@manager.callback_query(F.data.startswith("mgr_set_"))  # mgr_set_{order_id}_{статус}
async def set_order_status(callback: CallbackQuery):
    _, _, order_id, status = callback.data.split("_")
    await apply_status(callback, int(order_id), OrderStatus(status))


@manager.callback_query(F.data.startswith("mgr_cancel_"))  # первый шаг отмены: просим подтвердить
async def cancel_order_ask(callback: CallbackQuery):
    order = await rqo.get_order(int(callback.data.split("_")[2]))
    if order is None or OrderStatus(order.status) not in CANCELLABLE_BY_MANAGER:
        await callback.answer("Этот заказ уже нельзя отменить", show_alert=True)
        if order:
            await refresh_manager_message(callback, order)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=manager_cancel_confirm_keyboard(order.id))


@manager.callback_query(F.data.startswith("mgr_cancelyes_"))
async def cancel_order_confirm(callback: CallbackQuery):
    await apply_status(callback, int(callback.data.split("_")[2]), OrderStatus.CANCELLED)


@manager.callback_query(F.data.startswith("mgr_back_"))  # «Нет» в подтверждении отмены
async def cancel_order_back(callback: CallbackQuery):
    await callback.answer()
    order = await rqo.get_order(int(callback.data.split("_")[2]))
    if order:
        await refresh_manager_message(callback, order)
