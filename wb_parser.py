import aiohttp
import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

WB_CARD_API = "https://card.wb.ru/cards/v2/detail"
WB_SEARCH_API = "https://search.wb.ru/exactmatch/ru/common/v5/search"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
    "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "Connection": "keep-alive",
}

DEST_LIST = ["-1257786", "-1255546", "-2133462", "-1123654"]


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


def _estimate_basket(vol: int) -> int:
    # Calibrated: vol=8525 → basket=38, ratio ≈ 220
    return max(1, min(60, vol // 220))


async def _fetch_name_from_basket(nm: int) -> Optional[str]:
    vol = nm // 100000
    part = nm // 1000
    estimated = _estimate_basket(vol)
    # Try estimated basket first, then expand search ±10
    for delta in [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7, 8, -8, 9, -9, 10, -10]:
        n = estimated + delta
        if n < 1 or n > 60:
            continue
        url = f"https://basket-{n:02d}.wbbasket.ru/vol{vol}/part{part}/{nm}/info/ru/card.json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        name = data.get("imt_name") or data.get("name")
                        if name:
                            logger.info(f"Found article {nm} on basket-{n:02d}")
                            return name
        except Exception as e:
            logger.debug(f"basket-{n:02d} error: {e}")
    logger.warning(f"Name not found in any basket for article {nm}")
    return None


def _extract_price(product: dict) -> Optional[int]:
    for size in product.get("sizes", []):
        p = size.get("price", {})
        sale = p.get("product") or p.get("sale") or p.get("basic")
        if sale:
            return sale // 100
    if product.get("salePriceU"):
        return product["salePriceU"] // 100
    if product.get("priceU"):
        return product["priceU"] // 100
    return None


async def _fetch_price_card_api(nm: int) -> Optional[int]:
    for dest in DEST_LIST:
        params = {"appType": "1", "curr": "rub", "dest": dest, "nm": str(nm)}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    WB_CARD_API,
                    params=params,
                    headers=BROWSER_HEADERS,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,
                ) as resp:
                    logger.info(f"card.wb.ru status for {nm}: {resp.status}")
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        products = data.get("data", {}).get("products", [])
                        if products:
                            return _extract_price(products[0])
        except Exception as e:
            logger.warning(f"card.wb.ru error for {nm}: {e}")
        await asyncio.sleep(0.3)
    return None


async def _fetch_price_search_api(nm: int) -> Optional[int]:
    # Try both nm param and query param
    variants = [
        {"appType": "1", "curr": "rub", "dest": "-1257786", "nm": str(nm), "resultset": "catalog"},
        {"appType": "1", "curr": "rub", "dest": "-1257786", "query": str(nm), "resultset": "catalog", "sort": "popular"},
    ]
    for params in variants:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    WB_SEARCH_API,
                    params=params,
                    headers=BROWSER_HEADERS,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,
                ) as resp:
                    logger.info(f"search.wb.ru ({list(params.keys())[-2]}) status for {nm}: {resp.status}")
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        products = data.get("data", {}).get("products", [])
                        for p in products:
                            if p.get("id") == nm:
                                price = _extract_price(p)
                                if price:
                                    return price
                        if products:
                            price = _extract_price(products[0])
                            if price:
                                return price
        except Exception as e:
            logger.warning(f"search.wb.ru error for {nm}: {e}")
        await asyncio.sleep(1)
    return None


async def fetch_product(article: int) -> Optional[dict]:
    """
    Returns dict with price=None if product exists but price unavailable.
    Returns None only if article doesn't exist at all.
    """
    name_task = _fetch_name_from_basket(article)
    price_task = _fetch_price_card_api(article)
    name, price = await asyncio.gather(name_task, price_task)

    if price is None:
        logger.info(f"card.wb.ru gave no price for {article}, trying search API")
        await asyncio.sleep(1)
        price = await _fetch_price_search_api(article)

    if not name:
        logger.warning(f"fetch_product: article {article} not found in basket CDN")
        return None

    if price is None:
        logger.warning(f"fetch_product: article {article} found (name OK) but price unavailable")

    return {
        "name": name,
        "price": price,  # may be None
        "url": build_wb_url(article),
        "article": article,
    }
