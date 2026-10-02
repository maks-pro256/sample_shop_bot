"""Статусы заказов: допустимые переходы, подписи и тексты для менеджеров и покупателей"""
from enum import StrEnum

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.timezone import to_msk


class OrderStatus(StrEnum):
    NEW = "new"
    ACCEPTED = "accepted"
    READY = "ready"  # «Готов к выдаче» для самовывоза, «Передан в доставку» для доставки
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Менеджер двигает заказ строго вперёд по цепочке
NEXT_STATUS = {
    OrderStatus.NEW: OrderStatus.ACCEPTED,
    OrderStatus.ACCEPTED: OrderStatus.READY,
    OrderStatus.READY: OrderStatus.COMPLETED,
}
CANCELLABLE_BY_MANAGER = {OrderStatus.NEW, OrderStatus.ACCEPTED, OrderStatus.READY}
CANCELLABLE_BY_CUSTOMER = {OrderStatus.NEW}


def can_change_status(current: OrderStatus, new: OrderStatus, by_customer: bool = False) -> bool:
    if new == OrderStatus.CANCELLED:
        return current in (CANCELLABLE_BY_CUSTOMER if by_customer else CANCELLABLE_BY_MANAGER)
    return not by_customer and NEXT_STATUS.get(current) == new


def status_label(status: str, is_pickup: bool) -> str:
    if status == OrderStatus.READY:
        return "🏬 Готов к выдаче" if is_pickup else "🚚 Передан в доставку"
    return {
        OrderStatus.NEW: "🆕 Новый",
        OrderStatus.ACCEPTED: "✅ Принят",
        OrderStatus.COMPLETED: "✔️ Выполнен",
        OrderStatus.CANCELLED: "❌ Отменён",
    }[OrderStatus(status)]


def customer_notification(order) -> str:
    """Сообщение покупателю, когда менеджер меняет статус"""
    if order.status == OrderStatus.ACCEPTED:
        return f"✅ Заказ №{order.id} принят в работу."
    if order.status == OrderStatus.READY:
        if order.is_pickup:
            return f"🏬 Заказ №{order.id} готов к выдаче, ждём вас!"
        return f"🚚 Заказ №{order.id} передан в доставку."
    if order.status == OrderStatus.COMPLETED:
        return f"✔️ Заказ №{order.id} выполнен. Спасибо за покупку!"
    return (f"❌ Заказ №{order.id} отменён магазином.\n"
            f"Если есть вопросы, свяжитесь с нами через «📞 Контакты».")


# ---------- тексты ----------

def _items_text(order, with_ids: bool = False) -> str:
    lines = []
    for item in order.items:
        name = f"{item['name']} (ID {item['id']})" if with_ids else item['name']
        lines.append(f"• {name} × {item['quantity']} = {item['total']} ₽")
    return "\n".join(lines)


def _delivery_text(order) -> str:
    return "🏬 Самовывоз" if order.is_pickup else f"🚚 Доставка, адрес: {order.address}"


def manager_order_text(order) -> str:
    """Сообщение о заказе в чате менеджеров. Перерисовывается при каждой смене статуса"""
    username = f"@{order.customer_username}" if order.customer_username else "без username"
    status_line = f"Статус: {status_label(order.status, order.is_pickup)}"
    if order.status_changed_by:
        status_line += f" — {order.status_changed_by}, {to_msk(order.updated_at):%H:%M}"
    return (
        f"📦 Заказ №{order.id}\n"
        f"🕒 {to_msk(order.created_at):%d.%m.%Y %H:%M} (МСК)\n\n"
        f"👤 {order.customer_name}, {username} (ID: {order.user_id})\n"
        f"📞 {order.customer_phone}\n"
        f"{_delivery_text(order)}\n\n"
        f"📦 Состав заказа:\n{_items_text(order, with_ids=True)}\n\n"
        f"💰 Итого: {order.total} ₽\n\n"
        f"{status_line}"
    )


CANCEL_HINT = "ℹ️ Пока заказ в статусе «🆕 Новый», вы можете отменить его сами."


def customer_order_text(order) -> str:
    text = (
        f"📦 Заказ №{order.id} от {to_msk(order.created_at):%d.%m.%Y %H:%M}\n"
        f"Статус: {status_label(order.status, order.is_pickup)}\n\n"
        f"{_items_text(order)}\n\n"
        f"💰 Итого: {order.total} ₽\n"
        f"{_delivery_text(order)}"
    )
    if order.status == OrderStatus.NEW:
        text += f"\n\n{CANCEL_HINT}"
    return text


# ---------- клавиатуры ----------

def _next_status_button_text(order) -> str:
    next_status = NEXT_STATUS[OrderStatus(order.status)]
    if next_status == OrderStatus.ACCEPTED:
        return "✅ Принять"
    if next_status == OrderStatus.COMPLETED:
        return "✔️ Выполнен"
    return status_label(next_status, order.is_pickup)


def manager_order_keyboard(order) -> InlineKeyboardMarkup | None:
    """Кнопки под заказом в чате менеджеров. У завершённых и отменённых заказов кнопок нет"""
    rows = []
    if OrderStatus(order.status) in NEXT_STATUS:
        next_status = NEXT_STATUS[OrderStatus(order.status)]
        rows.append([InlineKeyboardButton(text=_next_status_button_text(order),
                                          callback_data=f"mgr_set_{order.id}_{next_status}")])
    if OrderStatus(order.status) in CANCELLABLE_BY_MANAGER:
        rows.append([InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"mgr_cancel_{order.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def manager_cancel_confirm_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Да, отменить", callback_data=f"mgr_cancelyes_{order_id}"),
        InlineKeyboardButton(text="Нет", callback_data=f"mgr_back_{order_id}"),
    ]])


def customer_order_keyboard(order) -> InlineKeyboardMarkup:
    rows = []
    if order.status == OrderStatus.NEW:
        rows.append([InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"ucancel_{order.id}")])
    rows.append([InlineKeyboardButton(text="🔙 Мои заказы", callback_data="myorders")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def customer_cancel_confirm_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Да, отменить", callback_data=f"ucancelyes_{order_id}"),
        InlineKeyboardButton(text="Нет", callback_data=f"myorder_{order_id}"),
    ]])


def customer_orders_list(orders: list) -> tuple[str, InlineKeyboardMarkup | None]:
    if not orders:
        return "📦 У вас пока нет заказов.", None
    rows = [
        [InlineKeyboardButton(
            text=f"№{order.id} · {order.total} ₽ · {status_label(order.status, order.is_pickup)}",
            callback_data=f"myorder_{order.id}",
        )]
        for order in orders
    ]
    text = (f"📦 Ваши последние заказы ({len(orders)}). Нажмите на заказ, чтобы открыть подробности.\n\n"
            f"{CANCEL_HINT}")
    return text, InlineKeyboardMarkup(inline_keyboard=rows)
