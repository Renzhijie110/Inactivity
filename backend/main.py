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
DEFAULT_PASSWORD = "admin123"

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
            
            return response.json()
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


# 仓库相关API端点（需要认证）
@app.get("/api/warehouse/warehouses")
async def get_warehouses(current_user: str = Depends(get_current_user)):
    """获取仓库列表"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT warehouse as code, COUNT(*) as count
                FROM items
                WHERE warehouse IS NOT NULL AND warehouse != ''
                GROUP BY warehouse
                ORDER BY warehouse
            """)
            warehouses = [{"code": row["code"], "count": row["count"]} for row in rows]
            return {"success": True, "warehouses": warehouses}
    except Exception as e:
        print(f"Error fetching warehouses: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/warehouse/items")
async def get_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    warehouse: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user)
):
    """获取物品列表"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # 构建查询条件
            conditions = []
            params = []
            param_count = 0
            
            if warehouse:
                param_count += 1
                conditions.append(f"warehouse = ${param_count}")
                params.append(warehouse)
            
            if search:
                param_count += 1
                search_param = f"%{search}%"
                conditions.append(f"(tracking_number ILIKE ${param_count} OR order_id ILIKE ${param_count} OR driver_id ILIKE ${param_count})")
                params.append(search_param)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            # 获取总数
            count_query = f"SELECT COUNT(*) FROM items {where_clause}"
            total = await conn.fetchval(count_query, *params)
            
            # 获取分页数据
            offset = (page - 1) * page_size
            param_count += 1
            params.append(page_size)
            param_count += 1
            params.append(offset)
            
            data_query = f"""
                SELECT 
                    id, tracking_number, order_id, warehouse, zone,
                    driver_id, current_status, nonupdated_start_timestamp
                FROM items
                {where_clause}
                ORDER BY id
                LIMIT ${param_count - 1} OFFSET ${param_count}
            """
            rows = await conn.fetch(data_query, *params)
            
            items = []
            for row in rows:
                items.append({
                    "id": row["id"],
                    "tracking_number": row["tracking_number"],
                    "order_id": row["order_id"],
                    "warehouse": row["warehouse"],
                    "zone": row["zone"],
                    "driver_id": row["driver_id"],
                    "current_status": row["current_status"],
                    "nonupdated_start_timestamp": str(row["nonupdated_start_timestamp"]) if row["nonupdated_start_timestamp"] else None
                })
            
            # 计算仓库统计
            warehouse_stats = {}
            if not warehouse and not search:
                stats_query = """
                    SELECT warehouse, COUNT(*) as count
                    FROM items
                    WHERE warehouse IS NOT NULL AND warehouse != ''
                    GROUP BY warehouse
                """
                stats_rows = await conn.fetch(stats_query)
                warehouse_stats = {row["warehouse"]: row["count"] for row in stats_rows}
            
            total_pages = (total + page_size - 1) // page_size
            
            return {
                "success": True,
                "data": items,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages
                },
                "warehouse_stats": warehouse_stats
            }
    except Exception as e:
        print(f"Error fetching items: {e}")
        raise HTTPException(status_code=500, detail=str(e))
