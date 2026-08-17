import aiohttp
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from wb_parser import extract_article, fetch_product, _fetch_name_from_basket
from admitad import make_affiliate_link
from config import FREE_LIMIT, PREMIUM_LIMIT, PREMIUM_PRICE_STARS, ADMIN_ID

router = Router()


class TrackState(StatesGroup):
    waiting_for_url = State()


# ── Keyboards ──────────────────────────────────────────────────────────────

def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить товар", callback_data="cb_add"),
            InlineKeyboardButton(text="📋 Мои товары",    callback_data="cb_list"),
        ],
        [
            InlineKeyboardButton(text="👤 Мой аккаунт",  callback_data="cb_account"),
            InlineKeyboardButton(text="⭐ Premium",       callback_data="cb_premium"),
        ],
        [
            InlineKeyboardButton(text="❓ Помощь",        callback_data="cb_help"),
        ],
    ])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="cb_main")]
    ])


def account_kb(is_premium: bool) -> InlineKeyboardMarkup:
    buttons = []
    if not is_premium:
        buttons.append([InlineKeyboardButton(text="⭐ Купить Premium", callback_data="cb_premium")])
    buttons.append([InlineKeyboardButton(text="◀️ Главное меню", callback_data="cb_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def remove_kb(items: list) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        rows.append([InlineKeyboardButton(
            text=f"🗑 {item['name'][:30]}",
            callback_data=f"rm_{item['article']}"
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cb_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def premium_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⭐ Купить за {PREMIUM_PRICE_STARS} Stars",
            callback_data="cb_buy_premium"
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="cb_main")],
    ])


# ── /start ─────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.get_or_create_user(message.from_user.id)
    await message.answer(
        "👋 <b>Привет!</b> Я слежу за ценами на Wildberries и пишу когда товар дешевеет.\n\n"
        "Выбери действие:",
        parse_mode="HTML",
        reply_markup=main_kb(),
    )


# ── Callback: главное меню ──────────────────────────────────────────────────

@router.callback_query(F.data == "cb_main")
async def cb_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "👋 <b>Главное меню</b>\n\nВыбери действие:",
        parse_mode="HTML",
        reply_markup=main_kb(),
    )
    await call.answer()


# ── Callback: добавить товар ────────────────────────────────────────────────

@router.callback_query(F.data == "cb_add")
async def cb_add(call: CallbackQuery, state: FSMContext):
    user = await db.get_or_create_user(call.from_user.id)
    count = await db.count_user_items(call.from_user.id)

    limit = PREMIUM_LIMIT if user["is_premium"] else FREE_LIMIT
    if count >= limit:
        txt = (
            f"⛔ Лимит {'Premium' if user['is_premium'] else 'бесплатного'} тарифа: {limit} товаров.\n\n"
            + ("" if user["is_premium"] else "Удали через «Мои товары» или купи Premium.")
        )
        await call.message.edit_text(txt, reply_markup=back_kb())
        await call.answer()
        return

    await state.set_state(TrackState.waiting_for_url)
    await call.message.edit_text(
        "📎 Отправь ссылку на товар WB или его артикул (число из URL):\n\n"
        "Пример: <code>https://www.wildberries.ru/catalog/12345678/detail.aspx</code>\n"
        "Или просто: <code>12345678</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="cb_main")]
        ]),
    )
    await call.answer()


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    user = await db.get_or_create_user(message.from_user.id)
    count = await db.count_user_items(message.from_user.id)
    limit = PREMIUM_LIMIT if user["is_premium"] else FREE_LIMIT
    if count >= limit:
        await message.answer(
            f"⛔ Лимит {limit} товаров. Удали что-то через /remove или купи Premium (/premium)."
        )
        return
    await state.set_state(TrackState.waiting_for_url)
    await message.answer("📎 Отправь ссылку или артикул товара WB:")


