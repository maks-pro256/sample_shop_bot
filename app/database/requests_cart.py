from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import async_session, Cart, Card


MAX_ITEM_QUANTITY = 20
MAX_CART_POSITIONS = 30


class CartError(Exception):
    """Действие с корзиной невозможно; текст исключения можно показать пользователю"""


async def _get_cart_for_update(session: AsyncSession, user_id: int) -> Cart:
    """Корзина с блокировкой строки до конца транзакции (SELECT ... FOR UPDATE).
    Параллельные запросы одного пользователя выполняются по очереди и не затирают друг друга"""
    query = select(Cart).where(Cart.user_id == user_id).with_for_update()
    cart = await session.scalar(query)
    if cart:
        return cart

    session.add(Cart(user_id=user_id, items={}))
    try:
        await session.flush()
    except IntegrityError:
        # Корзину только что создал параллельный запрос этого же пользователя
        await session.rollback()
    return await session.scalar(query)


async def save_cart_items(session: AsyncSession, cart: Cart, items: dict):
    # Присваиваем новый dict: изменения внутри старого SQLAlchemy не замечает и не сохраняет
    cart.items = items
    await session.commit()


async def build_cart_details(session: AsyncSession, items: dict) -> tuple[list[dict], int]:
    """Позиции корзины с названиями и ценами. Удалённые админом товары пропускаются"""
    cart_details = []
    total = 0
    for card_id_str, quantity in items.items():
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


async def add_to_cart(user_id: int, card_id: int):
    async with async_session() as session:
        if not await session.get(Card, card_id):
            raise CartError("😔 Этот товар больше не продаётся")

        cart = await _get_cart_for_update(session, user_id)
        items = dict(cart.items or {})
        key = str(card_id)
        if key not in items and len(items) >= MAX_CART_POSITIONS:
            raise CartError(f"⚠️ В корзине может быть не больше {MAX_CART_POSITIONS} разных товаров")
        if items.get(key, 0) >= MAX_ITEM_QUANTITY:
            raise CartError(f"⚠️ Не больше {MAX_ITEM_QUANTITY} шт. одного товара")
        items[key] = items.get(key, 0) + 1
        await save_cart_items(session, cart, items)


async def change_quantity(user_id: int, card_id: int, delta: int):
    """Меняет количество на delta; при нуле товар убирается из корзины"""
    async with async_session() as session:
        cart = await _get_cart_for_update(session, user_id)
        items = dict(cart.items or {})
        key = str(card_id)
        new_quantity = items.get(key, 0) + delta
        if new_quantity > MAX_ITEM_QUANTITY:
            raise CartError(f"⚠️ Не больше {MAX_ITEM_QUANTITY} шт. одного товара")
        if new_quantity > 0:
            items[key] = new_quantity
        else:
            items.pop(key, None)
        await save_cart_items(session, cart, items)


async def remove_from_cart(user_id: int, card_id: int):
    async with async_session() as session:
        cart = await _get_cart_for_update(session, user_id)
        items = dict(cart.items or {})
        items.pop(str(card_id), None)
        await save_cart_items(session, cart, items)


async def clear_cart(user_id: int):
    async with async_session() as session:
        cart = await _get_cart_for_update(session, user_id)
        await save_cart_items(session, cart, {})


async def get_cart_details(user_id: int) -> tuple[list[dict], int]:
    async with async_session() as session:
        cart = await session.scalar(select(Cart).where(Cart.user_id == user_id))
        if not cart or not cart.items:
            return [], 0
        return await build_cart_details(session, cart.items)


async def restore_cart_items(user_id: int, cart_details: list[dict]):
    """Возвращает позиции в корзину, если заказ не удалось отправить"""
    async with async_session() as session:
        cart = await _get_cart_for_update(session, user_id)
        items = dict(cart.items or {})
        for item in cart_details:
            key = str(item['id'])
            items[key] = min(MAX_ITEM_QUANTITY, items.get(key, 0) + item['quantity'])
        await save_cart_items(session, cart, items)
