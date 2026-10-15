"""Настройки окружения. Значения берутся из переменных окружения или файла .env."""

import os

from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "https://qa-internship.avito.com").rstrip("/")
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "15"))
REGISTER_ATTEMPTS = int(os.getenv("REGISTER_ATTEMPTS", "3"))
MAX_RESPONSE_TIME = float(os.getenv("MAX_RESPONSE_TIME", "3"))
STAND_RECOVERY_WAIT = float(os.getenv("STAND_RECOVERY_WAIT", "240"))
