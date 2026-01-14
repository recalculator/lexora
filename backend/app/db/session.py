"""Database session management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

def ensure_sslmode(database_url: str) -> str:
    """Ensure sslmode=require is present for Railway Postgres."""
    if not database_url or "postgresql" not in database_url.lower():
        return database_url
    
    # Check if sslmode is already present
    if "sslmode" in database_url.lower():
        return database_url
    
    # Parse URL and add sslmode=require
    parsed = urlparse(database_url)
    query_params = parse_qs(parsed.query)
    query_params['sslmode'] = ['require']
    new_query = urlencode(query_params, doseq=True)
    new_parsed = parsed._replace(query=new_query)
    return urlunparse(new_parsed)

# Ensure Railway Postgres SSL mode
db_url = ensure_sslmode(settings.database_url)

engine = create_engine(
    db_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
