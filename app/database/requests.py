import math

from app.database.models import async_session, Category, Card, CardPhoto, User, ShopSetting
from sqlalchemy import select, update, func


SHOP_DESCRIPTION_KEY = "description"
SHOP_CONTACTS_KEY = "contacts"
DEFAULT_SHOP_DESCRIPTION = "Добро пожаловать в наш магазин!"
DEFAULT_SHOP_CONTACTS = "Контакты пока не добавлены, скоро здесь появится информация."


async def get_setting(key: str, default: str) -> str:
    async with async_session() as session:
        setting = await session.get(ShopSetting, key)
        return setting.value if setting else default


async def get_shop_description() -> str:
    return await get_setting(SHOP_DESCRIPTION_KEY, DEFAULT_SHOP_DESCRIPTION)


async def get_shop_contacts() -> str:
    return await get_setting(SHOP_CONTACTS_KEY, DEFAULT_SHOP_CONTACTS)


async def set_user(tg_id):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))

        if not user:
            session.add(User(tg_id=tg_id))
            await session.commit()
            return False
        return True if user.name else False


async def get_user(tg_id):
    async with async_session() as session:
        return await session.scalar(select(User).where(User.tg_id == tg_id))


async def update_user(tg_id, name, phone_number):
    async with async_session() as session:
        await session.execute(update(User).where(User.tg_id == tg_id).values(name=name,
                                                                             phone_number=phone_number))
        await session.commit()


async def get_categories():
    async with async_session() as session:
        return await session.scalars(select(Category))


async def get_cards_page(category_id: int, page: int, page_size: int) -> tuple[list[Card], int, int]:
    """Товары категории постранично: (товары, всего страниц, фактическая страница).
    Номер страницы поджимается в допустимые границы — например, если товары удалили"""
    async with async_session() as session:
        cards_count = await session.scalar(
            select(func.count()).select_from(Card).where(Card.category_id == category_id)
        )
        pages_count = max(1, math.ceil(cards_count / page_size))
        page = min(max(page, 0), pages_count - 1)
        cards = await session.scalars(
            select(Card)
            .where(Card.category_id == category_id)
            .order_by(Card.id)
            .offset(page * page_size)
            .limit(page_size)
        )
        return list(cards), pages_count, page


async def get_card_photos(card_id: int) -> list[str]:
    """Все фото товара по порядку: обложка + дополнительные"""
    async with async_session() as session:
        card = await session.get(Card, card_id)
        if not card:
            return []
        extra_photos = await session.scalars(
            select(CardPhoto.file_id).where(CardPhoto.card_id == card_id).order_by(CardPhoto.position)
        )
        return [card.image, *extra_photos]


async def get_card(card_id: int):
    async with async_session() as session:
        return await session.get(Card, card_id)

