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
            
            # 创建weekly_inactivity表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS weekly_inactivity (
                    id SERIAL PRIMARY KEY,
                    warehouse VARCHAR(50) NOT NULL,
                    tno VARCHAR(100) NOT NULL,
                    nonupdated_start_date TIMESTAMP,
                    status INT,
                    route INT,
                    driver_id INT,
                    team_name VARCHAR(100),
                    if_driver_lost BOOLEAN,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            
            # 创建索引
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_weekly_inactivity_warehouse 
                ON weekly_inactivity(warehouse)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_weekly_inactivity_tno 
                ON weekly_inactivity(tno)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_weekly_inactivity_nonupdated_start_date 
                ON weekly_inactivity(nonupdated_start_date)
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
        await asyncio.sleep(60)
    
    print(f"[{datetime.now()}] ========== 定时任务完成，共处理 {len(warehouses)} 个warehouse，总计保存 {total_all_saved} 条记录 ==========")


async def cleanup_old_scan_records():
    """定时任务：删除超过15天的扫描记录"""
    print(f"[{datetime.now()}] ========== 开始执行清理任务：删除超过15天的扫描记录 ==========")
    
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # 先统计要删除的记录数
            count_before = await conn.fetchval("""
                SELECT COUNT(*) FROM scan_records
                WHERE nonupdated_start_timestamp < CURRENT_DATE - INTERVAL '15 days'
            """)
            
            if count_before == 0:
                print("✅ 没有需要清理的记录")
                return 0
            
            # 执行删除操作
            result = await conn.execute("""
                DELETE FROM scan_records
                WHERE nonupdated_start_timestamp < CURRENT_DATE - INTERVAL '15 days'
            """)
            
            # asyncpg的execute返回格式类似 "DELETE 123"，提取数字
            deleted_count = 0
            if result:
                try:
                    # 从返回字符串中提取数字（格式：'DELETE 123'）
                    if isinstance(result, str):
                        parts = result.split()
                        if len(parts) >= 2:
                            deleted_count = int(parts[1])
                    else:
                        deleted_count = int(result) if str(result).isdigit() else 0
                except (ValueError, AttributeError):
                    # 如果解析失败，使用之前统计的数量
                    deleted_count = count_before or 0
            
            print(f"✅ 清理任务完成，删除了 {deleted_count} 条超过15天的记录")
            return deleted_count
    
    except Exception as e:
        print(f"❌ 清理任务执行失败: {e}")
        import traceback
        print(traceback.format_exc())
        return 0


