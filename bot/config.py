import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")

# MODEL — только gpt-5.1-mini или gpt-4.1-mini
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.1-mini")

# ❗ Temperature — всегда 1, иначе будет ошибка
OPENAI_TEMPERATURE = 1

# Logs
LOGS_DIR = os.getenv("LOGS_DIR", "logs")
