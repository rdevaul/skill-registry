from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.storage import LocalStorageBackend, S3StorageBackend
from app.routers import identities, skills, admin, stats
from app.auth import require_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Initialize storage backend
    if settings.REGISTRY_STORAGE_BACKEND == "local":
        storage = LocalStorageBackend(settings.REGISTRY_DATA_DIR)
    elif settings.REGISTRY_STORAGE_BACKEND == "s3":
        storage = S3StorageBackend(settings.AWS_BUCKET_NAME, settings.AWS_REGION)
    else:
        raise ValueError(f"Unknown storage backend: {settings.REGISTRY_STORAGE_BACKEND}")

    # Load state into app.state
    app.state.storage = storage
    app.state.registry_state = storage.load_state()

    yield

    # Cleanup (if needed)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.REGISTRY_TITLE,
        description="A registry server for cryptographically signed AI agent skills",
        version="0.1.0",
        lifespan=lifespan
    )

    # Include routers
    app.include_router(identities.router)
    app.include_router(skills.router)
    app.include_router(admin.router)
    app.include_router(stats.router)

    # Setup templates and static files (create directories if they don't exist)
    import os
    os.makedirs("app/templates", exist_ok=True)
    os.makedirs("app/static", exist_ok=True)

    templates = Jinja2Templates(directory="app/templates")

    # Mount static files
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """Render homepage."""
        state = request.app.state.registry_state

        # Get stats
        approved_signers = [
            identity for identity in state.identities.values()
            if identity.status == "approved"
        ]
        skills_list = list(state.skills.values())

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "title": settings.REGISTRY_TITLE,
                "base_url": settings.REGISTRY_BASE_URL,
                "approved_signers": approved_signers,
                "skills": skills_list,
                "stats": {
                    "approved_signers": len(approved_signers),
                    "published_skills": len(skills_list),
                }
            }
        )

    @app.get("/admin/dashboard", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
    async def admin_dashboard(request: Request):
        """Render admin dashboard."""
        state = request.app.state.registry_state

        pending_identities = [
            identity for identity in state.identities.values()
            if identity.status == "pending"
        ]

        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={
                "title": f"Admin Dashboard - {settings.REGISTRY_TITLE}",
                "pending_identities": pending_identities,
            }
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        """Custom 404 handler."""
        return JSONResponse(
            status_code=404,
            content={"detail": "Not found"}
        )

    return app


app = create_app()
