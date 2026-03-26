"""Application configuration — centralisé via pydantic-settings."""
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: object) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v  # type: ignore[return-value]

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
        """Retourne l'URL SQLAlchemy pour le domaine donné (hr | crm | erp)."""
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

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "talan_neo4j"

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Google Generative AI ──────────────────────────────────────────────────
    google_api_key: str = ""

    # ── ChromaDB ─────────────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
