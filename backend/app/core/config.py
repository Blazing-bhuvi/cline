"""Application configuration loaded from environment variables / .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/  directory (this file lives at backend/app/core/config.py)
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent

DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Voter ID Verification Prototype"
    environment: str = "development"
    debug: bool = False

    # Database
    database_url: str = f"sqlite:///{(DEFAULT_DATA_DIR / 'voter.db').as_posix()}"

    # Runtime artifacts
    upload_dir: str = str(DEFAULT_DATA_DIR / "uploads")
    model_dir: str = str(DEFAULT_DATA_DIR / "models")

    # Session & limits
    session_ttl_seconds: int = 1800
    max_upload_mb: int = 15
    allowed_image_types: str = "image/jpeg,image/png,image/webp"

    # CORS (comma separated)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # OCR
    ocr_min_confidence: float = 0.55
    ocr_engine: str = "rapidocr"

    # Face matching thresholds (cosine similarity)
    face_similarity_match: float = 0.45
    face_similarity_review: float = 0.30
    face_min_size_ratio: float = 0.12
    face_embedding_model: str = "face_recognition_sface_2021dec.onnx"

    # DB text matching
    name_similarity_threshold: float = 0.85

    # Demonstration mode (never claims authoritative issuer verification)
    demo_mode: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_image_type_list(self) -> list[str]:
        return [t.strip().lower() for t in self.allowed_image_types.split(",") if t.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
