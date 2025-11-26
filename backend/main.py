import os
import asyncio
import secrets
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query, Depends, status, Header, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import asyncpg
import httpx
from dotenv import load_dotenv

load_dotenv()

# 简单的token存储（内存中）
valid_tokens: Dict[str, str] = {}  # token -> username

# 默认用户（生产环境应该从数据库读取）
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "40"

app = FastAPI(
    title="FastAPI Application",
    description="A FastAPI application",
    version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该指定具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection pool
db_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    """Get or create database connection pool"""
    global db_pool
    if db_pool is None:
        postgres_url = os.getenv("POSTGRES_URL")
        if not postgres_url:
            print("ERROR: POSTGRES_URL environment variable is not set")
            raise ValueError("POSTGRES_URL environment variable is not set")
        try:
            print(f"Connecting to database...")
            db_pool = await asyncpg.create_pool(postgres_url, min_size=1, max_size=10)
            print(f"✅ Database connection pool created successfully")
        except Exception as e:
            print(f"ERROR: Failed to create database connection pool: {e}")
            raise
    return db_pool


@app.on_event("startup")
async def startup():
    """Initialize database pool on startup"""
    try:
        await get_db_pool()
        print("✅ Application startup completed")
    except Exception as e:
        print(f"❌ Application startup failed: {e}")
        # Don't raise here, let the service start and handle errors in endpoints
        pass


@app.on_event("shutdown")
async def shutdown():
    """Close database pool on shutdown"""
    global db_pool
    if db_pool:
        try:
            await db_pool.close()
            print("✅ Database connection pool closed")
        except Exception as e:
            print(f"Error closing database pool: {e}")


# 认证相关模型
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# 工具函数
def create_token(username: str) -> str:
    """创建简单的随机token"""
    token = secrets.token_urlsafe(32)
    valid_tokens[token] = username
    return token


async def get_current_user(authorization: str = Header(None)):
    """验证token并获取当前用户"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证token"
        )
    
    # 支持 "Bearer token" 或直接 "token"
    token = authorization.replace("Bearer ", "").strip()
    
    if token not in valid_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的token"
        )
    
    return valid_tokens[token]


# 外部API基础URL
EXTERNAL_API_BASE = "https://noupdate.uniuni.site"

# 代理登录端点 - 转发到外部API
@app.post("/api/v1/auth/token")
async def proxy_login(
    username: str = Form(...),
    password: str = Form(...)
):
    """代理登录请求到外部API - 支持表单格式"""
    # 如果输入的是 uni_staff/123456，转换为默认账号密码
    if username == "uni_staff" and password == "123456":
        username = DEFAULT_USERNAME
        password = DEFAULT_PASSWORD
    
    try:
        async with httpx.AsyncClient() as client:
            # 转发登录请求到外部API
            response = await client.post(
                f"{EXTERNAL_API_BASE}/api/v1/auth/token",
                data={
                    "username": username,
                    "password": password
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "accept": "application/json"
                },
                timeout=30.0
            )
            
            if response.status_code != 200:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                raise HTTPException(
                    status_code=response.status_code,
                    detail=error_data.get("detail", "登录失败")
                )
            
            response_data = response.json()
            return {
                "access_token": response_data.get("access_token", ""),
                "token_type": response_data.get("token_type", "bearer")
            }
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"无法连接到外部API: {str(e)}"
        )

# 本地登录端点（保留作为备用）
@app.post("/api/auth/login", response_model=TokenResponse)
async def login(login_data: LoginRequest):
    """用户登录 - 简单的账号密码验证"""
    # 验证用户名
    if login_data.username != DEFAULT_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    # 验证密码（直接比较，简单直接）
    if login_data.password != DEFAULT_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    # 创建并返回简单的token
    token = create_token(login_data.username)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/auth/me")
async def get_current_user_info(current_user: str = Depends(get_current_user)):
    """获取当前用户信息"""
    return {"username": current_user}


# 健康检查端点（不需要认证）
@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


# 代理扫描记录API - 转发到外部API
@app.get("/api/v1/scan-records/weekly")
async def proxy_scan_records(
    show_cancelled: str = Query("false"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort: Optional[str] = Query(None),
    order: Optional[str] = Query(None),
    warehouse: Optional[str] = Query(None),
    authorization: str = Header(None)
):
    """代理扫描记录请求到外部API"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证token"
        )
    
    try:
        # 构建查询参数
        params = {
            "show_cancelled": show_cancelled,
            "page": page,
            "page_size": page_size,
        }
        if sort:
            params["sort"] = sort
        if order:
            params["order"] = order
        if warehouse:
            params["warehouse"] = warehouse
        
        async with httpx.AsyncClient() as client:
            # 转发请求到外部API
            response = await client.get(
                f"{EXTERNAL_API_BASE}/api/v1/scan-records/weekly",
                params=params,
                headers={
                    "Authorization": authorization,
                    "accept": "application/json"
                },
                timeout=30.0
            )
            
            if response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="认证失败"
                )
            
            if response.status_code != 200:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                raise HTTPException(
                    status_code=response.status_code,
                    detail=error_data.get("detail", "请求失败")
                )
            
            return response.json()
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"无法连接到外部API: {str(e)}"
        )
