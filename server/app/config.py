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
    llm_timeout_s: float = 90.0
    max_tool_rounds: int = 5

    supabase_url: str = ""
    supabase_service_key: str = ""

    history_messages: int = 20
    memory_hits: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
