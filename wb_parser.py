import aiohttp
import asyncio
import re
import random
from typing import Optional
from config import WB_HEADERS

WB_API_URL = "https://card.wb.ru/cards/v2/detail"

# Заголовки максимально приближенные к реальному браузеру
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "Connection": "keep-alive",
}

# Fallback: мобильный User-Agent
MOBILE_HEADERS = {
    **BROWSER_HEADERS,
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.165 Mobile Safari/537.36",
    "appType": "1",
}

DEST_IDS = ["-1257786", "-1255546", "-2133462", "-1123654"]


def extract_article(url_or_article: str) -> Optional[int]:
    url_or_article = url_or_article.strip()
    if url_or_article.isdigit():
        return int(url_or_article)
    match = re.search(r"/catalog/(\d+)/", url_or_article)
    if match:
        return int(match.group(1))
    return None


def build_wb_url(article: int) -> str:
    return f"https://www.wildberries.ru/catalog/{article}/detail.aspx"


def _parse_price(product: dict) -> Optional[int]:
    """Пробует несколько мест где WB прячет цену."""
    # Вариант 1: через sizes (актуальный формат)
    for size in product.get("sizes", []):
        p = size.get("price", {})
        sale = p.get("product") or p.get("sale") or p.get("basic")
        if sale:
            return sale // 100

    # Вариант 2: salePriceU (старый формат)
    if product.get("salePriceU"):
        return product["salePriceU"] // 100

    # Вариант 3: priceU
    if product.get("priceU"):
        return product["priceU"] // 100

    return None


async def _fetch_with_headers(article: int, headers: dict, dest: str) -> Optional[dict]:
    params = {
        "appType": "1",
        "curr": "rub",
        "dest": dest,
        "nm": str(article),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                WB_API_URL,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
                products = data.get("data", {}).get("products", [])
                if not products:
                    return None
                p = products[0]
                price = _parse_price(p)
                if not price:
                    return None
                return {
                    "name": p.get("name", "Без названия"),
                    "price": price,
                    "url": build_wb_url(article),
                    "article": article,
                }
    except Exception:
        return None


async def fetch_product(article: int) -> Optional[dict]:
    """
    Пробует несколько комбинаций заголовков и dest-id.
    Если WB заблокировал — возвращает None.
    """
    attempts = [
        (BROWSER_HEADERS, random.choice(DEST_IDS)),
        (MOBILE_HEADERS,  "-1257786"),
        (BROWSER_HEADERS, "-1255546"),
    ]

    for headers, dest in attempts:
        result = await _fetch_with_headers(article, headers, dest)
        if result:
            return result
        await asyncio.sleep(1)

    return None
