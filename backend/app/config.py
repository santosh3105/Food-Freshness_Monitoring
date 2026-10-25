
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

def _resolve_frontend_dir() -> Path:
    candidates = [
        PROJECT_ROOT / "frontend",
        BACKEND_DIR.parent / "frontend",
        Path.cwd() / "frontend",
        Path("/var/task/frontend"),
        Path(__file__).resolve().parents[2] / "frontend",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return PROJECT_ROOT / "frontend"

FRONTEND_DIR: Path = _resolve_frontend_dir()

IS_VERCEL = os.getenv("VERCEL", "").lower() in ("1", "true", "yes")

# ============================================================
# ENVIRONMENT CONFIGURATION
# ============================================================

ENV_FILE = BACKEND_DIR / ".env"

# Do not load local .env values over Vercel environment variables.
if not IS_VERCEL and ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    _env_values = dotenv_values(ENV_FILE)
else:
    _env_values = {}


def _get_env(name: str, default: str = "") -> str:
    """
    Read configuration values.

    Priority:
    1. Process environment variables
    2. Local .env values
    3. Default value
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
    Resolve the MongoDB connection URI.

    Vercel requires a configured remote database.
    Local development can use MongoDB on localhost.
    """

    uri = _get_env("MONGO_URI")

    if not uri:
        if IS_VERCEL:
            logger.error(
                "MONGO_URI is missing in Vercel Environment Variables. "
                "Configure MONGO_URI in Vercel Project Settings > Environment Variables."
            )
            return ""

        uri = "mongodb://127.0.0.1:27017/food_freshness_db"

    uri = uri.strip().strip("\"'")

    if uri.startswith("MONGO_URI="):
        uri = uri[len("MONGO_URI="):].strip().strip("\"'")

    if "<" in uri or ">" in uri:
        if IS_VERCEL:
            logger.error(
                "MONGO_URI contains placeholder characters '<' or '>'. "
                "Update Vercel Environment Variables with actual Atlas credentials."
            )
            return ""
        raise ValueError(
            "MONGO_URI contains placeholder characters. "
            "Configure the actual MongoDB connection string."
        )

    if not uri.startswith(("mongodb://", "mongodb+srv://")):
        if IS_VERCEL:
            logger.error(
                "Invalid MONGO_URI scheme. It must begin with mongodb:// or mongodb+srv://."
            )
            return ""
        raise ValueError(
            "Invalid MONGO_URI. It must begin with "
            "mongodb:// or mongodb+srv://."
        )

    if uri.startswith("mongodb+srv://") and uri.count("@") != 1:
        if IS_VERCEL:
            logger.error(
                "Invalid MongoDB Atlas URI. Check the username, password, and cluster hostname."
            )
            return ""
        raise ValueError(
            "Invalid MongoDB Atlas URI. Check the username, "
            "password, and cluster hostname."
        )

    return uri


# ============================================================
# APPLICATION SETTINGS
# ============================================================

class Settings:
    # --------------------------------------------------------
    # Application
    # --------------------------------------------------------

    PROJECT_NAME: str = "Food Freshness Monitoring Platform"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api"

    # --------------------------------------------------------
    # Environment
    # --------------------------------------------------------

    ENVIRONMENT: str = _get_env(
        "ENVIRONMENT",
        "production" if IS_VERCEL else "development",
    )

    DEBUG: bool = _get_env(
        "DEBUG",
        "False" if IS_VERCEL else "True",
    ).lower() in ("true", "1", "yes")

    # --------------------------------------------------------
    # Server
    # --------------------------------------------------------

    HOST: str = _get_env("HOST", "127.0.0.1")
    PORT: int = int(_get_env("PORT", "9000"))

    # --------------------------------------------------------
    # Database
    # --------------------------------------------------------

    MONGO_URI: str = _get_mongo_uri()

    DATABASE_NAME: str = _get_env(
        "DATABASE_NAME",
        "food_freshness_db",
    )

    # --------------------------------------------------------
    # JWT Authentication
    # --------------------------------------------------------

    JWT_SECRET: str = _get_env("JWT_SECRET")

    JWT_ALGORITHM: str = _get_env(
        "JWT_ALGORITHM",
        "HS256",
    )

    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        _get_env("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
    )

    # --------------------------------------------------------
    # Google Sign-In
    # --------------------------------------------------------

    GOOGLE_CLIENT_ID: str = _get_env(
        "GOOGLE_CLIENT_ID",
        "",
    )

    # --------------------------------------------------------
    # CORS
    # --------------------------------------------------------

    CORS_ORIGINS: str = _get_env(
        "CORS_ORIGINS",
        "*",
    )

    # --------------------------------------------------------
    # Project Paths
    # --------------------------------------------------------

    APP_DIR: Path = APP_DIR
    BACKEND_DIR: Path = BACKEND_DIR
    PROJECT_ROOT: Path = PROJECT_ROOT
    FRONTEND_DIR: Path = FRONTEND_DIR

    # --------------------------------------------------------
    # Uploads
    # --------------------------------------------------------
    # Vercel's application filesystem should not be used for
    # persistent uploads. Use /tmp for temporary runtime files.
    # Local development uses the project's uploads directory.

    UPLOAD_DIR: Path = (
        Path("/tmp/food_freshness_uploads")
        if IS_VERCEL
        else PROJECT_ROOT / "uploads"
    )

    # --------------------------------------------------------
    # Datasets
    # --------------------------------------------------------
    # Dataset files bundled with the project remain under the
    # project root. They should be deployed with the code.

    DATASETS_DIR: Path = PROJECT_ROOT / "datasets"


# ============================================================
# INITIALIZE SETTINGS
# ============================================================

settings = Settings()

if not settings.DATABASE_NAME:
    raise ValueError("DATABASE_NAME must not be empty.")


# ============================================================
# PRODUCTION SECURITY VALIDATION
# ============================================================

DEFAULT_INSECURE_JWT_SECRET = (
    "super_secret_food_freshness_monitoring_jwt_key_2026"
)

if IS_VERCEL:
    if (
        not settings.JWT_SECRET
        or len(settings.JWT_SECRET) < 32
        or settings.JWT_SECRET == DEFAULT_INSECURE_JWT_SECRET
    ):
        logger.warning(
            "JWT_SECRET is unconfigured or insecure in Vercel Environment Variables. "
            "Configure a 32+ character JWT_SECRET in Vercel Project Settings."
        )


# ============================================================
# DIRECTORY INITIALIZATION
# ============================================================

try:
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if not IS_VERCEL:
        settings.DATASETS_DIR.mkdir(parents=True, exist_ok=True)

except OSError as exc:
    logger.warning(
        "Could not initialize an application directory: %s",
        exc,
    )