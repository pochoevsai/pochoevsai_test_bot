import aiohttp
import urllib.parse
from config import EPN_CLIENT_ID, EPN_CLIENT_SECRET


async def make_affiliate_link(wb_url: str, subid: str = "") -> str:
    """Конвертирует WB ссылку в партнёрскую через EPN API 2.0."""
    if not EPN_CLIENT_ID or not EPN_CLIENT_SECRET:
        return wb_url

    try:
        encoded_url = urllib.parse.quote(wb_url, safe="")
        api_url = (
            f"https://epn.bz/api/v2/deeplink"
            f"?client_id={EPN_CLIENT_ID}"
            f"&client_secret={EPN_CLIENT_SECRET}"
            f"&url={encoded_url}"
            + (f"&subid={subid}" if subid else "")
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(
                api_url, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    link = data.get("data", {}).get("url") or data.get("url")
                    if link:
                        return link
    except Exception:
        pass

    # Fallback: прямая ссылка через epn.bz/go
    encoded = urllib.parse.quote(wb_url, safe="")
    return f"https://epn.bz/go/wb?client_id={EPN_CLIENT_ID}&url={encoded}"
