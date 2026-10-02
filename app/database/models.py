from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from datetime import datetime, timezone
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import BigInteger, Boolean, String, ForeignKey, JSON, DateTime, Text
import os


from dotenv import load_dotenv


load_dotenv()


# DB_ECHO=true пишет в лог каждый SQL-запрос, нужно только для отладки
engine = create_async_engine(
    url=os.getenv("DB_URL"),
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
)


# expire_on_commit=False: объекты остаются читаемыми после commit и закрытия сессии
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str] = mapped_column(String(25), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(25), nullable=True)


class Category(Base):
    __tablename__ = 'categories'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(25), unique=True)


class Card(Base):
    __tablename__ = 'cards'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(256))
    price: Mapped[int]
    image: Mapped[str] = mapped_column(String(256))  # обложка, первое фото товара
    category_id: Mapped[int] = mapped_column(ForeignKey('categories.id', ondelete='CASCADE'))


class CardPhoto(Base):
    """Дополнительные фото товара (обложка хранится в Card.image).
    Отдельная таблица, а не новая колонка: create_all создаст её и в уже существующей БД"""
    __tablename__ = 'card_photos'

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey('cards.id', ondelete='CASCADE'), index=True)
    file_id: Mapped[str] = mapped_column(String(256))
    position: Mapped[int]


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.tg_id'), unique=True)  # Telegram ID пользователя
    items: Mapped[dict] = mapped_column(JSON, default=dict)  # {"card_id": количество}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Order(Base):
    """Заказ — «документ»: состав, цены и контакты покупателя копируются на момент заказа,
    поэтому последующие изменения товаров и профиля его не меняют"""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)  # номер заказа для покупателя и менеджеров
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.tg_id'), index=True)
    customer_name: Mapped[str] = mapped_column(String(25), nullable=True)
    customer_phone: Mapped[str] = mapped_column(String(25), nullable=True)
    customer_username: Mapped[str] = mapped_column(String(64), nullable=True)
    items: Mapped[list] = mapped_column(JSON)  # [{"id", "name", "price", "quantity", "total"}]
    total: Mapped[int]
    is_pickup: Mapped[bool] = mapped_column(Boolean)
    address: Mapped[str] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    status_changed_by: Mapped[str] = mapped_column(String(100), nullable=True)
    admin_message_id: Mapped[int] = mapped_column(BigInteger, nullable=True)  # сообщение в чате заказов
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ShopSetting(Base):
    """Настройки магазина, которые админ меняет из бота (ключ -> значение)"""
    __tablename__ = "shop_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
