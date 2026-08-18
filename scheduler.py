import asyncio
import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db
from wb_parser import fetch_product
from epn import make_affiliate_link
from config import CHECK_INTERVAL_MINUTES

logger = logging.getLogger(__name__)


async def check_prices(bot: Bot):
    """Проверяет все отслеживаемые товары и отправляет уведомления при снижении цены."""
    items = await db.get_all_items()
    logger.info(f"Проверяю {len(items)} товаров...")

    for item in items:
        try:
            product = await fetch_product(item["article"])
            if not product or product["price"] is None:
                continue

            new_price = product["price"]
            old_price = item["last_price"]

            if old_price is None:
                # First successful price fetch — just save it, no notification
                await db.update_price(item["id"], new_price)
                logger.info(f"Первая цена для article={item['article']}: {new_price} ₽")
            elif new_price < old_price:
                diff = old_price - new_price
                pct = round(diff / old_price * 100)

                affiliate_url = await make_affiliate_link(
                    item["wb_url"], subid=str(item["user_id"])
                )

                await bot.send_message(
                    chat_id=item["user_id"],
                    text=(
                        f"🔥 <b>Цена снизилась!</b>\n\n"
                        f"🛍 {item['name']}\n"
                        f"📉 {old_price:,} ₽ → <b>{new_price:,} ₽</b>\n"
                        f"💸 Скидка: {diff:,} ₽ (-{pct}%)\n\n"
                        f"👉 <a href='{affiliate_url}'>Купить сейчас</a>"
                    ),
                    parse_mode="HTML",
                    disable_web_page_preview=False,
                )
                logger.info(f"Уведомление отправлено user={item['user_id']} article={item['article']}")
                await db.update_price(item["id"], new_price)
            elif new_price != old_price:
                await db.update_price(item["id"], new_price)

            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Ошибка при проверке {item['article']}: {e}")


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_prices,
        trigger="interval",
        minutes=CHECK_INTERVAL_MINUTES,
        args=[bot],
        id="price_checker",
    )
    return scheduler
