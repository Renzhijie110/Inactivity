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
        import traceback
        traceback.print_exc()
        # Don't raise here, let the service start and handle errors in endpoints
        # This allows the service to start even if DB is temporarily unavailable
        pass


@app.on_event("shutdown")
async def shutdown():
    """Close database pool on shutdown."""
    await db.disconnect()


@app.get("/health")
async def health():
    """Health check endpoint for load balancer and monitoring."""
    health_status = {
        "status": "ok",
        "service": "FastAPI Backend",
        "database": "unknown"
    }
    
    # Check database connection
    try:
        pool = await db.get_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            health_status["database"] = "connected"
        else:
            health_status["database"] = "not_connected"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    return health_status
