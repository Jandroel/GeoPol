from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GEOPOL_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/geopol.db"
    storage_path: Path = Path("./data/storage")
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    env: str = "development"
    max_upload_bytes: int = 5 * 1024**3
    chunk_bytes: int = 8 * 1024**2
    catalog_bytes: int = 24 * 1024**2
    batch_size: int = 250
    lease_seconds: int = 240
    session_hours: int = 12


settings = Settings()
