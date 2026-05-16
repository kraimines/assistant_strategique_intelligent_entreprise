"""Application configuration — centralisé via pydantic-settings."""
from functools import lru_cache
from typing import List

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    app_name: str = "Talan Platform API"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Stocké comme str pour éviter que pydantic-settings v2 tente json.loads()
    # avant le validator sur les champs List[str].
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://localhost:5174,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:5174",
        alias="cors_origins",
        validation_alias=AliasChoices("cors_origins", "cors_origins_raw"),
    )

    @property
    def cors_origins(self) -> List[str]:  # type: ignore[override]
        """Parse CORS origins — accepte virgule ou JSON array."""
        import json as _json
        v = (self.cors_origins_raw or "").strip()
        if not v:
            return ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]
        if v.startswith("["):
            try:
                return _json.loads(v)
            except _json.JSONDecodeError:
                pass
        return [o.strip() for o in v.split(",") if o.strip()]

    # ── JWT ───────────────────────────────────────────────────────────────────
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ── PostgreSQL (3 bases de données) ───────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "talan"
    postgres_password: str = "talan_secret"
    postgres_db_hr: str = "talan_hr"
    postgres_db_crm: str = "talan_crm"
    postgres_db_erp: str = "talan_erp"

    def database_url(self, domain: str) -> str:
        """Retourne l'URL SQLAlchemy (psycopg2) pour le domaine donné (hr | crm | erp)."""
        db_map = {
            "hr":  self.postgres_db_hr,
            "crm": self.postgres_db_crm,
            "erp": self.postgres_db_erp,
        }
        db_name = db_map.get(domain)
        if not db_name:
            raise ValueError(f"Unknown domain '{domain}'. Must be one of {list(db_map)}")
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{db_name}"
        )

    def async_database_url(self, domain: str) -> str:
        """Retourne l'URL SQLAlchemy (asyncpg) pour le domaine donné (hr | crm | erp)."""
        db_map = {
            "hr":  self.postgres_db_hr,
            "crm": self.postgres_db_crm,
            "erp": self.postgres_db_erp,
        }
        db_name = db_map.get(domain)
        if not db_name:
            raise ValueError(f"Unknown domain '{domain}'. Must be one of {list(db_map)}")
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{db_name}"
        )

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "talan_neo4j"

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Google Generative AI ──────────────────────────────────────────────────
    # Accepte GOOGLE_API_KEY ou GEMINI_API_KEY indifféremment
    google_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("google_api_key", "gemini_api_key"),
    )
    gemini_model: str = "gemini-2.0-flash"
    gemini_temperature: float = 0.1
    gemini_max_tokens: int = 4096

    # ── LangSmith ─────────────────────────────────────────────────────────────
    # Accepte LANGSMITH_API_KEY ou LANGCHAIN_API_KEY
    langsmith_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("langsmith_api_key", "langchain_api_key"),
    )
    langsmith_project: str = Field(
        default="talan-enterprise-platform",
        validation_alias=AliasChoices("langsmith_project", "langchain_project"),
    )
    langchain_tracing_v2: bool = True

    # ── Groq (gratuit, 14 400 req/jour) ──────────────────────────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # ── Anthropic / Claude (structured tool-use extraction) ───────────────────
    # Optional — if set, the analyst uses Claude 3.5 Sonnet for superior extraction
    # fallback to Groq if not set
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("anthropic_api_key", "claude_api_key"),
    )
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # ── Mistral AI (second fallback — 256K context, 500K TPM, no daily cap) ───
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"

    # ── LLM provider actif : "gemini" | "groq" | "anthropic" ─────────────────
    llm_provider: str = "groq"

    # ── Providers par rôle (optimisation quota / performance) ─────────────────
    # json_llm_provider    : orchestrateur, analyst, scanner → JSON structuré
    # tool_llm_provider    : agents HR/CRM/ERP/market/competitive → tool calling
    # text_llm_provider    : email_agent, final_response → génération FR
    # explain_llm_provider : simulation — explications + recommandations Talan
    json_llm_provider:    str = "groq"
    tool_llm_provider:    str = "groq"
    text_llm_provider:    str = "gemini"
    explain_llm_provider: str = "groq"

    # ── ChromaDB ─────────────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"

    # ── SMTP (envoi d'emails) ─────────────────────────────────────────────────
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # ── Market Analysis Agent ─────────────────────────────────────────────────
    # NewsAPI (https://newsapi.org) — 100 req/day free
    newsapi_key: str = ""
    # GNews (https://gnews.io) — 100 req/day free
    gnews_key: str = ""
    # Alpha Vantage (https://www.alphavantage.co) — 25 req/day free (yfinance fallback)
    alpha_vantage_key: str = ""
    # Polygon.io (https://polygon.io) — market data (optional premium)
    polygon_key: str = ""
    # Slack webhook for critical alerts (optional)
    slack_webhook_url: str = ""
    # Pipeline interval in minutes (default 30)
    market_analysis_interval_minutes: int = 30
    # Alert threshold: talan_impact_score >= this value triggers an alert
    market_alert_threshold: float = 0.4
    # GNN model checkpoint path
    gnn_model_path: str = "./gnn_model.pt"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
