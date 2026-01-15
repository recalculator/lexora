"""FastAPI application main."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import RequestIDMiddleware, get_logger
from app.api import routes

logger = get_logger()

app = FastAPI(
    title="Lexora API",
    description="Legal Contract Analysis Platform API",
    version="1.0.0",
)

# Add CORS middleware
# Allow localhost origins for dev and all Vercel preview + prod URLs
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,  # localhost origins for dev
    allow_origin_regex="https://.*\\.vercel\\.app",  # All Vercel preview and prod URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request ID middleware
app.add_middleware(RequestIDMiddleware)

# Include routers
app.include_router(routes.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Lexora API",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
