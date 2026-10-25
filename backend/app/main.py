import os
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response

from backend.app.config import settings
from backend.app.database import (
    connect_to_mongo,
    close_mongo_connection,
    get_database,
)
from backend.app.routes import (
    auth_routes,
    user_routes,
    inventory_routes,
    dashboard_routes,
    ai_routes,
    analytics_routes,
    report_routes,
    retailer_routes,
    inspector_routes,
    admin_routes,
    warehouse_routes,
    notification_routes,
)


# ============================================================
# LOGGING CONFIGURATION
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# APPLICATION LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize application resources.

    MongoDB connection failures are logged instead of being
    silently ignored. The application may start without MongoDB,
    but database-dependent operations will require a working
    database connection.
    """

    logger.info("Starting %s", settings.PROJECT_NAME)

    try:
        connect_to_mongo()
        logger.info("MongoDB initialization completed.")
    except Exception:
        logger.exception(
            "MongoDB initialization failed during application startup."
        )

    try:
        yield
    finally:
        logger.info("Shutting down %s", settings.PROJECT_NAME)

        try:
            close_mongo_connection()
            logger.info("MongoDB connection cleanup completed.")
        except Exception:
            logger.exception(
                "An error occurred while closing the MongoDB connection."
            )


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description=(
        "Production AI-Powered Food Freshness Monitoring Platform REST API. "
        "Includes Computer Vision Freshness Classification, "
        "Arrhenius Shelf-Life Kinetics, Prescriptive Storage "
        "Recommendations, Executive Analytics, and Compliance Reporting."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ============================================================
# CORS CONFIGURATION
# ============================================================

cors_origins_raw = getattr(
    settings,
    "CORS_ORIGINS",
    os.getenv("CORS_ORIGINS", "*"),
)

cors_origins = [
    origin.strip()
    for origin in cors_origins_raw.split(",")
    if origin.strip()
]

if not cors_origins:
    cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=(
        r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# VERCEL SERVERLESS ROUTING MIDDLEWARE
# ============================================================

@app.middleware("http")
async def vercel_routing_middleware(request: Request, call_next):
    """
    Ensure Vercel serverless executions preserve the intended request path.
    When Vercel rewrites or catches traffic through /api/index.py, the real requested path
    is passed in headers like 'x-matched-path', 'x-forwarded-uri', or 'x-real-path'.
    This middleware restores the original path in the ASGI scope so FastAPI's router
    matches /docs, /openapi.json, /health, /api/..., and frontend pages accurately.
    """
    scope = request.scope
    current_path = scope.get("path", "")

    if current_path in ("/api/index.py", "/api/index", "/api/index.py/", "/api/"):
        matched_path = (
            request.headers.get("x-forwarded-uri")
            or request.headers.get("x-original-url")
            or request.headers.get("x-rewrite-url")
            or request.headers.get("x-real-path")
            or request.headers.get("x-matched-path")
            or request.query_params.get("__path__")
        )
        if matched_path and matched_path not in ("/api/index.py", "/api/index", "/api/index.py/"):
            clean_path = matched_path.split("?")[0]
            if not clean_path.startswith("/"):
                clean_path = "/" + clean_path
            scope["path"] = clean_path
            scope["raw_path"] = clean_path.encode("utf-8")

    response = await call_next(request)
    return response


@app.get("/api/index.py", include_in_schema=False)
@app.get("/api/index", include_in_schema=False)
async def vercel_entrypoint_fallback():
    login_page = settings.FRONTEND_DIR / "login.html"
    if login_page.is_file():
        return FileResponse(login_page)
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "docs": "/docs",
        "openapi": "/openapi.json"
    }


# ============================================================
# GLOBAL DATABASE EXCEPTION HANDLERS
# ============================================================

@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    msg = str(exc)
    logger.error("RuntimeError intercepted on path %s: %s", request.url.path, msg)
    if "mongodb" in msg.lower() or "database" in msg.lower() or "atlas" in msg.lower():
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Database service unavailable. Please check MongoDB Atlas connection."
            },
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred."},
    )


# ============================================================
# UPLOADS DIRECTORY
# ============================================================

settings.UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

app.mount(
    "/uploads",
    StaticFiles(directory=str(settings.UPLOAD_DIR)),
    name="uploads",
)


# ============================================================
# API ROUTES
# ============================================================

api_prefix = settings.API_V1_PREFIX

all_routers = [
    auth_routes.router,
    user_routes.router,
    inventory_routes.router,
    dashboard_routes.router,
    ai_routes.router,
    analytics_routes.router,
    report_routes.router,
    retailer_routes.router,
    inspector_routes.router,
    admin_routes.router,
    warehouse_routes.router,
    notification_routes.router,
]

for r in all_routers:
    app.include_router(r, prefix=api_prefix)
    # Also support direct path without /api prefix (e.g. /auth/login)
    app.include_router(r, include_in_schema=False)


# ============================================================
# DATABASE STATUS HELPER
# ============================================================

def check_database_connection() -> bool:
    """
    Check MongoDB connectivity without exposing credentials.
    """

    try:
        db = get_database()

        if db is None:
            return False

        db.client.admin.command("ping")
        return True

    except Exception:
        logger.exception("MongoDB connectivity check failed.")
        return False


# ============================================================
# API DOCUMENTATION ALIASES (/api/docs & /api/openapi.json)
# ============================================================

@app.get(
    "/api/docs",
    include_in_schema=False,
    summary="Swagger UI documentation under /api prefix"
)
async def api_docs_swagger():
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"{settings.PROJECT_NAME} - Swagger UI",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )


@app.get(
    "/api/openapi.json",
    include_in_schema=False,
    summary="OpenAPI JSON specification under /api prefix"
)
async def api_openapi_specification():
    return app.openapi()


# ============================================================
# HEALTH CHECK ENDPOINTS
# ============================================================

@app.get(
    "/health",
    tags=["Operational Probes"],
    summary="Process Liveness Probe",
)
@app.get(
    "/api/health",
    tags=["Operational Probes"],
    include_in_schema=False,
)
async def health_liveness_check():
    """
    Check whether the application can respond to requests.

    A healthy application process does not necessarily mean
    that MongoDB is connected.
    """

    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get(
    "/ready",
    tags=["Operational Probes"],
    summary="Dependency Readiness Probe",
)
@app.get(
    "/api/ready",
    tags=["Operational Probes"],
    include_in_schema=False,
)
async def readiness_probe():
    """
    Check whether MongoDB is available.

    Returns HTTP 503 if the database is unavailable.
    """

    db_connected = check_database_connection()

    if not db_connected:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "database": "disconnected",
                "message": (
                    "MongoDB is unavailable. "
                    "Check the database configuration and connectivity."
                ),
            },
        )

    return {
        "status": "ready",
        "database": "connected",
        "models": {
            "cv_analyzer": "not_verified",
            "shelf_life_predictor": "not_verified",
            "recommendation_engine": "not_verified",
            "report_generator": "not_verified",
        },
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
    }


# ============================================================
# FRONTEND STATIC FILES AND ROUTING
# ============================================================

if settings.FRONTEND_DIR.exists():

    css_dir = settings.FRONTEND_DIR / "css"

    if css_dir.exists():
        app.mount(
            "/css",
            StaticFiles(directory=str(css_dir)),
            name="css",
        )

    js_dir = settings.FRONTEND_DIR / "js"

    if js_dir.exists():
        app.mount(
            "/js",
            StaticFiles(directory=str(js_dir)),
            name="js",
        )

    app.mount(
        "/static",
        StaticFiles(directory=str(settings.FRONTEND_DIR)),
        name="static",
    )

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return Response(
            status_code=status.HTTP_204_NO_CONTENT
        )

    @app.get(
        "/",
        tags=["Frontend"],
        include_in_schema=False,
    )
    async def serve_index():
        index_file = settings.FRONTEND_DIR / "index.html"

        if index_file.is_file():
            return FileResponse(index_file)

        return {
            "message": (
                "Food Freshness Platform API is running. "
                "Access /docs for interactive API documentation."
            )
        }

    page_names = [
        "index.html",
        "login.html",
        "register.html",
        "dashboard.html",
        "inventory.html",
        "add-food.html",
        "food-details.html",
        "profile.html",
        "executive-dashboard.html",
        "reports.html",
        "retailer-dashboard.html",
        "dashboard-inspector.html",
        "admin-dashboard.html",
        "warehouse-dashboard.html",
        "scan.html",
    ]

    def make_handler(page_name: str):
        async def page_handler():
            target = settings.FRONTEND_DIR / page_name

            if target.is_file():
                return FileResponse(target)

            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "detail": f"{page_name} not found"
                },
            )

        page_handler.__name__ = (
            "serve_" + page_name.replace(".", "_").replace("-", "_")
        )

        return page_handler

    for page in page_names:
        handler = make_handler(page)

        app.add_api_route(
            f"/{page}",
            handler,
            methods=["GET"],
            tags=["Frontend"],
            include_in_schema=False,
        )

        clean_name = page.removesuffix(".html")

        if clean_name != "index":
            app.add_api_route(
                f"/{clean_name}",
                handler,
                methods=["GET"],
                tags=["Frontend"],
                include_in_schema=False,
            )

else:
    logger.warning(
        "Frontend directory does not exist: %s",
        settings.FRONTEND_DIR,
    )


# ============================================================
# LOCAL DEVELOPMENT ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        reload_dirs=[str(settings.BACKEND_DIR)],
    )