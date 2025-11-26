"""Configuration management for the application."""
import os
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings."""
    
    # Database
    postgres_url: Optional[str] = os.getenv("POSTGRES_URL")
    
    # External API
    external_api_base: str = os.getenv(
        "EXTERNAL_API_BASE",
        "https://noupdate.uniuni.site"
    )
    
    # Authentication
    default_username: str = os.getenv("DEFAULT_USERNAME", "admin")
    default_password: str = os.getenv("DEFAULT_PASSWORD", "40")
    
    # CORS
    cors_origins: List[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]
    
    # API
    api_timeout: float = 30.0


settings = Settings()

