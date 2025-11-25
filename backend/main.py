import os
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Query, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import asyncpg
import httpx
from dotenv import load_dotenv

load_dotenv()

# JWT配置
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30天

# 密码加密
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer认证
security = HTTPBearer()

# 默认用户（生产环境应该从数据库读取）
DEFAULT_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
# 默认密码的哈希值（admin123）
DEFAULT_PASSWORD_HASH = pwd_context.hash(DEFAULT_PASSWORD)

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
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """创建JWT token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证token并获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return username


# 登录端点
@app.post("/api/auth/login", response_model=TokenResponse)
async def login(login_data: LoginRequest):
    """用户登录"""
    # 验证用户名和密码
    if login_data.username != DEFAULT_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # 验证密码（支持明文和哈希密码）
    if not verify_password(login_data.password, DEFAULT_PASSWORD_HASH):
        # 也支持直接比较（用于向后兼容）
        if login_data.password != DEFAULT_PASSWORD:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )
    
    # 创建token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": login_data.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/auth/me")
async def get_current_user_info(current_user: str = Depends(get_current_user)):
    """获取当前用户信息"""
    return {"username": current_user}


# 健康检查端点（不需要认证）
@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


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
