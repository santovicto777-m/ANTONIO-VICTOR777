import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    database_url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'nota_site.db'}")
    REQUIRE_PERSISTENT_DATABASE = os.getenv("RENDER", "").lower() == "true" or os.getenv("APP_ENV", "").lower() == "production"
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    REMEMBER_COOKIE_HTTPONLY = True
    WTF_CSRF_TIME_LIMIT = 3600
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    PROFILE_UPLOAD_FOLDER = str(BASE_DIR / "app" / "static" / "uploads" / "profile")
    PROFILE_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
