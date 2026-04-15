import os
from dotenv import load_dotenv

load_dotenv()

OZON_CLIENT_ID: str = os.getenv("OZON_CLIENT_ID", "")
OZON_API_KEY: str = os.getenv("OZON_API_KEY", "")

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: int = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "deepseek")   # deepseek | openai | claude
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")

MODE: str = os.getenv("MODE", "semi")                        # semi | auto
POLL_INTERVAL_MINUTES: int = int(os.getenv("POLL_INTERVAL_MINUTES", "15"))
DRY_RUN: bool = os.getenv("DRY_RUN", "false").lower() == "true"
