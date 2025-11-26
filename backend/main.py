import os
import asyncio
import secrets
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query, Depends, status, Header, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import asyncpg
import httpx
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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

# Scheduler for cron jobs
scheduler: Optional[AsyncIOScheduler] = None


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


async def init_database_tables():
    """初始化数据库表结构"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # 创建扫描记录表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_records (
                    id SERIAL PRIMARY KEY,
                    tracking_number VARCHAR(255),
                    order_id VARCHAR(255),
                    warehouse VARCHAR(255),
                    zone VARCHAR(255),
                    driver_id VARCHAR(255),
                    current_status VARCHAR(255),
                    nonupdated_start_timestamp TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tracking_number, order_id, warehouse, nonupdated_start_timestamp)
                )
            """)
            
            # 创建索引以提高查询性能
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scan_records_tracking_number 
                ON scan_records(tracking_number)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scan_records_warehouse 
                ON scan_records(warehouse)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scan_records_created_at 
                ON scan_records(created_at)
            """)
            
            print("✅ Database tables initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize database tables: {e}")
        raise


async def get_external_api_token() -> Optional[str]:
    """获取外部API的认证token"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{EXTERNAL_API_BASE}/api/v1/auth/token",
                data={
                    "username": DEFAULT_USERNAME,
                    "password": DEFAULT_PASSWORD
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "accept": "application/json"
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                response_data = response.json()
                return response_data.get("access_token")
            else:
                print(f"❌ Failed to get external API token: {response.status_code}")
                return None
    except Exception as e:
        print(f"❌ Error getting external API token: {e}")
        return None


async def fetch_and_save_scan_records_for_warehouse(warehouse: Optional[str] = None):
    """获取指定warehouse的扫描记录并写入数据库"""
    warehouse_label = warehouse if warehouse else "所有仓库"
    print(f"[{datetime.now()}] 开始获取扫描记录 - Warehouse: {warehouse_label}")
    
    try:
        # 获取认证token
        token = await get_external_api_token()
        if not token:
            print(f"❌ 无法获取认证token，跳过 {warehouse_label} 的数据获取")
            return 0
        
        pool = await get_db_pool()
        async with httpx.AsyncClient() as client:
            page = 1
            page_size = 100
            total_saved = 0
            
            while True:
                # 构建查询参数（类似API端点）
                params = {
                    "show_cancelled": "false",
                    "page": page,
                    "page_size": page_size,
                    "sort": "nonupdated_start_timestamp",
                    "order": "desc"
                }
                # 如果指定了warehouse，添加到参数中
                if warehouse:
                    params["warehouse"] = warehouse
                
                response = await client.get(
                    f"{EXTERNAL_API_BASE}/api/v1/scan-records/weekly",
                    params=params,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "accept": "application/json"
                    },
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    print(f"❌ 获取扫描记录失败: {response.status_code}")
                    break
                
                data = response.json()
                items = data.get("data") or data.get("items") or []
                
                if not items or len(items) == 0:
                    break
                
                # 批量插入数据库
                async with pool.acquire() as conn:
                    for item in items:
                        try:
                            # 解析时间戳
                            timestamp_str = item.get("nonupdated_start_timestamp")
                            timestamp = None
                            if timestamp_str:
                                try:
                                    # 尝试解析ISO格式的时间戳
                                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                except:
                                    try:
                                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                                    except:
                                        pass
                            
                            # 使用 INSERT ... ON CONFLICT 来避免重复插入
                            await conn.execute("""
                                INSERT INTO scan_records (
                                    tracking_number, order_id, warehouse, zone, 
                                    driver_id, current_status, nonupdated_start_timestamp, updated_at
                                ) VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP)
                                ON CONFLICT (tracking_number, order_id, warehouse, nonupdated_start_timestamp)
                                DO UPDATE SET
                                    zone = EXCLUDED.zone,
                                    driver_id = EXCLUDED.driver_id,
                                    current_status = EXCLUDED.current_status,
                                    updated_at = CURRENT_TIMESTAMP
                            """,
                                item.get("tracking_number"),
                                item.get("order_id"),
                                item.get("warehouse"),
                                item.get("zone"),
                                item.get("driver_id"),
                                item.get("current_status"),
                                timestamp
                            )
                            total_saved += 1
                        except Exception as e:
                            print(f"❌ 保存记录失败: {e}, item: {item.get('tracking_number', 'unknown')}")
                            continue
                
                # 检查是否还有更多页面
                pagination = data.get("pagination", {})
                total_pages = pagination.get("total_pages")
                if not total_pages:
                    # 如果没有分页信息，尝试从total计算
                    total = pagination.get("total") or data.get("total", 0)
                    if total > 0:
                        total_pages = (total + page_size - 1) // page_size
                    else:
                        total_pages = 1
                
                if page >= total_pages:
                    break
                
                page += 1
            
            print(f"✅ {warehouse_label} 数据获取完成，共保存 {total_saved} 条记录")
            return total_saved
    
    except Exception as e:
        print(f"❌ {warehouse_label} 数据获取失败: {e}")
        return 0


async def fetch_and_save_scan_records():
    """定时任务：获取所有配置的warehouse的扫描记录并写入数据库"""
    print(f"[{datetime.now()}] ========== 开始执行定时任务：获取扫描记录 ==========")
    
    # 从环境变量获取warehouse列表，如果没有则使用默认列表
    warehouses_str = os.getenv("SYNC_WAREHOUSES", "")
    if warehouses_str:
        warehouses = [w.strip() for w in warehouses_str.split(",") if w.strip()]
    else:
        # 默认仓库列表（与前端保持一致）
        warehouses = ['JFK', 'EWR', 'PHL', 'DCA', 'BOS', 'RDU', 'CLT', 'BUF', 'RIC', 'PIT', 'MDT', 'ALB', 'SYR', 'PWM', 'MIA', 'TPA', 'JAX', 'MCO', 'GNV', 'TLH']
    
    if not warehouses:
        print("⚠️ 未配置需要同步的warehouse，跳过本次任务")
        return
    
    total_all_saved = 0
    for warehouse in warehouses:
        saved_count = await fetch_and_save_scan_records_for_warehouse(warehouse)
        total_all_saved += saved_count
        # 每个warehouse之间稍作延迟，避免请求过快
        await asyncio.sleep(1)
    
    print(f"[{datetime.now()}] ========== 定时任务完成，共处理 {len(warehouses)} 个warehouse，总计保存 {total_all_saved} 条记录 ==========")


@app.on_event("startup")
async def startup():
    """Initialize database pool and start scheduler on startup"""
    global scheduler
    try:
        await get_db_pool()
        await init_database_tables()
        
        # 初始化并启动定时任务调度器
        scheduler = AsyncIOScheduler()
        # 每小时执行一次（可以根据需要调整）
        # 例如：每天凌晨2点执行 -> CronTrigger(hour=2, minute=0)
        # 每30分钟执行一次 -> CronTrigger(minute='*/30')
        scheduler.add_job(
            fetch_and_save_scan_records,
            trigger=CronTrigger(hour='2', minute=0),  # 每小时整点执行
            id='fetch_scan_records',
            name='获取扫描记录定时任务',
            replace_existing=True
        )
        scheduler.start()
        print("✅ Scheduler started - 定时任务将在每小时整点执行")
        
        # 启动时立即执行一次
        asyncio.create_task(fetch_and_save_scan_records())
        
        print("✅ Application startup completed")
    except Exception as e:
        print(f"❌ Application startup failed: {e}")
        # Don't raise here, let the service start and handle errors in endpoints
        pass


@app.on_event("shutdown")
async def shutdown():
    """Close database pool and scheduler on shutdown"""
    global db_pool, scheduler
    if scheduler:
        try:
            scheduler.shutdown()
            print("✅ Scheduler stopped")
        except Exception as e:
            print(f"Error stopping scheduler: {e}")
    
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


# 手动触发定时任务端点（用于测试）
@app.post("/api/cron/trigger-scan-records")
async def trigger_scan_records():
    """手动触发扫描记录定时任务（用于测试）"""
    try:
        # 在后台执行定时任务
        asyncio.create_task(fetch_and_save_scan_records())
        return {
            "status": "success",
            "message": "定时任务已触发，正在后台执行"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"触发定时任务失败: {str(e)}"
        )


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
