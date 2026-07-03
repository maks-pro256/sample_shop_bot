from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import Cart, Card
import json

async def get_or_create_cart(user_id: int):
    async with AsyncSession() as session:
        """Получить или создать корзину пользователя"""
        cart = await session.scalar(
            select(Cart).where(Cart.user_id == user_id)
        )
        
        if not cart:
            cart = Cart(user_id=user_id, items={})
            session.add(cart)
            await session.commit()
        
        return cart

async def add_to_cart(user_id: int, card_id: int):
    async with AsyncSession() as session:
        """Добавить товар в корзину"""
        cart = await get_or_create_cart(session, user_id)
        items = cart.items or {}
        
        card_id_str = str(card_id)
        items[card_id_str] = items.get(card_id_str, 0) + 1
        cart.items = items
        
        await session.commit()
        return True

async def get_cart_details(session: AsyncSession, user_id: int):
    async with AsyncSession() as session:
        """Получить детальную информацию о корзине"""
        cart = await session.scalar(
            select(Cart).where(Cart.user_id == user_id)
        )
        
        if not cart or not cart.items:
            return [], 0
        
        items = cart.items
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

async def remove_from_cart(session: AsyncSession, user_id: int, card_id: int):
    async with AsyncSession() as session:
        """Удалить товар из корзины"""
        cart = await session.scalar(
            select(Cart).where(Cart.user_id == user_id)
        )
        
        if cart and cart.items:
            items = cart.items
            if str(card_id) in items:
                del items[str(card_id)]
                cart.items = items
                await session.commit()
                return True
        return False

async def clear_cart(session: AsyncSession, user_id: int):
    async with AsyncSession() as session:
        """Очистить корзину"""
        cart = await session.scalar(
            select(Cart).where(Cart.user_id == user_id)
        )
        
        if cart:
            cart.items = {}
            await session.commit()
            return True
        return False

async def update_quantity(session: AsyncSession, user_id: int, card_id: int, new_quantity: int):
    async with AsyncSession() as session:
        """Изменить количество товара"""
        if new_quantity <= 0:
            return await remove_from_cart(session, user_id, card_id)
        
        cart = await session.scalar(
            select(Cart).where(Cart.user_id == user_id)
        )
        
        if cart:
            items = cart.items or {}
            items[str(card_id)] = new_quantity
            cart.items = items
            await session.commit()
            return True
        return False