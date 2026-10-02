from app.database.models import async_session, Category, Card, User, ShopSetting
from app.database.requests import SHOP_DESCRIPTION_KEY
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


async def add_card_database(category_id: int, name: str, price: int,
                           description: str, photo: str):
    try:
        async with async_session() as session:
            async with session.begin():  # автоматический commit при успехе
                await session.execute(
                    insert(Card).values(
                        category_id=category_id,
                        name=name, 
                        price=price, 
                        description=description, 
                        image=photo
                    )
                )
            # session.begin() автоматически делает commit
            logger.info(f"Карточка '{name}' успешно добавлена в БД")
            return True
    except SQLAlchemyError as e:
        logger.error(f"Ошибка при добавлении карточки: {e}")
        return False


async def del_card_database(card_id: int):
    async with async_session() as session:
        card = await session.get(Card, card_id)

        if card:
            await session.delete(card)
            await session.commit()


async def delete_category_database(category_id: int):
    """Полностью удаляет категорию и все связанные с ней карточки"""
    async with async_session() as session:
        # Карточки удаляем явно: SQLite без PRAGMA foreign_keys не выполняет ON DELETE CASCADE
        await session.execute(
            delete(Card).where(Card.category_id == category_id)
        )
        await session.execute(
            delete(Category).where(Category.id == category_id)
        )
        await session.commit()


async def set_shop_description(text: str):
    async with async_session() as session:
        setting = await session.get(ShopSetting, SHOP_DESCRIPTION_KEY)
        if setting:
            setting.value = text
        else:
            session.add(ShopSetting(key=SHOP_DESCRIPTION_KEY, value=text))
        await session.commit()
