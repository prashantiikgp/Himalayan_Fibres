"""Himalayan Fibers Email Marketing System - Main Application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.db.session import init_db

# Setup logging
setup_logging(debug=settings.debug)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Himalayan Fibers Email Marketing System")
    await init_db()
    logger.info("Database initialized")
    yield
    # Shutdown
    logger.info("Shutting down")


# Create FastAPI app
app = FastAPI(
    title="Himalayan Fibers Email Marketing",
    description="Email marketing automation system for Himalayan Fibers",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers — Email
from app.api.routes import webhooks, contacts, templates, campaigns, segments, content

app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(contacts.router, prefix="/api/v1")
app.include_router(templates.router, prefix="/api/v1")
app.include_router(campaigns.router, prefix="/api/v1")
app.include_router(segments.router, prefix="/api/v1")
app.include_router(content.router, prefix="/api/v1")

# Include routers — WhatsApp
from app.whatsapp.routes import router as wa_router
from app.whatsapp.webhook import router as wa_webhook_router

app.include_router(wa_router, prefix="/api/v1")
app.include_router(wa_webhook_router)  # No prefix — Meta requires /webhook/whatsapp


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Himalayan Fibers Email Marketing System",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