async def generate_weekly_inactivity_report():
    """定时任务：每周日生成周报数据，从scan_records写入weekly_inactivity表"""
    print(f"[{datetime.now()}] ========== 开始执行周报生成任务 ==========")
    
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            records = await conn.fetch("""
                SELECT DISTINCT 
                    tracking_number,
                    order_id,
                    warehouse,
                    driver_id,
                    current_status,
                    nonupdated_start_timestamp
                FROM scan_records
                WHERE nonupdated_start_timestamp > CURRENT_DATE - INTERVAL '14 days'
                AND nonupdated_start_timestamp < CURRENT_DATE - INTERVAL '6 days'
                AND current_status != '203'
                AND current_status != '213'
            """)
            
            if not records:
                print("✅ 没有符合条件的记录需要写入")
                # 即使没有记录，也清空表
                await conn.execute("TRUNCATE TABLE weekly_inactivity")
                print("✅ 已清空 weekly_inactivity 表")
                return 0
            
            print(f"📊 找到 {len(records)} 条符合条件的记录")
            
            # 在插入之前先清空表
            await conn.execute("TRUNCATE TABLE weekly_inactivity")
            print("✅ 已清空 weekly_inactivity 表，准备插入新数据")
            
            # 批量插入数据
            inserted_count = 0
            for record in records:
                try:
                    # 转换字段类型
                    tracking_number = record['tracking_number']
                    warehouse = record['warehouse']
                    nonupdated_start_date = record['nonupdated_start_timestamp']
                    
                    # 转换status为int（如果转换失败则为NULL）
                    status = None
                    try:
                        status = int(record['current_status']) if record['current_status'] else None
                    except (ValueError, TypeError):
                        pass
                    
                    # 转换driver_id为int（如果转换失败则为NULL）
                    driver_id = None
                    try:
                        driver_id = int(record['driver_id']) if record['driver_id'] else None
                    except (ValueError, TypeError):
                        pass
                    
                    # route可以从order_id提取，或者设为NULL
                    # 这里假设route可能需要从order_id或其他逻辑获取，暂时设为NULL
                    route = None
                    
                    # team_name暂时设为NULL，如果需要可以从其他表关联获取
                    team_name = None
                    
                    # if_driver_lost暂时设为NULL，需要根据业务逻辑确定
                    if_driver_lost = None
                    
                    # 直接插入数据（因为已经清空了表，不需要检查是否存在）
                    await conn.execute("""
                        INSERT INTO weekly_inactivity (
                            warehouse, tno, nonupdated_start_date, status, 
                            route, driver_id, team_name, if_driver_lost, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                    """,
                        warehouse,
                        tracking_number,
                        nonupdated_start_date,
                        status,
                        route,
                        driver_id,
                        team_name,
                        if_driver_lost
                    )
                    inserted_count += 1
                except Exception as e:
                    print(f"❌ 插入记录失败: {e}, tracking_number: {record.get('tracking_number', 'unknown')}")
                    continue
            
            print(f"✅ 周报生成任务完成，共插入 {inserted_count} 条记录到 weekly_inactivity 表")
            return inserted_count
    
    except Exception as e:
        print(f"❌ 周报生成任务执行失败: {e}")
        import traceback
        print(traceback.format_exc())
        return 0


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
        # 添加获取扫描记录的定时任务（每天凌晨2点执行）
        scheduler.add_job(
            fetch_and_save_scan_records,
            trigger=CronTrigger(hour='2', minute=0),  # 每天凌晨2点执行
            id='fetch_scan_records',
            name='获取扫描记录定时任务',
            max_instances=1,
            replace_existing=True
        )
        
        # 添加清理旧数据的定时任务（每天凌晨1点执行）
        scheduler.add_job(
            cleanup_old_scan_records,
            trigger=CronTrigger(hour='1', minute=0),  # 每天凌晨1点执行
            id='cleanup_old_records',
            name='清理超过15天的扫描记录',
            max_instances=1,
            replace_existing=True
        )
        
        # 添加周报生成定时任务（每周日执行）
        scheduler.add_job(
            generate_weekly_inactivity_report,
            trigger=CronTrigger(day_of_week=6, hour=5, minute=0),  # 每周日凌晨0点执行
            id='generate_weekly_inactivity',
            name='生成周报数据（weekly_inactivity）',
            max_instances=1,
            replace_existing=True
        )
        
        scheduler.start()
        print("✅ Scheduler started")
        print("  - 获取扫描记录任务：每天凌晨2点执行")
        print("  - 清理旧数据任务：每天凌晨1点执行")
        print("  - 周报生成任务：每周日凌晨0点执行")
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
    # 保存原始用户名，用于返回给前端
    original_username = username
    # 如果输入的是配置的用户名和对应的随机密码，转换为默认账号密码  
    if ((username == "uni_staff" and password == "Kp9mN2vQ7xRwZ5") or 
    (username == "JFK" and password == "aB3cD5eF8gHiJ1") or 
    (username == "EWR" and password == "jK2lM4nO6pQrS9") or 
    (username == "PHL" and password == "sT7uV9wX1yZ2aB") or 
    (username == "DCA" and password == "bC4dE6fG8hIjK3") or 
    (username == "BOS" and password == "kL3mN5oP7qRsT0") or 
    (username == "RDU" and password == "tU8vW0xY2zA3bC") or 
    (username == "CLT" and password == "cD5eF7gH9iJkL4") or 
    (username == "BUF" and password == "lM4nO6pQ8rStU1") or 
    (username == "RIC" and password == "uV9wX1yZ3aB4cD") or 
    (username == "PIT" and password == "dE6fG8hI0jKlM5") or 
    (username == "MDT" and password == "mN5oP7qR9sTuV2") or 
    (username == "ALB" and password == "vW0xY2zA4bC5dE") or 
    (username == "SYR" and password == "eF7gH9iJ1kLmN6") or 
    (username == "PWM" and password == "nO6pQ8rS0tUvW3") or 
    (username == "MIA" and password == "wX1yZ3aB5cD6eF") or 
    (username == "TPA" and password == "fG8hI0jK2lMnO7") or 
    (username == "JAX" and password == "oP7qR9sT1uVwX4") or 
    (username == "MCO" and password == "xY2zA4bC6dE7fG") or
    (username == "GNV" and password == "aB3cD5eF8gHiJ1") or
    (username == "TLH" and password == "jK2lM4nO6pQrS9")):
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
                "token_type": response_data.get("token_type", "bearer"),
                "username": original_username  # 返回原始用户名，用于前端限制仓库选择
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


# 手动触发清理任务端点（用于测试）
@app.post("/api/cron/trigger-cleanup")
async def trigger_cleanup():
    """手动触发清理旧数据定时任务（用于测试）"""
    try:
        # 在后台执行清理任务
        asyncio.create_task(cleanup_old_scan_records())
        return {
            "status": "success",
            "message": "清理任务已触发，正在后台执行"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"触发清理任务失败: {str(e)}"
        )


# 手动触发周报生成任务端点（用于测试）
@app.post("/api/cron/trigger-weekly-report")
async def trigger_weekly_report():
    """手动触发周报生成定时任务（用于测试）"""
    try:
        # 在后台执行周报生成任务
        asyncio.create_task(generate_weekly_inactivity_report())
        return {
            "status": "success",
            "message": "周报生成任务已触发，正在后台执行"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"触发周报生成任务失败: {str(e)}"
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
