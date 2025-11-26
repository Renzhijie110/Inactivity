"""Authentication routes."""
from fastapi import APIRouter, HTTPException, Form, Depends, status
from ..models import LoginRequest, TokenResponse, UserInfo
from ..auth import create_token, get_current_user, verify_credentials
from ..services.external_api import external_api_client
from ..config import settings

router = APIRouter(prefix="/api", tags=["Authentication"])


@router.post("/v1/auth/token")
async def proxy_login(
    username: str = Form(...),
    password: str = Form(...)
):
    """Proxy login request to external API - supports form format."""
    # Convert uni_staff/123456 to default credentials
    if username == "uni_staff" and password == "123456":
        username = settings.default_username
        password = settings.default_password
    
    return await external_api_client.login(username, password)


@router.post("/auth/login", response_model=TokenResponse)
async def login(login_data: LoginRequest):
    """User login - simple username/password verification."""
    if not verify_credentials(login_data.username, login_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    token = create_token(login_data.username)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/auth/me", response_model=UserInfo)
async def get_current_user_info(current_user: str = Depends(get_current_user)):
    """Get current user information."""
    return {"username": current_user}

