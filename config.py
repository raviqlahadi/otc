from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # WhatsApp
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # PostgreSQL
    database_url: str = "postgresql://postgres:postgres@localhost:5432/option_tracing"

    # BKT defaults
    bkt_p_l0: float = 0.3
    bkt_p_guess: float = 0.25
    bkt_p_slip: float = 0.1
    bkt_p_transit: float = 0.1

    model_config = {"env_file": ".env", "env_prefix": ""}


settings = Settings()
