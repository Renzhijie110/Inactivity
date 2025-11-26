"""Authentication and authorization utilities."""
import secrets
from typing import Dict
from fastapi import HTTPException, Header, status
from .config import settings


# Simple token storage (in-memory)
# In production, this should be stored in Redis or a database
valid_tokens: Dict[str, str] = {}  # token -> username


def create_token(username: str) -> str:
    """Create a random token for the user."""
    token = secrets.token_urlsafe(32)
    valid_tokens[token] = username
    return token


async def get_current_user(authorization: str = Header(None)) -> str:
    """Verify token and get current user."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证token"
        )
    
    # Support "Bearer token" or just "token"
    token = authorization.replace("Bearer ", "").strip()
    
    if token not in valid_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的token"
        )
    
    return valid_tokens[token]


def verify_credentials(username: str, password: str) -> bool:
    """Verify user credentials."""
    # Special case: convert uni_staff/123456 to default credentials
    if username == "uni_staff" and password == "123456":
        username = settings.default_username
        password = settings.default_password
    
    return (
        username == settings.default_username and
        password == settings.default_password
    )

