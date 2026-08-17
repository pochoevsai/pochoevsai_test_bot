import aiohttp
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from wb_parser import extract_article, fetch_product, _fetch_name_from_basket
from admitad import make_affiliate_link
from config import FREE_LIMIT

router = Router()


class TrackState(StatesGroup):
    waiting_for_url = State()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.get_or_create_user(message.from_user.id)
    await message.answer(
        "👋 Привет! Я слежу за ценами на Wildberries и сообщаю когда товар дешевеет.\n\n"
        "📌 <b>Команды:</b>\n"
        "/add — добавить товар\n"
        "/list — мои товары\n"
        "/remove — убрать товар\n"
        "/help — помощь",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Как пользоваться:</b>\n\n"
        "1. Скопируй ссылку на товар с Wildberries\n"
        "2. Отправь /add и вставь ссылку\n"
        "3. Я буду проверять цену каждый час\n"
        "4. Когда цена упадёт — пришлю уведомление\n\n"
        f"🆓 Бесплатно: до {FREE_LIMIT} товаров\n"
        "⭐ Premium: неограниченно + моментальные уведомления",
        parse_mode="HTML",
    )


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    user = await db.get_or_create_user(message.from_user.id)
    count = await db.count_user_items(message.from_user.id)

    if count >= FREE_LIMIT and not user["is_premium"]:
        await message.answer(
            f"⛔ Лимит {FREE_LIMIT} товара на бесплатном тарифе.\n\n"
            "Удали что-то через /remove или напиши чтобы узнать про Premium."
        )
        return

    await state.set_state(TrackState.waiting_for_url)
    await message.answer(
        "📎 Отправь ссылку на товар WB или его артикул (число из URL):"
    )


@router.message(TrackState.waiting_for_url)
async def process_url(message: Message, state: FSMContext):
    await state.clear()
    text = message.text.strip()
    article = extract_article(text)

    if not article:
        await message.answer(
            "❌ Не смог найти артикул.\n"
            "Пример ссылки: https://www.wildberries.ru/catalog/12345678/detail.aspx\n"
            "Или просто число: 12345678"
        )
        return

    msg = await message.answer("🔍 Ищу товар...")
    product = await fetch_product(article)

    if not product:
        await msg.edit_text(
            "❌ Товар не найден. Проверь артикул — возможно товар снят с продажи.\n\n"
            "Пример ссылки: https://www.wildberries.ru/catalog/12345678/detail.aspx"
        )
        return

    added = await db.add_item(
        user_id=message.from_user.id,
        article=article,
        name=product["name"],
        price=product["price"],
        wb_url=product["url"],
    )

    if not added:
        await msg.edit_text("ℹ️ Этот товар уже отслеживается.")
        return

    if product["price"]:
        await msg.edit_text(
            f"✅ <b>Добавлено!</b>\n\n"
            f"🛍 {product['name']}\n"
            f"💰 Текущая цена: <b>{product['price']:,} ₽</b>\n\n"
            f"Уведомлю как только цена снизится.",
            parse_mode="HTML",
        )
    else:
        await msg.edit_text(
            f"✅ <b>Добавлено в отслеживание!</b>\n\n"
            f"🛍 {product['name']}\n"
            f"⏳ Цена будет получена при первой проверке (каждый час)\n\n"
            f"Уведомлю как только цена снизится.",
            parse_mode="HTML",
        )


@router.message(Command("debug"))
async def cmd_debug(message: Message):
    nm = 852506329
    results = [f"🔬 Debug article {nm}:"]

    # Test basket
    name = await _fetch_name_from_basket(nm)
    results.append(f"Basket name: {name or 'NONE'}")

    # Test card.wb.ru
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Origin": "https://www.wildberries.ru",
        "Referer": "https://www.wildberries.ru/",
    }
    for dest in ["-1257786", "-1255546"]:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://card.wb.ru/cards/v2/detail",
                    params={"appType": "1", "curr": "rub", "dest": dest, "nm": str(nm)},
                    headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    results.append(f"card.wb.ru dest={dest}: {r.status}")
                    if r.status == 200:
                        data = await r.json(content_type=None)
                        prods = data.get("data", {}).get("products", [])
                        results.append(f"  products: {len(prods)}")
        except Exception as e:
            results.append(f"card.wb.ru {dest}: ERROR {str(e)[:50]}")

    # Test search.wb.ru
    for key, val in [("nm", str(nm)), ("query", str(nm))]:
        try:
            params = {"appType": "1", "curr": "rub", "dest": "-1257786", key: val, "resultset": "catalog"}
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://search.wb.ru/exactmatch/ru/common/v5/search",
                    params=params, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    results.append(f"search ({key}): {r.status}")
                    if r.status == 200:
                        data = await r.json(content_type=None)
                        prods = data.get("data", {}).get("products", [])
                        results.append(f"  products: {len(prods)}")
                        if prods:
                            p = prods[0]
                            results.append(f"  id={p.get('id')} salePriceU={p.get('salePriceU')}")
        except Exception as e:
            results.append(f"search ({key}): ERROR {str(e)[:50]}")

    await message.answer("\n".join(results))


@router.message(Command("list"))
async def cmd_list(message: Message):
    items = await db.get_user_items(message.from_user.id)

    if not items:
        await message.answer(
            "📭 Список пустой.\n"
            "Добавь товар через /add"
        )
        return

    lines = ["📋 <b>Твои товары:</b>\n"]
    for i, item in enumerate(items, 1):
        price_str = f"{item['last_price']:,} ₽" if item["last_price"] else "неизвестно"
        lines.append(f"{i}. {item['name'][:40]}\n   💰 {price_str} | арт. {item['article']}")

    lines.append(f"\n<i>Всего: {len(items)}</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("remove"))
async def cmd_remove(message: Message):
    items = await db.get_user_items(message.from_user.id)

    if not items:
        await message.answer("📭 Список пустой.")
        return

    lines = ["Отправь артикул товара для удаления:\n"]
    for item in items:
        lines.append(f"• {item['name'][:35]} — <code>{item['article']}</code>")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text.regexp(r"^\d{6,10}$"))
async def process_remove_article(message: Message):
    article = int(message.text.strip())
    removed = await db.remove_item(message.from_user.id, article)

    if removed:
        await message.answer(f"🗑 Товар {article} удалён из отслеживания.")
    else:
        await message.answer(
            f"❓ Артикул {article} не найден в твоём списке.\n"
            "Используй /list чтобы увидеть все товары."
        )
