"""All settings in one place, read from environment variables or a .env file.

Every variable is prefixed with MERIDIAN_, e.g. MERIDIAN_DB_URL. Defaults match
docker-compose.yml so `make up && make ingest` works with no extra setup.
"""

from datetime import datetime
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MERIDIAN_", env_file=".env", extra="ignore")

    # Landing/staging database written by the ingestion pipeline.
    db_url: str = "mysql+pymysql://meridian:meridian@127.0.0.1:3306/meridian_landing"
    # Trusted system of record seeded from the course SQL pack (read-only for us).
    trusted_db_url: str = "mysql+pymysql://meridian:meridian@127.0.0.1:3306/meridian_retail"

    # Floci (local AWS). Set to empty to talk to real AWS later.
    aws_endpoint_url: str | None = "http://localhost:4566"
    aws_region: str = "us-east-1"
    landing_bucket: str = "meridian-landing"
    # Only used when aws_endpoint_url is set (Floci accepts anything non-empty).
    # Against real AWS, leave the endpoint empty and boto3 uses your normal AWS profile.
    local_aws_key: str = "test"
    local_aws_secret: str = "test"

    # Fixed "now" so every run of the same files gives the same answer (Class 5 idea).
    run_at: datetime = datetime.fromisoformat("2026-09-18T10:30:00+00:00")
    freshness_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
