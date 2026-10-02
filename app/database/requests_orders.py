from sqlalchemy import select

from app.database.models import async_session, Cart, Order, User
from app.database.requests_cart import build_cart_details, save_cart_items, restore_cart_items
from app.orders import OrderStatus, can_change_status


async def create_order_from_cart(tg_user, is_pickup: bool, address: str | None) -> Order | None:
    """Атомарно превращает корзину в заказ: в одной транзакции читает корзину, создаёт заказ и очищает корзину.
    Второй параллельный вызов дождётся первого (SELECT ... FOR UPDATE) и получит пустую корзину → None"""
    async with async_session() as session:
        cart = await session.scalar(
            select(Cart).where(Cart.user_id == tg_user.id).with_for_update()
        )
        if not cart or not cart.items:
            return None
        cart_items, total = await build_cart_details(session, cart.items)
        if not cart_items:  # в корзине были только удалённые товары
            return None

        user = await session.scalar(select(User).where(User.tg_id == tg_user.id))
        order = Order(
            user_id=tg_user.id,
            customer_name=user.name if user else None,
            customer_phone=user.phone_number if user else None,
            customer_username=tg_user.username,
            items=cart_items,
            total=total,
            is_pickup=is_pickup,
            address=address[:500] if address else None,
            status=OrderStatus.NEW,
        )
        session.add(order)
        await save_cart_items(session, cart, {})  # commit: заказ и пустая корзина сохраняются вместе
        return order


async def cancel_unsent_order(order: Order):
    """Заказ не удалось отправить менеджерам: удаляем его и возвращаем товары в корзину"""
    async with async_session() as session:
        saved_order = await session.get(Order, order.id)
        if saved_order:
            await session.delete(saved_order)
            await session.commit()
    await restore_cart_items(order.user_id, order.items)


async def set_admin_message_id(order_id: int, message_id: int):
    async with async_session() as session:
        order = await session.get(Order, order_id)
        if order:
            order.admin_message_id = message_id
            await session.commit()


async def get_order(order_id: int) -> Order | None:
    async with async_session() as session:
        return await session.get(Order, order_id)


async def get_user_orders(user_id: int, limit: int = 10) -> list[Order]:
    async with async_session() as session:
        orders = await session.scalars(
            select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(limit)
        )
        return list(orders)


async def change_order_status(order_id: int, new_status: OrderStatus, changed_by: str,
                              by_customer: bool = False) -> tuple[bool, Order | None]:
    """Меняет статус, если такой переход разрешён из текущего статуса.
    Строка блокируется (FOR UPDATE): если два менеджера нажали кнопки одновременно,
    второй увидит уже новый статус и получит отказ. Возвращает (изменён ли, актуальный заказ)"""
    async with async_session() as session:
        order = await session.scalar(
            select(Order).where(Order.id == order_id).with_for_update()
        )
        if not order or not can_change_status(OrderStatus(order.status), new_status, by_customer):
            return False, order
        order.status = new_status
        order.status_changed_by = changed_by
        await session.commit()
        return True, order
