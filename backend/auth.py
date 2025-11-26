"""Authentication and authorization utilities."""
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from fastapi import HTTPException, Header, status
from .config import settings


# Simple token storage (in-memory)
# In production, this should be stored in Redis or a database
valid_tokens: Dict[str, str] = {}  # token -> username
external_api_tokens: Dict[str, str] = {}  # local_token -> external_api_token
token_timestamps: Dict[str, datetime] = {}  # token -> creation timestamp
token_credentials: Dict[str, Tuple[str, str]] = {}  # token -> (username, password) for refresh
EXTERNAL_TOKEN_EXPIRY_HOURS = 1  # External API token expires in 1 hour


def create_token(
    username: str, 
    external_api_token: Optional[str] = None,
    credentials: Optional[Tuple[str, str]] = None
) -> str:
    """Create a random token for the user and optionally store external API token.
    
    Args:
        username: Username
        external_api_token: External API token to store
        credentials: Tuple of (username, password) for token refresh
    """
    token = secrets.token_urlsafe(32)
    valid_tokens[token] = username
    token_timestamps[token] = datetime.now()
    
    if external_api_token:
        external_api_tokens[token] = external_api_token
    
    if credentials:
        token_credentials[token] = credentials
    
    return token


def set_external_api_token(local_token: str, external_api_token: str) -> None:
    """Store external API token for a local token."""
    if local_token in valid_tokens:
        external_api_tokens[local_token] = external_api_token
        token_timestamps[local_token] = datetime.now()


def get_external_api_token(local_token: str) -> Optional[str]:
    """Get external API token for a local token."""
    return external_api_tokens.get(local_token)


def is_token_expired(local_token: str) -> bool:
    """Check if external API token is expired (1 hour)."""
    if local_token not in token_timestamps:
        return True
    
    timestamp = token_timestamps[local_token]
    expiry_time = timestamp + timedelta(hours=EXTERNAL_TOKEN_EXPIRY_HOURS)
    return datetime.now() >= expiry_time


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


async def refresh_external_api_token(local_token: str) -> Optional[str]:
    """Refresh external API token if credentials are available."""
    if local_token not in token_credentials:
        return None
    
    username, password = token_credentials[local_token]
    
    try:
        from .services.external_api import external_api_client
        external_response = await external_api_client.login(username, password)
        external_token = external_response.get("access_token")
        
        if external_token:
            set_external_api_token(local_token, external_token)
            return external_token
    except Exception as e:
        print(f"Failed to refresh token: {e}")
        return None
    
    return None


async def get_external_api_authorization(authorization: str = Header(None)) -> str:
    """Get external API authorization token from current user's token.
    
    If the user's token is already an external API token (not in valid_tokens),
    return it directly. Otherwise, try to get the stored external API token.
    If token is expired, try to refresh it automatically.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证token"
        )
    
    # Support "Bearer token" or just "token"
    token = authorization.replace("Bearer ", "").strip()
    
    # If token is not in valid_tokens, assume it's already an external API token
    if token not in valid_tokens:
        return f"Bearer {token}"
    
    # Check if token is expired
    if is_token_expired(token):
        # Try to refresh the token
        refreshed_token = await refresh_external_api_token(token)
        if refreshed_token:
            return f"Bearer {refreshed_token}"
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="外部API token已过期且无法自动刷新，请重新登录"
            )
    
    # Try to get stored external API token
    external_token = get_external_api_token(token)
    if external_token:
        return f"Bearer {external_token}"
    
    # If no external token stored, raise error
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未找到外部API token，请重新登录"
    )


async def get_external_api_authorization_optional(authorization: str = Header(None)) -> Optional[str]:
    """Get external API authorization token from current user's token (optional).
    
    Returns None if token is not available, instead of raising an error.
    """
    if not authorization:
        return None
    
    try:
        return await get_external_api_authorization(authorization)
    except HTTPException:
        return None


def verify_credentials(username: str, password: str) -> bool:
    """Verify user credentials."""
    # Special case: convert uni_staff/123456 to default credentials
    if username == "" and password == "123456":
        username = settings.default_username
        password = settings.default_password
    
    return (
        username == settings.default_username and
        password == settings.default_password
    )

