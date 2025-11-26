"""Main FastAPI application."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import db
from .routers import auth, proxy, consjob

app = FastAPI(
    title="FastAPI Application",
    description="A FastAPI application",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Include routers
app.include_router(auth.router)
app.include_router(proxy.router)
app.include_router(consjob.router)


@app.on_event("startup")
async def startup():
    """Initialize database pool on startup."""
    try:
        await db.connect()
        print("✅ Application startup completed")
    except Exception as e:
        print(f"❌ Application startup failed: {e}")
        # Don't raise here, let the service start and handle errors in endpoints
        pass


@app.on_event("shutdown")
async def shutdown():
    """Close database pool on shutdown."""
    await db.disconnect()


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
