import asyncio
import logging
import os
from aiogram import Bot, Dispatcher


from app.client import client
from app.admin import admin
from app.database.models import init_models


from dotenv import load_dotenv


load_dotenv()


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)


async def main():
    bot = Bot(token=os.getenv("TG_TOKEN"))

    dp = Dispatcher()
    dp.include_router(client)
    dp.include_router(admin)
    dp.startup.register(startup)
    dp.shutdown.register(shutdown)
    await dp.start_polling(bot)


async def startup(dispatcher: Dispatcher):
    await init_models()
    logging.info("Bot started up...")


async def shutdown(dispatcher: Dispatcher):
    logging.info("Bot shutting down...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped")
