
"""
MongoDB Atlas connection and collection helpers.

Designed for:
- Local development
- Vercel serverless deployment
- MongoDB Atlas
- Safe TLS certificate verification
- Database index initialization
"""

import logging
import os
import time
from typing import Optional

import certifi
from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError

from backend.app.config import settings

logger = logging.getLogger(__name__)

client: Optional[MongoClient] = None
db = None


# ============================================================
# CONFIGURATION
# ============================================================

CONNECTION_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1

SERVER_SELECTION_TIMEOUT_MS = 5000
CONNECT_TIMEOUT_MS = 5000
SOCKET_TIMEOUT_MS = 10000


# ============================================================
# ENVIRONMENT HELPERS
# ============================================================

def _is_vercel_environment() -> bool:
    """Return True when running in the Vercel environment."""
    return bool(os.getenv("VERCEL"))


def _is_local_mongodb(uri: str) -> bool:
    """Identify a MongoDB URI pointing to a local development server."""
    uri = uri.lower()

    return (
        "127.0.0.1" in uri
        or "localhost" in uri
        or "mongodb://mongo:" in uri
    )


# ============================================================
# MONGODB CONNECTION
# ============================================================

def connect_to_mongo() -> bool:
    """
    Connect to MongoDB using application settings.

    On Vercel, a missing or unreachable Atlas connection never
    triggers a fallback to localhost.

    Returns:
        True if the database connection succeeds.
        False if the connection cannot be established.
    """
    global client, db

    mongo_uri = getattr(settings, "MONGO_URI", None)
    database_name = getattr(settings, "DATABASE_NAME", None)

    # --------------------------------------------------------
    # Validate configuration
    # --------------------------------------------------------

    if not mongo_uri or not str(mongo_uri).strip():
        logger.error("MONGO_URI is not configured.")
        return False

    if not database_name or not str(database_name).strip():
        logger.error("DATABASE_NAME is not configured.")
        return False

    mongo_uri = str(mongo_uri).strip()
    database_name = str(database_name).strip()

    if not mongo_uri.startswith(("mongodb://", "mongodb+srv://")):
        logger.error(
            "Invalid MongoDB URI scheme. Expected mongodb:// "
            "or mongodb+srv://."
        )
        return False

    # Prevent accidental local database use in production.
    if _is_vercel_environment() and _is_local_mongodb(mongo_uri):
        logger.error(
            "Production configuration points to local MongoDB. "
            "Set MONGO_URI to your MongoDB Atlas connection string "
            "in Vercel Environment Variables."
        )
        return False

    # --------------------------------------------------------
    # Reuse a healthy existing connection
    # --------------------------------------------------------

    if client is not None and db is not None:
        try:
            client.admin.command("ping")
            logger.debug("Existing MongoDB connection is healthy.")
            return True

        except PyMongoError:
            logger.warning(
                "Existing MongoDB connection is unavailable. "
                "Attempting to reconnect."
            )

            try:
                client.close()
            except Exception:
                logger.debug(
                    "Error closing stale MongoDB client.",
                    exc_info=True,
                )

            client = None
            db = None

    # --------------------------------------------------------
    # Configure MongoDB client
    # --------------------------------------------------------

    is_tls = (
        mongo_uri.startswith("mongodb+srv://")
        or "tls=true" in mongo_uri.lower()
        or "ssl=true" in mongo_uri.lower()
    )

    client_kwargs = {
        "serverSelectionTimeoutMS": SERVER_SELECTION_TIMEOUT_MS,
        "connectTimeoutMS": CONNECT_TIMEOUT_MS,
        "socketTimeoutMS": SOCKET_TIMEOUT_MS,
        "retryWrites": True,
        "appname": "FoodFreshnessMonitoringPlatform",
    }

    # Use a trusted CA bundle when TLS is enabled.
    # Do not disable certificate validation.
    if is_tls:
        client_kwargs["tlsCAFile"] = certifi.where()

    logger.info(
        "Connecting to MongoDB database '%s'. Environment: %s",
        database_name,
        "Vercel" if _is_vercel_environment() else "local/development",
    )

    new_client = None
    last_error = None

    # --------------------------------------------------------
    # Attempt connection
    # --------------------------------------------------------

    for attempt in range(1, CONNECTION_ATTEMPTS + 1):
        try:
            new_client = MongoClient(mongo_uri, **client_kwargs)

            # MongoClient is lazy; ping verifies actual connectivity.
            new_client.admin.command("ping")

            # Set the globals before initializing indexes because
            # init_indexes() uses get_database().
            client = new_client
            db = client[database_name]

            logger.info(
                "Successfully connected to MongoDB database '%s'.",
                database_name,
            )

            # Index initialization is separate from connectivity.
            try:
                init_indexes()
            except Exception:
                logger.exception(
                    "MongoDB is connected, but index initialization "
                    "failed. Review the index definitions and database "
                    "permissions."
                )

            return True

        except Exception as exc:
            last_error = exc

            logger.error(
                "MongoDB connection attempt %s/%s failed. "
                "Error type: %s. Message: %s",
                attempt,
                CONNECTION_ATTEMPTS,
                type(exc).__name__,
                exc,
            )

            if new_client is not None:
                try:
                    new_client.close()
                except Exception:
                    logger.debug(
                        "Error closing unsuccessful MongoDB client.",
                        exc_info=True,
                    )

            new_client = None
            client = None
            db = None

            if attempt < CONNECTION_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

    # --------------------------------------------------------
    # Connection failed
    # --------------------------------------------------------

    if last_error is not None:
        logger.error(
            "Unable to connect to the configured MongoDB database "
            "after %s attempts. Error type: %s.",
            CONNECTION_ATTEMPTS,
            type(last_error).__name__,
        )

        if _is_vercel_environment():
            logger.error(
                "Vercel MongoDB troubleshooting: verify MONGO_URI, "
                "DATABASE_NAME, Atlas database-user credentials, "
                "Atlas Network Access, cluster availability, and DNS."
            )

    client = None
    db = None

    # Deliberately do not fall back to localhost.
    return False


