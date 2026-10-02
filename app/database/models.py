from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import BigInteger, String, ForeignKey, JSON, DateTime, Text
import os


from dotenv import load_dotenv


load_dotenv()


engine = create_async_engine(url=os.getenv("DB_URL"), echo=True)


async_session = async_sessionmaker(engine)


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
    image: Mapped[str] = mapped_column(String(256))
    category_id: Mapped[int] = mapped_column(ForeignKey('categories.id', ondelete='CASCADE'))


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.tg_id'), unique=True)  # Telegram ID пользователя
    items: Mapped[dict] = mapped_column(JSON, default=dict)  # {"card_id": количество}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ShopSetting(Base):
    """Настройки магазина, которые админ меняет из бота (ключ -> значение)"""
    __tablename__ = "shop_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
