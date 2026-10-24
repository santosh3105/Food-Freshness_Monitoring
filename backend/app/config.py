import os
import logging
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

from dotenv import load_dotenv, dotenv_values

logger = logging.getLogger(__name__)

# ============================================================
# BASE PATHS
# ============================================================

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

# ============================================================
# ENVIRONMENT CONFIGURATION
# Primary configuration loaded from backend/.env when available,
# with seamless fallback to environment variables in Docker/Cloud.
# ============================================================

ENV_FILE = BACKEND_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    _env_values = dotenv_values(ENV_FILE)
else:
    load_dotenv()
    _env_values = {}


def _get_env(name: str, default: str = "") -> str:
    """Read a setting from backend/.env, then fall back to the process environment."""
    value = _env_values.get(name)

    if value is None or not str(value).strip():
        value = os.getenv(name, default)

    return str(value).strip().strip("\"'")


# ============================================================
# MONGODB URI VALIDATION & RESOLUTION
# ============================================================

def _get_mongo_uri() -> str:
    """Load MongoDB URI directly from backend/.env or environment variables."""
    env_file = BACKEND_DIR / ".env"
    env_values = dotenv_values(env_file) if env_file.exists() else {}

    uri = env_values.get("MONGO_URI") or os.getenv("MONGO_URI")

    if not uri:
        # Default local MongoDB connection
        uri = "mongodb://127.0.0.1:27017/food_freshness_db"

    uri = str(uri).strip().strip("\"'")

    if uri.startswith("MONGO_URI="):
        uri = uri[len("MONGO_URI="):].strip().strip("\"'")

    if "<" in uri or ">" in uri:
        raise ValueError(
            "The MONGO_URI still contains placeholder brackets. "
            "Please configure actual database credentials."
        )

    if ("127.0.0.1" not in uri and "localhost" not in uri and "mongo:" not in uri) and uri.startswith("mongodb+srv://"):
        if uri.count("@") != 1:
            raise ValueError(
                "MONGO_URI must contain exactly one '@' separator. "
                "Check the connection string."
            )

    if not uri.startswith(("mongodb://", "mongodb+srv://")):
        raise ValueError("Invalid MongoDB URI scheme.")

    return uri


# ============================================================
# APPLICATION SETTINGS
# ============================================================

class Settings:
    PROJECT_NAME: str = "Food Freshness Monitoring Platform"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api"

    # Environment
    ENVIRONMENT: str = _get_env("ENVIRONMENT", "development")
    DEBUG: bool = _get_env("DEBUG", "True").lower() in (
        "true",
        "1",
        "yes",
    )

    # Server
    HOST: str = _get_env("HOST", "127.0.0.1")
    PORT: int = int(_get_env("PORT", "9000"))

    # MongoDB
    MONGO_URI: str = _get_mongo_uri()
    DATABASE_NAME: str = _get_env(
        "DATABASE_NAME",
        "food_freshness_db",
    )

    # JWT Authentication
    JWT_SECRET: str = _get_env(
        "JWT_SECRET",
        "super_secret_food_freshness_monitoring_jwt_key_2026",
    )
    JWT_ALGORITHM: str = _get_env("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        _get_env("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
    )

    # Social Single Sign-On: Google
    GOOGLE_CLIENT_ID: str = _get_env("GOOGLE_CLIENT_ID", "")

    # CORS
    CORS_ORIGINS: str = _get_env("CORS_ORIGINS", "*")

    # Paths
    APP_DIR: Path = APP_DIR
    BACKEND_DIR: Path = BACKEND_DIR
    PROJECT_ROOT: Path = PROJECT_ROOT
    UPLOAD_DIR: Path = PROJECT_ROOT / "uploads"
    FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"
    DATASETS_DIR: Path = PROJECT_ROOT / "datasets"


# ============================================================
# INITIALIZE SETTINGS
# ============================================================

settings = Settings()

# Ensure required directories exist.
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.DATASETS_DIR.mkdir(parents=True, exist_ok=True)
