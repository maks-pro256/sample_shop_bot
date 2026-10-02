from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import async_session, Cart, Card


async def _get_or_create_cart(session: AsyncSession, user_id: int) -> Cart:
    cart = await session.scalar(select(Cart).where(Cart.user_id == user_id))
    if not cart:
        cart = Cart(user_id=user_id, items={})
        session.add(cart)
    return cart


async def _save_items(session: AsyncSession, cart: Cart, items: dict):
    # Присваиваем новый dict: изменения внутри старого SQLAlchemy не замечает и не сохраняет
    cart.items = items
    await session.commit()


async def add_to_cart(user_id: int, card_id: int):
    async with async_session() as session:
        cart = await _get_or_create_cart(session, user_id)
        items = dict(cart.items or {})
        items[str(card_id)] = items.get(str(card_id), 0) + 1
        await _save_items(session, cart, items)


async def change_quantity(user_id: int, card_id: int, delta: int):
    """Меняет количество на delta; при нуле товар убирается из корзины"""
    async with async_session() as session:
        cart = await _get_or_create_cart(session, user_id)
        items = dict(cart.items or {})
        new_quantity = items.get(str(card_id), 0) + delta
        if new_quantity > 0:
            items[str(card_id)] = new_quantity
        else:
            items.pop(str(card_id), None)
        await _save_items(session, cart, items)


async def remove_from_cart(user_id: int, card_id: int):
    async with async_session() as session:
        cart = await _get_or_create_cart(session, user_id)
        items = dict(cart.items or {})
        items.pop(str(card_id), None)
        await _save_items(session, cart, items)


async def clear_cart(user_id: int):
    async with async_session() as session:
        cart = await _get_or_create_cart(session, user_id)
        await _save_items(session, cart, {})


async def get_cart_details(user_id: int) -> tuple[list[dict], int]:
    """Возвращает позиции корзины и общую сумму. Удалённые админом товары пропускаются"""
    async with async_session() as session:
        cart = await session.scalar(select(Cart).where(Cart.user_id == user_id))
        if not cart or not cart.items:
            return [], 0

        cart_details = []
        total = 0
        for card_id_str, quantity in cart.items.items():
            card = await session.get(Card, int(card_id_str))
            if card:
                cart_details.append({
                    'id': card.id,
                    'name': card.name,
                    'price': card.price,
                    'quantity': quantity,
                    'total': card.price * quantity
                })
                total += card.price * quantity

        return cart_details, total
