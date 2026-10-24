import os
import logging
from pathlib import Path

from dotenv import load_dotenv, dotenv_values

logger = logging.getLogger(__name__)

# ============================================================
# BASE PATHS
# ============================================================

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

IS_VERCEL = os.getenv("VERCEL", "").lower() in ("1", "true", "yes")

# ============================================================
# ENVIRONMENT CONFIGURATION
# ============================================================

ENV_FILE = BACKEND_DIR / ".env"

# Do not load a local .env file over Vercel's configuration.
if not IS_VERCEL and ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    _env_values = dotenv_values(ENV_FILE)
else:
    _env_values = {}


def _get_env(name: str, default: str = "") -> str:
    """
    Read environment variables.

    Process environment variables take priority over .env values.
    """

    value = os.getenv(name)

    if value is None or not str(value).strip():
        value = _env_values.get(name)

    if value is None or not str(value).strip():
        value = default

    return str(value).strip().strip("\"'")


# ============================================================
# MONGODB CONFIGURATION
# ============================================================

def _get_mongo_uri() -> str:
    """
    Resolve MongoDB URI from the deployment environment.

    Vercel must use a configured remote MongoDB connection.
    Local development can use localhost as a fallback.
    """

    uri = _get_env("MONGO_URI")

    if not uri:
        if IS_VERCEL:
            raise ValueError(
                "MONGO_URI is missing. Configure MONGO_URI in "
                "Vercel Project Settings > Environment Variables."
            )

        uri = "mongodb://127.0.0.1:27017/food_freshness_db"

    uri = uri.strip().strip("\"'")

    if uri.startswith("MONGO_URI="):
        uri = uri[len("MONGO_URI="):].strip().strip("\"'")

    if "<" in uri or ">" in uri:
        raise ValueError(
            "MONGO_URI contains placeholder characters. "
            "Configure the actual MongoDB connection string."
        )

    if not uri.startswith(("mongodb://", "mongodb+srv://")):
        raise ValueError(
            "Invalid MONGO_URI. It must begin with "
            "mongodb:// or mongodb+srv://."
        )

    if uri.startswith("mongodb+srv://") and uri.count("@") != 1:
        raise ValueError(
            "Invalid MongoDB Atlas URI. Check the username, "
            "password, and cluster hostname."
        )

    return uri


# ============================================================
# APPLICATION SETTINGS
# ============================================================

class Settings:
    PROJECT_NAME: str = "Food Freshness Monitoring Platform"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api"

    # Environment
    ENVIRONMENT: str = _get_env(
        "ENVIRONMENT",
        "production" if IS_VERCEL else "development",
    )

    DEBUG: bool = _get_env(
        "DEBUG",
        "False" if IS_VERCEL else "True",
    ).lower() in ("true", "1", "yes")

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
    JWT_SECRET: str = _get_env("JWT_SECRET")

    JWT_ALGORITHM: str = _get_env(
        "JWT_ALGORITHM",
        "HS256",
    )

    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        _get_env("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
    )

    # Google Sign-In
    GOOGLE_CLIENT_ID: str = _get_env(
        "GOOGLE_CLIENT_ID",
        "",
    )

    # CORS
    CORS_ORIGINS: str = _get_env(
        "CORS_ORIGINS",
        "*",
    )

    # Paths
    APP_DIR: Path = APP_DIR
    BACKEND_DIR: Path = BACKEND_DIR
    PROJECT_ROOT: Path = PROJECT_ROOT

    # Vercel's application directory is not a persistent writable
    # location. Use /tmp for files created at runtime.
    UPLOAD_DIR: Path = (
        Path("/tmp/food_freshness_uploads")
        if IS_VERCEL
        else PROJECT_ROOT / "uploads"
    )

    # Dataset files bundled with the project remain in the project.
    DATASETS_DIR: Path = PROJECT_ROOT / "datasets"


# ============================================================
# INITIALIZE SETTINGS
# ============================================================

settings = Settings()

if not settings.DATABASE_NAME:
    raise ValueError("DATABASE_NAME must not be empty.")

# Do not silently use an insecure JWT secret in production.
if IS_VERCEL and (
    not settings.JWT_SECRET
    or len(settings.JWT_SECRET) < 32
    or settings.JWT_SECRET
    == "super_secret_food_freshness_monitoring_jwt_key_2026"
):
    raise ValueError(
        "JWT_SECRET is missing or insecure. Configure a strong "
        "JWT_SECRET in Vercel Environment Variables."
    )

# Create writable runtime directories.
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Create the datasets directory only in local development.
# On Vercel, the deployed application directory may be read-only.
if not IS_VERCEL:
    settings.DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    