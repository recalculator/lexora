"""Application configuration using Pydantic settings."""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings."""
    
    # Database
    database_url: str = "postgresql://lexora:lexora123@postgres:5432/lexora"  # Default for local dev only
    
    # Redis
    redis_url: str = "redis://redis:6379/0"  # Default for local dev only
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = int(os.getenv("PORT", "8000"))  # Railway sets PORT env var
    
    # LLM
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    
    # Model paths
    model_path: str = "/app/models/clause_risknet.onnx"
    calibration_path: str = "/app/models/calibration.json"
    sklearn_model_dir: str = "/app/models/sklearn"
    
    # Storage
    storage_path: str = "/app/storage"
    max_upload_size: int = 10485760  # 10MB
    
    # Logging
    log_level: str = "INFO"
    enable_prompt_logging: bool = True
    
    # Security
    secret_key: str = "dev-secret-key-change-in-production"
    cors_origins: str = "http://localhost:3000,http://localhost:3001,http://localhost:3002"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