@router.message(TrackState.waiting_for_url)
async def process_url(message: Message, state: FSMContext):
    await state.clear()
    text = message.text.strip()
    article = extract_article(text)

    if not article:
        await message.answer(
            "❌ Не смог найти артикул.\n"
            "Пример: https://www.wildberries.ru/catalog/12345678/detail.aspx",
            reply_markup=back_kb(),
        )
        return

    msg = await message.answer("🔍 Ищу товар...")
    product = await fetch_product(article)

    if not product:
        await msg.edit_text(
            "❌ Товар не найден. Проверь артикул — возможно снят с продажи.",
            reply_markup=back_kb(),
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
        await msg.edit_text("ℹ️ Этот товар уже отслеживается.", reply_markup=back_kb())
        return

    if product["price"]:
        await msg.edit_text(
            f"✅ <b>Добавлено!</b>\n\n"
            f"🛍 {product['name']}\n"
            f"💰 Цена сейчас: <b>{product['price']:,} ₽</b>\n\n"
            f"Уведомлю когда цена снизится.",
            parse_mode="HTML",
            reply_markup=back_kb(),
        )
    else:
        await msg.edit_text(
            f"✅ <b>Добавлено!</b>\n\n"
            f"🛍 {product['name']}\n"
            f"⏳ Цена будет получена при следующей проверке (каждый час)\n\n"
            f"Уведомлю когда цена снизится.",
            parse_mode="HTML",
            reply_markup=back_kb(),
        )


# ── Callback: список товаров ────────────────────────────────────────────────

@router.callback_query(F.data == "cb_list")
async def cb_list(call: CallbackQuery):
    items = await db.get_user_items(call.from_user.id)

    if not items:
        await call.message.edit_text(
            "📭 Список пуст. Добавь товар!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить товар", callback_data="cb_add")],
                [InlineKeyboardButton(text="◀️ Меню", callback_data="cb_main")],
            ]),
        )
        await call.answer()
        return

    lines = ["📋 <b>Твои товары:</b>\n"]
    for i, item in enumerate(items, 1):
        price_str = f"{item['last_price']:,} ₽" if item["last_price"] else "—"
        lines.append(f"{i}. {item['name'][:35]}\n   💰 {price_str} | арт. {item['article']}")

    lines.append(f"\n<i>Всего: {len(items)}</i>")

    await call.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить товар", callback_data="cb_remove")],
            [InlineKeyboardButton(text="◀️ Меню", callback_data="cb_main")],
        ]),
    )
    await call.answer()


@router.message(Command("list"))
async def cmd_list(message: Message):
    items = await db.get_user_items(message.from_user.id)
    if not items:
        await message.answer("📭 Список пуст.", reply_markup=main_kb())
        return
    lines = ["📋 <b>Твои товары:</b>\n"]
    for i, item in enumerate(items, 1):
        price_str = f"{item['last_price']:,} ₽" if item["last_price"] else "—"
        lines.append(f"{i}. {item['name'][:35]}\n   💰 {price_str} | арт. {item['article']}")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=main_kb())


# ── Callback: удалить ──────────────────────────────────────────────────────

@router.callback_query(F.data == "cb_remove")
async def cb_remove(call: CallbackQuery):
    items = await db.get_user_items(call.from_user.id)
    if not items:
        await call.message.edit_text("📭 Нечего удалять.", reply_markup=back_kb())
        await call.answer()
        return
    await call.message.edit_text(
        "🗑 Выбери товар для удаления:",
        reply_markup=remove_kb(items),
    )
    await call.answer()


@router.callback_query(F.data.startswith("rm_"))
async def cb_rm_item(call: CallbackQuery):
    article = int(call.data.split("_", 1)[1])
    removed = await db.remove_item(call.from_user.id, article)
    if removed:
        await call.answer("✅ Удалено!", show_alert=False)
    else:
        await call.answer("❓ Не найдено", show_alert=False)
    # Refresh list
    items = await db.get_user_items(call.from_user.id)
    if not items:
        await call.message.edit_text("📭 Список пуст.", reply_markup=back_kb())
    else:
        await call.message.edit_reply_markup(reply_markup=remove_kb(items))


@router.message(Command("remove"))
async def cmd_remove(message: Message):
    items = await db.get_user_items(message.from_user.id)
    if not items:
        await message.answer("📭 Список пуст.")
        return
    await message.answer("🗑 Выбери товар для удаления:", reply_markup=remove_kb(items))


# ── Callback: мой аккаунт ──────────────────────────────────────────────────

@router.callback_query(F.data == "cb_account")
async def cb_account(call: CallbackQuery):
    user = await db.get_or_create_user(call.from_user.id)
    count = await db.count_user_items(call.from_user.id)
    is_premium = bool(user["is_premium"])
    limit = PREMIUM_LIMIT if is_premium else FREE_LIMIT

    tg = call.from_user
    name = tg.full_name or tg.username or str(tg.id)
    username_str = f"@{tg.username}" if tg.username else "—"
    tier = "⭐ Premium" if is_premium else "🆓 Бесплатный"

    await call.message.edit_text(
        f"👤 <b>Мой аккаунт</b>\n\n"
        f"<b>Имя:</b> {name}\n"
        f"<b>Username:</b> {username_str}\n"
        f"<b>ID:</b> <code>{tg.id}</code>\n\n"
        f"<b>Тариф:</b> {tier}\n"
        f"<b>Товаров:</b> {count} / {limit}\n\n"
        + ("" if is_premium else
           f"⭐ <b>Premium</b> — до {PREMIUM_LIMIT} товаров + моментальные уведомления\n"
           f"Стоимость: {PREMIUM_PRICE_STARS} ⭐ Telegram Stars"),
        parse_mode="HTML",
        reply_markup=account_kb(is_premium),
    )
    await call.answer()


