import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # === Telegram ===
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    # === Cloud Run ===
    DEFAULT_IMAGE = os.getenv("DEFAULT_IMAGE", "docker.io/ajndjd2/ahmed-vip1")

    # === Browser ===
    HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
    CHROME_PROFILE_DIR = os.getenv("CHROME_PROFILE_DIR", "/tmp/chrome_profile")
    PAGE_TIMEOUT = int(os.getenv("PAGE_TIMEOUT", "60")) * 1000
    NAV_TIMEOUT = int(os.getenv("NAV_TIMEOUT", "120")) * 1000

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    # === Database ===
    DB_PATH = os.getenv("DB_PATH", "/tmp/bot.db")

    # === Logs ===
    LOG_DIR = os.getenv("LOG_DIR", "/tmp/logs")


config = Config()
