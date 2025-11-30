# bot/config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")
