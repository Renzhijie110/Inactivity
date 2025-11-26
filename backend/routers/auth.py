"""Authentication routes."""
from fastapi import APIRouter, HTTPException, Form, Depends, status
from ..models import LoginRequest, TokenResponse, UserInfo
from ..auth import create_token, get_current_user, verify_credentials, set_external_api_token
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
    original_username = username
    if username == "uni_staff" and password == "123456":
        username = settings.default_username
        password = settings.default_password
    
    try:
        # Get external API token
        external_response = await external_api_client.login(username, password)
        external_token = external_response.get("access_token")
        
        if external_token:
            # Create local token and store external API token with credentials for refresh
            local_token = create_token(
                username, 
                external_token,
                credentials=(username, password)  # Store credentials for token refresh
            )
            return {
                "access_token": local_token,
                "token_type": "bearer",
                "external_token": external_token  # Also return external token for backward compatibility
            }
        
        return external_response
    except HTTPException as e:
        # Re-raise HTTPException with proper status code
        raise e
    except Exception as e:
        # Handle any other exceptions (network errors, etc.)
        error_msg = str(e)
        print(f"Error during login: {error_msg}")
        
        # If it's a connection error or timeout, return 503
        if "无法连接到外部API" in error_msg or "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"外部API服务不可用: {error_msg}"
            )
        
        # For other errors, return 500 with error message
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"登录失败: {error_msg}"
        )


@router.post("/auth/login", response_model=TokenResponse)
async def login(login_data: LoginRequest):
    """User login - simple username/password verification and get external API token."""
    if not verify_credentials(login_data.username, login_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    # Use default credentials for external API
    external_username = settings.default_username
    external_password = settings.default_password
    
    try:
        # Get external API token
        external_response = await external_api_client.login(
            external_username,
            external_password
        )
        external_token = external_response.get("access_token")
        
        # Create local token with external API token and credentials for refresh
        token = create_token(
            login_data.username, 
            external_token,
            credentials=(external_username, external_password)  # Store credentials for token refresh
        )
        return {"access_token": token, "token_type": "bearer"}
    except Exception as e:
        # If external API fails, still allow local login but without external token
        print(f"Warning: Failed to get external API token: {e}")
        token = create_token(login_data.username)
        return {"access_token": token, "token_type": "bearer"}


@router.get("/auth/me", response_model=UserInfo)
async def get_current_user_info(current_user: str = Depends(get_current_user)):
    """Get current user information."""
    return {"username": current_user}

