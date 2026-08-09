import os

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

        ENVIRONMENT: str = "development"
        SECRET_KEY: str = os.getenv("SECRET_KEY", "")
        VIBECLOUD_FERNET_KEY: str = os.getenv("VIBECLOUD_FERNET_KEY", "")
        ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "")
        ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
        DATABASE_URL: str = os.getenv("DATABASE_URL", "")
        GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        AI_RATE_LIMIT_PER_HOUR: int = 20
        CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "")
        RATE_LIMIT_LOGIN: str = "5/minute"
        RATE_LIMIT_PUBLIC: str = "30/minute"
        MEDUSA_URL: str = os.getenv("MEDUSA_URL", "http://localhost:9000")
        MEDUSA_ADMIN_API_KEY: str = os.getenv("VIBECLOUD_API_KEY", os.getenv("MEDUSA_ADMIN_API_KEY", ""))
        MEDUSA_B2B_DISCOUNT_PERCENT: float = float(os.getenv("MEDUSA_B2B_DISCOUNT_PERCENT", "0.30"))
        MEDUSA_SYNC_BATCH_SIZE: int = int(os.getenv("MEDUSA_SYNC_BATCH_SIZE", "50"))
        STOREFRONT_URL: str = os.getenv("STOREFRONT_URL", "http://localhost:3000")
except ImportError:
    class Settings:
        ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
        SECRET_KEY = os.getenv("SECRET_KEY", "")
        VIBECLOUD_FERNET_KEY = os.getenv("VIBECLOUD_FERNET_KEY", "")
        ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
        ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
        DATABASE_URL = os.getenv("DATABASE_URL", "")
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        AI_RATE_LIMIT_PER_HOUR = int(os.getenv("AI_RATE_LIMIT_PER_HOUR", "20"))
        CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")
        RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "5/minute")
        RATE_LIMIT_PUBLIC = os.getenv("RATE_LIMIT_PUBLIC", "30/minute")
        MEDUSA_URL = os.getenv("MEDUSA_URL", "http://localhost:9000")
        MEDUSA_ADMIN_API_KEY = os.getenv("VIBECLOUD_API_KEY", os.getenv("MEDUSA_ADMIN_API_KEY", ""))
        MEDUSA_B2B_DISCOUNT_PERCENT = float(os.getenv("MEDUSA_B2B_DISCOUNT_PERCENT", "0.30"))
        MEDUSA_SYNC_BATCH_SIZE = int(os.getenv("MEDUSA_SYNC_BATCH_SIZE", "50"))
        STOREFRONT_URL = os.getenv("STOREFRONT_URL", "http://localhost:3000")

settings = Settings()

if os.getenv("ENVIRONMENT", "development").lower() == "production":
    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        raise ValueError("SECRET_KEY debe tener al menos 32 caracteres en producción por razones de seguridad.")

