from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jarvis_api_token: str = ""
    encryption_key: str = ""  # la stessa di FreeLLMAPI: da qui si ricava la password del suo account interno
    owner_name: str = "signore"
    timezone: str = "Europe/Rome"

    freellm_base_url: str = ""
    freellm_api_key: str = ""
    freellm_model: str = "auto"
    freellm_internal_url: str = ""  # se impostata, /v1/* viene inoltrato qui (FreeLLMAPI nello stesso container)
    freellm_db_path: str = ""  # se FREELLM_API_KEY è vuota, la chiave unificata si legge da questo DB SQLite
    llm_timeout_s: float = 90.0
    llm_attempt_timeout_s: float = 35.0
    llm_routing: bool = True  # profili auto:fast/smart/reliable/balanced scelti per tipo di richiesta (solo con modello «auto»)
    web_search_engines: bool = True  # ricerca web dai motori di FreeLLMAPI (Parallel); DuckDuckGo come ripiego  # primo tentativo: se il provider non risponde in tempo si ripiega su un altro modello (invece di aspettare 60 s)
    llm_temperature: float = 0.6
    llm_temperature_tools: float = 0.2  # con i tool serve precisione, non creatività
    llm_max_tokens: int = 1500  # tetto per risposta: protegge la quota gratuita
    stt_model: str = "auto"  # trascrizione dei vocali (FreeLLMAPI /v1/audio/transcriptions)
    history_chars: int = 7000  # budget della cronologia inviata al modello (le conversazioni lunghe si accorciano dalle più vecchie)
    github_repo: str = "xX-VyrnCore-Xx/jarvis-assistant"  # da dove le app scaricano gli aggiornamenti
    github_webhook_secret: str = ""  # facoltativo: notifica istantanea alla pubblicazione di una Release
    update_check_minutes: int = 30
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

    firebase_service_account_json: str = ""  # JSON dell'account di servizio Firebase (push Android)
    low_tokens_alert: int = 5_000_000  # avviso quando i token residui scendono sotto questa soglia (0 = off)

    freeapi_db_backup_url: str = ""  # dataset HF di FreeLLMAPI: da qui si ricava anche dove salvare il backup di Supabase
    freeapi_db_backup_token: str = ""
    hf_backup_keep: int = 14

    # origini delle app (Tauri su Windows, Capacitor su Android); altre, separate da virgola
    cors_origins: str = ""

    privacy_mode: str = "standard"  # off | standard (IBAN, carte, chiavi, password, CF) | strict (anche email e telefoni): mascherati verso i modelli
    # secondo cervello (RAG)
    rag_enabled: bool = True
    rag_embed_model: str = "bge-m3"  # famiglia di embedding di FreeLLMAPI (multilingue, 1024 dimensioni); 'auto' = predefinita del router
    rag_context_chars: int = 1800  # quanto contesto del secondo cervello entra in ogni risposta
    rag_min_cosine: float = 0.35  # sotto questa somiglianza (e senza parole in comune) un frammento non entra nel contesto
    rag_enrich_per_cycle: int = 2  # documenti arricchiti (titolo, riassunto, tag, entità) ogni ciclo; 0 = spento
    telegram_mode: str = "auto"  # auto | webhook | polling: webhook se c'è un indirizzo pubblico, altrimenti lettura diretta
    github_token: str = ""  # GITHUB_TOKEN: token classico con scope repo (+workflow) per le sessioni di coding; senza, la funzione è spenta
    coding_repos_per_day: int = 3  # repository nuovi che JARVIS può creare ogni giorno
    live_news: bool = True  # notizie in tempo reale dai feed RSS/Atom e salvataggio periodico nel secondo cervello
    live_ingest_minutes: int = 20
    live_news_per_cycle: int = 20
    knowledge_refresh_per_day: int = 5  # voci di base riscaricate ogni giorno (a rotazione) per tenerle aggiornate
    knowledge_seed_per_cycle: int = 3  # voci di base di Wikipedia caricate ogni 5 minuti nel secondo cervello (0 = spento)
    skills_enabled: bool = True  # competenze specialistiche (programmazione, finanza, marketing...) attivate dalla richiesta
    skills_max_active: int = 2
    skills_context_chars: int = 3000
    reminder_calendar_popup: bool = True  # l'evento del Calendario avvisa anche da solo (notifica di Google Calendar) oltre ai canali di JARVIS
    learn_enabled: bool = True  # impara da solo fatti, preferenze e impegni dalle conversazioni (poi li salva nel secondo cervello)
    learn_max_per_day: int = 30
    proactive_enabled: bool = True  # JARVIS ti avvisa da solo: eventi in arrivo, email nuove, riepilogo serale e settimanale
    proactive_max_per_day: int = 6  # tetto agli avvisi non urgenti (gli eventi imminenti non contano)
    evening_hour: int = 21  # ora del riepilogo serale (0 = spento)
    profile_refresh_days: int = 7
    briefing_hour: int = 8  # ora del buongiorno automatico (0 = spento)
    chat_per_minute: int = 20
    auth_fail_limit: int = 8
    auth_lock_s: int = 900
    pending_ttl_s: int = 600

    history_messages: int = 14
    memory_hits: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