# ============================================================
# CLOSE CONNECTION
# ============================================================

def close_mongo_connection() -> None:
    """Close the MongoDB client and clear the global references."""
    global client, db

    if client is not None:
        try:
            client.close()
            logger.info("MongoDB client closed.")

        except Exception:
            logger.exception("Error closing MongoDB client.")

        finally:
            client = None
            db = None


# ============================================================
# DATABASE ACCESS
# ============================================================

def get_database():
    """
    Return the connected database.

    Attempts to establish a connection if one is not available.
    Raises RuntimeError if the database cannot be reached.
    """
    global db

    if db is not None:
        return db

    if not connect_to_mongo():
        raise RuntimeError(
            "MongoDB is unavailable. Check MONGO_URI, DATABASE_NAME, "
            "Atlas network access, credentials, DNS, TLS, and logs."
        )

    if db is None:
        raise RuntimeError(
            "MongoDB connection was reported successful, "
            "but the database handle is unavailable."
        )

    return db


# ============================================================
# INDEX INITIALIZATION
# ============================================================

def init_indexes() -> None:
    """Create required indexes and validate existing index options."""

    # connect_to_mongo() assigns db before calling init_indexes().
    # Therefore this does not trigger a recursive connection attempt.
    database = db

    if database is None:
        raise RuntimeError(
            "Cannot initialize indexes before MongoDB is connected."
        )

    index_definitions = {
        "users": [
            ([("email", ASCENDING)], {"unique": True}),
            ([("role", ASCENDING)], {}),
            ([("status", ASCENDING)], {}),
            ([("is_active", ASCENDING)], {}),
            ([("google_id", ASCENDING)], {"sparse": True}),
        ],
        "inventory": [
            ([("user_id", ASCENDING)], {}),
            ([("category", ASCENDING)], {}),
            ([("expiry_date", ASCENDING)], {}),
        ],
        "freshness_records": [
            ([("inventory_id", ASCENDING)], {}),
        ],
        "storage_conditions": [
            ([("inventory_id", ASCENDING)], {}),
        ],
        "alerts": [
            ([("user_id", ASCENDING)], {}),
            ([("inventory_id", ASCENDING)], {}),
            ([("status", ASCENDING)], {}),
        ],
        "notifications": [
            ([("user_id", ASCENDING)], {}),
            ([("is_read", ASCENDING)], {}),
        ],
        "food_inspections": [
            ([("inspector_id", ASCENDING)], {}),
            ([("inspection_id", ASCENDING)], {"unique": True}),
            ([("status", ASCENDING)], {}),
            ([("category", ASCENDING)], {}),
            ([("created_at", ASCENDING)], {}),
        ],
        "audit_logs": [
            ([("timestamp", ASCENDING)], {}),
            ([("action", ASCENDING)], {}),
            ([("actor_id", ASCENDING)], {}),
            ([("target_id", ASCENDING)], {}),
        ],
        "storage_rules": [
            ([("category", ASCENDING)], {"unique": True}),
        ],
        "storage_zones": [
            ([("zone_id", ASCENDING)], {"unique": True}),
            ([("category", ASCENDING)], {}),
            ([("status", ASCENDING)], {}),
        ],
        "storage_readings": [
            (
                [
                    ("zone_id", ASCENDING),
                    ("recorded_at", ASCENDING),
                ],
                {},
            ),
            ([("recorded_at", ASCENDING)], {}),
        ],
        "temperature_rules": [
            ([("rule_id", ASCENDING)], {"unique": True}),
            (
                [
                    ("category", ASCENDING),
                    ("product_name", ASCENDING),
                ],
                {},
            ),
        ],
        "temperature_commands": [
            ([("command_id", ASCENDING)], {"unique": True}),
            (
                [
                    ("zone_id", ASCENDING),
                    ("created_at", ASCENDING),
                ],
                {},
            ),
            ([("status", ASCENDING)], {}),
        ],
    }

    for collection_name, indexes in index_definitions.items():
        collection = database[collection_name]

        try:
            existing_indexes = collection.index_information()

        except PyMongoError:
            logger.exception(
                "Could not read indexes for collection '%s'.",
                collection_name,
            )
            raise

        for keys, options in indexes:
            expected_keys = list(keys)
            expected_unique = options.get("unique", False)
            expected_sparse = options.get("sparse", False)

            existing = next(
                (
                    index_info
                    for index_info in existing_indexes.values()
                    if list(index_info.get("key", [])) == expected_keys
                ),
                None,
            )

            if existing is not None:
                existing_unique = existing.get("unique", False)
                existing_sparse = existing.get("sparse", False)

                if (
                    existing_unique != expected_unique
                    or existing_sparse != expected_sparse
                ):
                    raise RuntimeError(
                        f"Index configuration conflict in collection "
                        f"'{collection_name}' for keys {expected_keys}. "
                        f"Existing unique={existing_unique}, "
                        f"expected unique={expected_unique}; "
                        f"existing sparse={existing_sparse}, "
                        f"expected sparse={expected_sparse}. "
                        "Review the existing index before changing it."
                    )

                logger.debug(
                    "Index already exists for '%s': %s",
                    collection_name,
                    expected_keys,
                )
                continue

            try:
                collection.create_index(keys, **options)

                logger.info(
                    "Created index for '%s': %s",
                    collection_name,
                    expected_keys,
                )

            except PyMongoError:
                logger.exception(
                    "Failed to create index for collection '%s', "
                    "keys=%s",
                    collection_name,
                    expected_keys,
                )
                raise

    logger.info("MongoDB indexes initialized successfully.")


# ============================================================
# COLLECTION HELPERS
# ============================================================

def get_users_collection():
    return get_database()["users"]


def get_inventory_collection():
    return get_database()["inventory"]


def get_freshness_records_collection():
    return get_database()["freshness_records"]


def get_storage_conditions_collection():
    return get_database()["storage_conditions"]


def get_alerts_collection():
    return get_database()["alerts"]


def get_notifications_collection():
    return get_database()["notifications"]


def get_food_inspections_collection():
    return get_database()["food_inspections"]


def get_audit_logs_collection():
    return get_database()["audit_logs"]


def get_storage_rules_collection():
    return get_database()["storage_rules"]


def get_system_config_collection():
    return get_database()["system_config"]


def get_storage_zones_collection():
    return get_database()["storage_zones"]


def get_storage_readings_collection():
    return get_database()["storage_readings"]


def get_temperature_rules_collection():
    return get_database()["temperature_rules"]


def get_temperature_commands_collection():
    return get_database()["temperature_commands"]
