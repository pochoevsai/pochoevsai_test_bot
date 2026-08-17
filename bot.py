import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

from config import BOT_TOKEN, PROXY_URL
from handlers import router
from database import init_db
from scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан в .env")

    await init_db()
    logger.info("База данных инициализирована")

    if PROXY_URL:
        from aiohttp_socks import ProxyConnector
        connector = ProxyConnector.from_url(PROXY_URL)
        session = AiohttpSession(connector=connector)
        bot = Bot(token=BOT_TOKEN, session=session)
        logger.info(f"Прокси: {PROXY_URL}")
    else:
        bot = Bot(token=BOT_TOKEN)

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Планировщик запущен")
    logger.info("Бот запущен")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
