from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jarvis_api_token: str = ""
    owner_name: str = "signore"
    timezone: str = "Europe/Rome"

    freellm_base_url: str = ""
    freellm_api_key: str = ""
    freellm_model: str = "auto"
    freellm_internal_url: str = ""  # se impostata, /v1/* viene inoltrato qui (FreeLLMAPI nello stesso container)
    freellm_db_path: str = ""  # se FREELLM_API_KEY è vuota, la chiave unificata si legge da questo DB SQLite
    llm_timeout_s: float = 90.0
    max_tool_rounds: int = 5

    supabase_url: str = ""
    supabase_service_key: str = ""

    telegram_bot_token: str = ""
    telegram_owner_id: int = 0
    telegram_webhook_secret: str = ""
    public_url: str = ""  # su Render viene da RENDER_EXTERNAL_URL
    render_external_url: str = ""
    reminder_poll_s: float = 30.0

    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""

    # origini delle app (Tauri su Windows, Capacitor su Android); altre, separate da virgola
    cors_origins: str = ""

    history_messages: int = 14
    memory_hits: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
