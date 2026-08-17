import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMITAD_TOKEN = os.getenv("ADMITAD_TOKEN")
ADMITAD_CAMPAIGN_ID = os.getenv("ADMITAD_CAMPAIGN_ID")
FREE_LIMIT = int(os.getenv("FREE_LIMIT", "3"))
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))
PROXY_URL = os.getenv("PROXY_URL", "")

WB_API_URL = "https://card.wb.ru/cards/v2/detail"
WB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