# ── Callback: premium ──────────────────────────────────────────────────────

@router.callback_query(F.data == "cb_premium")
async def cb_premium(call: CallbackQuery):
    user = await db.get_or_create_user(call.from_user.id)
    if user["is_premium"]:
        await call.message.edit_text(
            "⭐ У тебя уже <b>Premium</b>! Наслаждайся.",
            parse_mode="HTML",
            reply_markup=back_kb(),
        )
        await call.answer()
        return

    await call.message.edit_text(
        f"⭐ <b>Premium подписка</b>\n\n"
        f"✅ До <b>{PREMIUM_LIMIT} товаров</b> одновременно (вместо {FREE_LIMIT})\n"
        f"✅ Проверка цены каждые <b>30 минут</b>\n"
        f"✅ Приоритетные уведомления\n\n"
        f"💳 Оплата через <b>Telegram Stars</b> — безопасно и мгновенно\n"
        f"Стоимость: <b>{PREMIUM_PRICE_STARS} ⭐</b>",
        parse_mode="HTML",
        reply_markup=premium_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "cb_buy_premium")
async def cb_buy_premium(call: CallbackQuery):
    await call.answer()
    await call.message.answer_invoice(
        title="⭐ WB Price Bot Premium",
        description=f"До {PREMIUM_LIMIT} товаров, проверка каждые 30 мин",
        payload="premium_subscription",
        currency="XTR",
        prices=[LabeledPrice(label="Premium", amount=PREMIUM_PRICE_STARS)],
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    await db.set_premium(message.from_user.id, True)
    await message.answer(
        "🎉 <b>Premium активирован!</b>\n\n"
        f"Теперь ты можешь отслеживать до {PREMIUM_LIMIT} товаров.\n"
        "Спасибо за поддержку! ❤️",
        parse_mode="HTML",
        reply_markup=main_kb(),
    )


# ── /setpremium (только для ADMIN_ID) ──────────────────────────────────────

@router.message(Command("setpremium"))
async def cmd_setpremium(message: Message):
    if ADMIN_ID and message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /setpremium <user_id>")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("user_id должен быть числом")
        return
    await db.set_premium(target_id, True)
    await message.answer(f"✅ Premium выдан пользователю {target_id}")


# ── Callback: помощь ───────────────────────────────────────────────────────

@router.callback_query(F.data == "cb_help")
async def cb_help(call: CallbackQuery):
    await call.message.edit_text(
        "❓ <b>Как пользоваться</b>\n\n"
        "1. Нажми <b>➕ Добавить товар</b>\n"
        "2. Отправь ссылку с Wildberries или артикул\n"
        "3. Бот будет проверять цену каждый час\n"
        "4. Когда цена упадёт — получишь уведомление\n\n"
        f"🆓 Бесплатно: до <b>{FREE_LIMIT} товаров</b>\n"
        f"⭐ Premium: до <b>{PREMIUM_LIMIT} товаров</b> + чаще проверки",
        parse_mode="HTML",
        reply_markup=back_kb(),
    )
    await call.answer()


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "❓ <b>Помощь</b>\n\n"
        "Отправь ссылку на WB или нажми кнопки в меню.",
        parse_mode="HTML",
        reply_markup=main_kb(),
    )


# ── Debug ──────────────────────────────────────────────────────────────────

@router.message(Command("debug"))
async def cmd_debug(message: Message):
    nm = 852506329
    results = [f"🔬 Debug article {nm}:"]

    name = await _fetch_name_from_basket(nm)
    results.append(f"Basket name: {name or 'NONE'}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://www.wildberries.ru",
        "Referer": "https://www.wildberries.ru/",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://card.wb.ru/cards/v4/detail",
                params={"appType": "1", "curr": "rub", "dest": "1259570991", "spp": "30", "nm": str(nm)},
                headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                results.append(f"card.wb.ru/v4: {r.status}")
                if r.status == 200:
                    data = await r.json(content_type=None)
                    prods = data.get("products", [])
                    results.append(f"  products: {len(prods)}")
                    if prods:
                        sizes = prods[0].get("sizes", [])
                        price = sizes[0].get("price", {}).get("product") if sizes else None
                        results.append(f"  price={price} → {price//100 if price else 'N/A'} ₽")
    except Exception as e:
        results.append(f"card.wb.ru/v4: ERROR {str(e)[:80]}")

    await message.answer("\n".join(results))
