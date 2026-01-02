"""
LinkedIn Qualifier v1 - FastAPI Application

Headless API for qualifying LinkedIn followers against client-specific ICPs.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import clients, batches

app = FastAPI(
    title="LinkedIn Qualifier API",
    description="Qualify LinkedIn followers against client-specific ICPs",
    version="1.0.0"
)

# CORS middleware (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "LinkedIn Qualifier API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Health check with database connection test."""
    from .services.supabase_client import test_connection
    
    db_ok = test_connection()
    
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected"
    }


# Include routers
app.include_router(clients.router, prefix="/clients", tags=["Clients"])
app.include_router(batches.router, prefix="/batches", tags=["Batches"])
