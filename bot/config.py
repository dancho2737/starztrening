import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# OpenAI ключ (поддерживает оба варианта)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")

# Модель – обязательно 4o-mini
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Температура всегда = 1 (ограничение модели)
LOGS_DIR = os.getenv("LOGS_DIR", "logs")
