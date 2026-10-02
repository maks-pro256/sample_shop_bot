from app.database.models import async_session, Category, Card, CardPhoto, User, ShopSetting
from app.database.requests import SHOP_DESCRIPTION_KEY, SHOP_CONTACTS_KEY
from sqlalchemy import select, insert, delete, func
from sqlalchemy.exc import SQLAlchemyError,IntegrityError
import logging

logger = logging.getLogger(__name__)


async def add_category_database(title: str):
    async with async_session() as session:
        try:
            # Проверяем, существует ли уже такая категория (опционально)
            result = await session.execute(
                select(Category).where(Category.name == title)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                raise IntegrityError("Категория с таким названием уже существует", 
                                   params={}, orig=None)
            
            # Добавляем новую категорию (INSERT, не UPDATE!)
            new_category = Category(name=title)
            session.add(new_category)
            
            # Или через execute с insert
            # await session.execute(
            #     insert(Category).values(name=title)
            # )
            
            await session.commit()
            
        except SQLAlchemyError:
            await session.rollback()  # Откатываем транзакцию при ошибке
            raise  # Пробрасываем исключение дальше


EDITABLE_CARD_FIELDS = {"name", "price", "description"}


def _add_extra_photos(session, card_id: int, photos: list[str]):
    for position, file_id in enumerate(photos[1:], start=1):
        session.add(CardPhoto(card_id=card_id, file_id=file_id, position=position))


async def add_card_database(category_id: int, name: str, price: int,
                            description: str, photos: list[str]) -> bool:
    """Создаёт товар: первое фото становится обложкой, остальные идут в card_photos"""
    try:
        async with async_session() as session:
            async with session.begin():  # автоматический commit при успехе
                card = Card(
                    category_id=category_id,
                    name=name,
                    price=price,
                    description=description,
                    image=photos[0],
                )
                session.add(card)
                await session.flush()  # нужен card.id для фото
                _add_extra_photos(session, card.id, photos)
            logger.info(f"Карточка '{name}' успешно добавлена в БД")
            return True
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при добавлении карточки: {e}")
        return False


async def update_card_field(card_id: int, field: str, value: str | int) -> bool:
    """Меняет одно поле товара. False, если товар уже удалён"""
    if field not in EDITABLE_CARD_FIELDS:
        raise ValueError(f"Поле {field} нельзя редактировать")
    async with async_session() as session:
        card = await session.get(Card, card_id)
        if not card:
            return False
        setattr(card, field, value)
        await session.commit()
        return True


async def replace_card_photos(card_id: int, photos: list[str]) -> bool:
    """Полностью заменяет фото товара. False, если товар уже удалён"""
    async with async_session() as session:
        card = await session.get(Card, card_id)
        if not card:
            return False
        card.image = photos[0]
        await session.execute(delete(CardPhoto).where(CardPhoto.card_id == card_id))
        _add_extra_photos(session, card_id, photos)
        await session.commit()
        return True


async def del_card_database(card_id: int):
    async with async_session() as session:
        card = await session.get(Card, card_id)

        if card:
            # Фото удаляем явно: SQLite без PRAGMA foreign_keys не выполняет ON DELETE CASCADE
            await session.execute(delete(CardPhoto).where(CardPhoto.card_id == card_id))
            await session.delete(card)
            await session.commit()


async def delete_category_database(category_id: int):
    """Полностью удаляет категорию и все связанные с ней карточки"""
    async with async_session() as session:
        # Каскад удаляем явно: SQLite без PRAGMA foreign_keys не выполняет ON DELETE CASCADE
        category_card_ids = select(Card.id).where(Card.category_id == category_id)
        await session.execute(
            delete(CardPhoto).where(CardPhoto.card_id.in_(category_card_ids))
        )
        await session.execute(
            delete(Card).where(Card.category_id == category_id)
        )
        await session.execute(
            delete(Category).where(Category.id == category_id)
        )
        await session.commit()


async def set_setting(key: str, value: str):
    async with async_session() as session:
        setting = await session.get(ShopSetting, key)
        if setting:
            setting.value = value
        else:
            session.add(ShopSetting(key=key, value=value))
        await session.commit()


async def set_shop_description(text: str):
    await set_setting(SHOP_DESCRIPTION_KEY, text)


async def set_shop_contacts(text: str):
    await set_setting(SHOP_CONTACTS_KEY, text)
