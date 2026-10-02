import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation


from app.client import client
from app.admin import admin
from app.database.models import init_models
from app.middlewares import ThrottlingMiddleware
from app.timezone import MSK


from dotenv import load_dotenv


load_dotenv()


# Время в логах по Москве независимо от часового пояса сервера
logging.Formatter.converter = staticmethod(
    lambda timestamp: datetime.fromtimestamp(timestamp, MSK).timetuple()
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("shop_bot")


async def main():
    bot = Bot(token=os.getenv("TG_TOKEN"))

    # События одного пользователя обрабатываются строго по очереди:
    # иначе фото из альбома, пришедшие одновременно, затирают друг друга в FSM
    dp = Dispatcher(events_isolation=SimpleEventIsolation())
    throttling = ThrottlingMiddleware()
    dp.message.outer_middleware(throttling)
    dp.callback_query.outer_middleware(throttling)
    dp.include_router(client)
    dp.include_router(admin)
    dp.startup.register(startup)
    dp.shutdown.register(shutdown)
    await dp.start_polling(bot)


async def startup(dispatcher: Dispatcher):
    await init_models()
    logger.info("Бот запущен")


async def shutdown(dispatcher: Dispatcher):
    logger.info("Бот останавливается")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
