from app.database.models import async_session, Category, Card, User, ShopSetting
from sqlalchemy import select, update


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


async def get_cards_by_category(category_id: int):
    async with async_session() as session:
        return await session.scalars(select(Card).where(Card.category_id == category_id))


async def get_card(card_id: int):
    async with async_session() as session:
        return await session.get(Card, card_id)

