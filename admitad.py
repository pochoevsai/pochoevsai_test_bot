import aiohttp
from config import ADMITAD_TOKEN, ADMITAD_CAMPAIGN_ID


async def make_affiliate_link(wb_url: str, subid: str = "") -> str:
    """Генерирует партнёрскую ссылку через Admitad API.
    Если токен не настроен — возвращает оригинальную ссылку.
    """
    if not ADMITAD_TOKEN or not ADMITAD_CAMPAIGN_ID:
        return wb_url

    api_url = f"https://api.admitad.com/deeplink/{ADMITAD_CAMPAIGN_ID}/make/"
    params = {"url": wb_url, "subid": subid}
    headers = {"Authorization": f"Bearer {ADMITAD_TOKEN}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                api_url, params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("deeplink", wb_url)
    except Exception:
        pass

    return wb_url
