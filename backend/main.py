import os
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncpg
import httpx
from dotenv import load_dotenv

load_dotenv()

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
            raise ValueError("POSTGRES_URL environment variable is not set")
        db_pool = await asyncpg.create_pool(postgres_url)
    return db_pool


@app.on_event("startup")
async def startup():
    """Initialize database pool on startup"""
    await get_db_pool()


@app.on_event("shutdown")
async def shutdown():
    """Close database pool on shutdown"""
    global db_pool
    if db_pool:
        await db_pool.close()


class WarehouseItem:
    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id")
        self.tracking_number = data.get("tracking_number")
        self.order_id = data.get("order_id")
        self.warehouse = data.get("warehouse")
        self.zone = data.get("zone")
        self.driver_id = data.get("driver_id")
        self.sorter_id = data.get("sorter_id")
        self.team_id = data.get("team_id")
        self.status = data.get("status")
        self.current_status = data.get("current_status")
        self.last_refresh_status = data.get("last_refresh_status")
        self.last_refresh_time = data.get("last_refresh_time")
        self.record_status = data.get("record_status")
        self.case_closed_status = data.get("case_closed_status")
        self.judgment_status = data.get("judgment_status")
        self.judgment_time = data.get("judgment_time")
        self.payment_status = data.get("payment_status")
        self.fine_amount = data.get("fine_amount", 0)
        self.driver_scan_record = data.get("driver_scan_record")
        self.driver_scan_timestamp = data.get("driver_scan_timestamp")
        self.dsp_code = data.get("dsp_code")
        self.oa_handler = data.get("oa_handler")
        self.oa_operator = data.get("oa_operator")
        self.update_time = data.get("update_time")
        self.nonupdated_start_date = data.get("nonupdated_start_date")
        self.nonupdated_start_timestamp = data.get("nonupdated_start_timestamp")
        self.nonupdated_over_72hrs = data.get("nonupdated_over_72hrs")
        self.recovery_cutoff_timestamp = data.get("recovery_cutoff_timestamp")
        self.updated_during_grace_period = data.get("updated_during_grace_period", 0)
        self.week_number = data.get("week_number", 0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion"""
        return {
            "id": self.id,
            "tracking_number": self.tracking_number,
            "order_id": self.order_id,
            "warehouse": self.warehouse,
            "zone": self.zone,
            "driver_id": self.driver_id,
            "sorter_id": self.sorter_id,
            "team_id": self.team_id,
            "status": self.status,
            "current_status": self.current_status,
            "last_refresh_status": self.last_refresh_status,
            "last_refresh_time": self.last_refresh_time,
            "record_status": self.record_status,
            "case_closed_status": self.case_closed_status,
            "judgment_status": self.judgment_status,
            "judgment_time": self.judgment_time,
            "payment_status": self.payment_status,
            "fine_amount": self.fine_amount,
            "driver_scan_record": self.driver_scan_record,
            "driver_scan_timestamp": self.driver_scan_timestamp,
            "dsp_code": self.dsp_code,
            "oa_handler": self.oa_handler,
            "oa_operator": self.oa_operator,
            "update_time": self.update_time,
            "nonupdated_start_date": self.nonupdated_start_date,
            "nonupdated_start_timestamp": self.nonupdated_start_timestamp,
            "nonupdated_over_72hrs": self.nonupdated_over_72hrs,
            "recovery_cutoff_timestamp": self.recovery_cutoff_timestamp,
            "updated_during_grace_period": self.updated_during_grace_period,
            "week_number": self.week_number,
        }


async def get_token_from_eric() -> str:
    """Get authentication token from Eric's API"""
    payload = {
        "username": "admin",
        "password": "40"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://noupdate.uniuni.site/api/v1/auth/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        resp = response.json()
        return resp["access_token"]


async def get_warehouse_data_for_single_warehouse(
    warehouse: str, 
    token: str
) -> List[WarehouseItem]:
    """Fetch data for a single warehouse"""
    page_size = 100
    all_items: List[WarehouseItem] = []
    page = 1
    total: Optional[int] = None

    print(f"Fetching data for warehouse: {warehouse}")

    async with httpx.AsyncClient() as client:
        while True:
            url = (
                f"https://tools.uniuni.com:8887/api/v1/scan-records/weekly?"
                f"show_cancelled=false&page={page}&page_size={page_size}&"
                f"sort=nonupdated_start_timestamp&order=desc&warehouse={warehouse}"
            )

            response = await client.get(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                }
            )
            response.raise_for_status()
            data = response.json()

            if total is None:
                total = data.get("total", 0)

            items = data.get("items", [])
            print(f"  Page {page} - Items: {len(items)}")
            
            for item_data in items:
                all_items.append(WarehouseItem(item_data))

            page += 1

            # Get all available data, no limit
            warehouse_items = [i for i in all_items if i.warehouse == warehouse]
            if total is not None and len(warehouse_items) >= total:
                break

            if len(items) == 0:
                break

    return all_items


async def get_warehouse_data_concurrent(
    warehouses: List[str]
) -> List[WarehouseItem]:
    """Fetch data from multiple warehouses concurrently"""
    token = await get_token_from_eric()
    print(f"🚀 Starting concurrent data fetching for {len(warehouses)} warehouses...")

    # Concurrently fetch data from all warehouses
    warehouse_tasks = [
        get_warehouse_data_for_single_warehouse(warehouse, token)
        for warehouse in warehouses
    ]

    results = await asyncio.gather(*warehouse_tasks, return_exceptions=True)

    # Process results
    all_items: List[WarehouseItem] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"❌ Error fetching data for {warehouses[i]}: {result}")
            continue
        print(f"✅ Completed fetching for {warehouses[i]}: {len(result)} items")
        all_items.extend(result)

    print(f"🎉 Total items fetched from all warehouses: {len(all_items)}")

    # Show statistics per warehouse
    print("📊 Warehouse data summary:")
    for i, result in enumerate(results):
        if not isinstance(result, Exception):
            print(f"  {warehouses[i]}: {len(result)} items")

    return all_items


def deduplicate_items(items: List[WarehouseItem]) -> List[WarehouseItem]:
    """Remove duplicate items based on tracking_number, keeping the one with highest id"""
    print("🔄 Starting deduplication process...")

    unique_map: Dict[str, WarehouseItem] = {}

    for item in items:
        if (item.tracking_number not in unique_map or
            unique_map[item.tracking_number].id < item.id):
            unique_map[item.tracking_number] = item

    unique_items = list(unique_map.values())
    print(f"✅ Deduplication completed: {len(items)} -> {len(unique_items)} items")

    return unique_items


async def insert_items_batch(items: List[WarehouseItem]) -> List[Dict[str, Any]]:
    """Insert items into database in batches"""
    batch_size = 1000
    inserted_items: List[Dict[str, Any]] = []

    print(f"🔄 Starting batch insert for {len(items)} items...")

    pool = await get_db_pool()

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(items) + batch_size - 1) // batch_size
        print(f"📦 Processing batch {batch_num}/{total_batches} ({len(batch)} items)")

        try:
            async with pool.acquire() as conn:
                # Prepare values for batch insert
                values_list = []
                for item in batch:
                    values_list.append((
                        item.id, item.tracking_number, item.order_id, item.warehouse,
                        item.zone, item.driver_id, item.sorter_id, item.team_id,
                        item.status, item.current_status, item.last_refresh_status,
                        item.last_refresh_time, item.record_status, item.case_closed_status,
                        item.judgment_status, item.judgment_time, item.payment_status,
                        item.fine_amount, item.driver_scan_record, item.driver_scan_timestamp,
                        item.dsp_code, item.oa_handler, item.oa_operator, item.update_time,
                        item.nonupdated_start_date, item.nonupdated_start_timestamp,
                        item.nonupdated_over_72hrs, item.recovery_cutoff_timestamp,
                        item.updated_during_grace_period, item.week_number
                    ))

                # Use executemany for batch insert
                await conn.executemany(
                    """
                    INSERT INTO recent_inactivity_records (
                        id, tracking_number, order_id, warehouse, zone, driver_id, sorter_id, team_id,
                        status, current_status, last_refresh_status, last_refresh_time, record_status,
                        case_closed_status, judgment_status, judgment_time, payment_status, fine_amount,
                        driver_scan_record, driver_scan_timestamp, dsp_code, oa_handler, oa_operator,
                        update_time, nonupdated_start_date, nonupdated_start_timestamp, nonupdated_over_72hrs,
                        recovery_cutoff_timestamp, updated_during_grace_period, week_number
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30)
                    ON CONFLICT (id) DO UPDATE SET
                        tracking_number = EXCLUDED.tracking_number,
                        order_id = EXCLUDED.order_id,
                        warehouse = EXCLUDED.warehouse,
                        zone = EXCLUDED.zone,
                        driver_id = EXCLUDED.driver_id,
                        sorter_id = EXCLUDED.sorter_id,
                        team_id = EXCLUDED.team_id,
                        status = EXCLUDED.status,
                        current_status = EXCLUDED.current_status,
                        last_refresh_status = EXCLUDED.last_refresh_status,
                        last_refresh_time = EXCLUDED.last_refresh_time,
                        record_status = EXCLUDED.record_status,
                        case_closed_status = EXCLUDED.case_closed_status,
                        judgment_status = EXCLUDED.judgment_status,
                        judgment_time = EXCLUDED.judgment_time,
                        payment_status = EXCLUDED.payment_status,
                        fine_amount = EXCLUDED.fine_amount,
                        driver_scan_record = EXCLUDED.driver_scan_record,
                        driver_scan_timestamp = EXCLUDED.driver_scan_timestamp,
                        dsp_code = EXCLUDED.dsp_code,
                        oa_handler = EXCLUDED.oa_handler,
                        oa_operator = EXCLUDED.oa_operator,
                        update_time = EXCLUDED.update_time,
                        nonupdated_start_date = EXCLUDED.nonupdated_start_date,
                        nonupdated_start_timestamp = EXCLUDED.nonupdated_start_timestamp,
                        nonupdated_over_72hrs = EXCLUDED.nonupdated_over_72hrs,
                        recovery_cutoff_timestamp = EXCLUDED.recovery_cutoff_timestamp,
                        updated_during_grace_period = EXCLUDED.updated_during_grace_period,
                        week_number = EXCLUDED.week_number
                    RETURNING id, tracking_number
                    """,
                    values_list
                )

                # Fetch inserted items
                rows = await conn.fetch(
                    "SELECT id, tracking_number FROM recent_inactivity_records WHERE id = ANY($1)",
                    [item.id for item in batch]
                )
                inserted_items.extend([dict(row) for row in rows])

            print(f"✅ Batch {batch_num} completed: {len(batch)} items inserted")

        except Exception as error:
            print(f"❌ Error in batch {batch_num}: {error}")
            # Fallback to individual inserts
            print("🔄 Falling back to individual inserts for this batch...")
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                for item in batch:
                    try:
                        await conn.execute(
                            """
                            INSERT INTO recent_inactivity_records (
                                id, tracking_number, order_id, warehouse, zone, driver_id, sorter_id, team_id,
                                status, current_status, last_refresh_status, last_refresh_time, record_status,
                                case_closed_status, judgment_status, judgment_time, payment_status, fine_amount,
                                driver_scan_record, driver_scan_timestamp, dsp_code, oa_handler, oa_operator,
                                update_time, nonupdated_start_date, nonupdated_start_timestamp, nonupdated_over_72hrs,
                                recovery_cutoff_timestamp, updated_during_grace_period, week_number
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30)
                            ON CONFLICT (id) DO UPDATE SET
                                tracking_number = EXCLUDED.tracking_number,
                                order_id = EXCLUDED.order_id,
                                warehouse = EXCLUDED.warehouse,
                                zone = EXCLUDED.zone,
                                driver_id = EXCLUDED.driver_id,
                                sorter_id = EXCLUDED.sorter_id,
                                team_id = EXCLUDED.team_id,
                                status = EXCLUDED.status,
                                current_status = EXCLUDED.current_status,
                                last_refresh_status = EXCLUDED.last_refresh_status,
                                last_refresh_time = EXCLUDED.last_refresh_time,
                                record_status = EXCLUDED.record_status,
                                case_closed_status = EXCLUDED.case_closed_status,
                                judgment_status = EXCLUDED.judgment_status,
                                judgment_time = EXCLUDED.judgment_time,
                                payment_status = EXCLUDED.payment_status,
                                fine_amount = EXCLUDED.fine_amount,
                                driver_scan_record = EXCLUDED.driver_scan_record,
                                driver_scan_timestamp = EXCLUDED.driver_scan_timestamp,
                                dsp_code = EXCLUDED.dsp_code,
                                oa_handler = EXCLUDED.oa_handler,
                                oa_operator = EXCLUDED.oa_operator,
                                update_time = EXCLUDED.update_time,
                                nonupdated_start_date = EXCLUDED.nonupdated_start_date,
                                nonupdated_start_timestamp = EXCLUDED.nonupdated_start_timestamp,
                                nonupdated_over_72hrs = EXCLUDED.nonupdated_over_72hrs,
                                recovery_cutoff_timestamp = EXCLUDED.recovery_cutoff_timestamp,
                                updated_during_grace_period = EXCLUDED.updated_during_grace_period,
                                week_number = EXCLUDED.week_number
                            RETURNING id, tracking_number
                            """,
                            item.id, item.tracking_number, item.order_id, item.warehouse, item.zone,
                            item.driver_id, item.sorter_id, item.team_id, item.status, item.current_status,
                            item.last_refresh_status, item.last_refresh_time, item.record_status,
                            item.case_closed_status, item.judgment_status, item.judgment_time,
                            item.payment_status, item.fine_amount, item.driver_scan_record,
                            item.driver_scan_timestamp, item.dsp_code, item.oa_handler, item.oa_operator,
                            item.update_time, item.nonupdated_start_date, item.nonupdated_start_timestamp,
                            item.nonupdated_over_72hrs, item.recovery_cutoff_timestamp,
                            item.updated_during_grace_period, item.week_number
                        )
                        row = await conn.fetchrow(
                            "SELECT id, tracking_number FROM recent_inactivity_records WHERE id = $1",
                            item.id
                        )
                        if row:
                            inserted_items.append(dict(row))
                    except Exception as e:
                        print(f"Error inserting item {item.tracking_number}: {e}")

    print(f"✅ Batch insert completed: {len(inserted_items)} items inserted")
    return inserted_items


@app.get("/")
async def root():
    """根路径"""
    return {"message": "Hello World", "status": "ok"}


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy"}


@app.get("/api/hello")
async def hello():
    """示例 API 端点"""
    return {"message": "Hello from FastAPI!"}


@app.get("/api/warehouse/items")
async def get_warehouse_items(
    warehouse: Optional[str] = Query(None, description="Filter by warehouse code"),
    search: Optional[str] = Query(None, description="Search in tracking_number, order_id, driver_id, etc."),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page"),
    sort_by: Optional[str] = Query("nonupdated_start_timestamp", description="Field to sort by"),
    order: str = Query("desc", regex="^(asc|desc)$", description="Sort order")
):
    """Get warehouse items with filtering, searching, and pagination"""
    try:
        pool = await get_db_pool()
        
        # Build WHERE clause with proper parameterized queries
        where_conditions = []
        params = []
        param_num = 1
        
        if warehouse:
            where_conditions.append("warehouse = $" + str(param_num))
            params.append(warehouse)
            param_num += 1
        
        if search:
            search_pattern = f"%{search}%"
            # Use same parameter for all ILIKE conditions
            param_str = "$" + str(param_num)
            where_conditions.append(
                f"(tracking_number ILIKE {param_str} OR "
                f"order_id ILIKE {param_str} OR "
                f"driver_id ILIKE {param_str} OR "
                f"sorter_id ILIKE {param_str} OR "
                f"dsp_code ILIKE {param_str})"
            )
            params.append(search_pattern)
            param_num += 1
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Validate sort_by field to prevent SQL injection
        allowed_sort_fields = [
            "id", "tracking_number", "order_id", "warehouse", "zone",
            "driver_id", "sorter_id", "team_id", "status", "current_status",
            "last_refresh_status", "last_refresh_time", "record_status",
            "case_closed_status", "judgment_status", "judgment_time",
            "payment_status", "fine_amount", "nonupdated_start_timestamp",
            "nonupdated_over_72hrs", "week_number"
        ]
        if sort_by not in allowed_sort_fields:
            sort_by = "nonupdated_start_timestamp"
        
        # Calculate offset
        offset = (page - 1) * page_size
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM recent_inactivity_records {where_clause}"
        async with pool.acquire() as conn:
            if params:
                total_count = await conn.fetchval(count_query, *params)
            else:
                total_count = await conn.fetchval(count_query)
            
            # Get paginated data
            limit_param = "$" + str(param_num)
            offset_param = "$" + str(param_num + 1)
            data_query = f"""
                SELECT * FROM recent_inactivity_records 
                {where_clause}
                ORDER BY {sort_by} {order.upper()}
                LIMIT {limit_param} OFFSET {offset_param}
            """
            query_params = params + [page_size, offset]
            rows = await conn.fetch(data_query, *query_params)
        
        # Convert to WarehouseItem objects and then to dicts
        items = [WarehouseItem(dict(row)).to_dict() for row in rows]
        
        # Get warehouse statistics if no warehouse filter
        warehouse_stats = {}
        if not warehouse:
            async with pool.acquire() as conn:
                stats_rows = await conn.fetch(
                    "SELECT warehouse, COUNT(*) as count FROM recent_inactivity_records GROUP BY warehouse"
                )
                warehouse_stats = {row["warehouse"]: row["count"] for row in stats_rows}
        
        return JSONResponse({
            "success": True,
            "data": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            },
            "filters": {
                "warehouse": warehouse,
                "search": search
            },
            "warehouse_stats": warehouse_stats
        })
        
    except Exception as error:
        print(f"Error fetching warehouse items: {error}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal Server Error",
                "details": str(error)
            }
        )


@app.get("/api/warehouse/warehouses")
async def get_warehouses():
    """Get list of all available warehouses with item counts"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT warehouse, COUNT(*) as count FROM recent_inactivity_records GROUP BY warehouse ORDER BY warehouse"
            )
            warehouses = [{"code": row["warehouse"], "count": row["count"]} for row in rows]
        
        return JSONResponse({
            "success": True,
            "warehouses": warehouses
        })
    except Exception as error:
        print(f"Error fetching warehouses: {error}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal Server Error",
                "details": str(error)
            }
        )


@app.post("/api/warehouse/sync")
async def sync_warehouse_data():
    """Sync warehouse data from API to database"""
    try:
        warehouses = list(set([
            "JFK", "EWR", "PHL", "DCA", "BOS", "RDU", "CLT", "BUF", "RIC",
            "MIA", "TPA", "MCO", "JAX", "GNV", "TLH", "ALB", "MDT", "PIT",
            "AVP", "SYR", "PWM"
        ]))

        print("🚀 Starting warehouse data processing...")

        # 1. Fetch new data from API
        api_data = await get_warehouse_data_concurrent(warehouses)
        print(f"📡 Fetched {len(api_data)} items from API")

        # 2. Fetch existing data from database
        print("🗄️ Fetching existing data from database...")
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM recent_inactivity_records")
            existing_data = [WarehouseItem(dict(row)) for row in rows]
        print(f"📊 Found {len(existing_data)} existing items in database")

        # 3. Merge API data and database data
        all_data = api_data + existing_data
        print(f"🔄 Total items after merge: {len(all_data)}")

        # 4. Deduplicate merged data
        unique_items = deduplicate_items(all_data)
        print(f"✅ After deduplication: {len(unique_items)} unique items")

        # Show statistics by warehouse
        warehouse_stats: Dict[str, int] = {}
        for item in unique_items:
            warehouse_stats[item.warehouse] = warehouse_stats.get(item.warehouse, 0) + 1

        print("📈 Unique items per warehouse:")
        for warehouse, count in warehouse_stats.items():
            print(f"  {warehouse}: {count} items")

        if len(unique_items) > 0:
            # 5. Clear database
            print("🗑️ Clearing existing data from database...")
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM recent_inactivity_records")
            print("✅ Database cleared successfully")

            # 6. Batch insert deduplicated complete data
            inserted_items = await insert_items_batch(unique_items)

            print(f"✅ Successfully inserted {len(inserted_items)} unique items")

            return JSONResponse({
                "success": True,
                "apiItems": len(api_data),
                "existingItems": len(existing_data),
                "totalAfterMerge": len(all_data),
                "uniqueItems": len(unique_items),
                "duplicatesRemoved": len(all_data) - len(unique_items),
                "insertedItems": len(inserted_items),
                "message": "Data processing completed successfully"
            })
        else:
            return JSONResponse({
                "success": True,
                "message": "No items to insert",
                "apiItems": len(api_data),
                "existingItems": len(existing_data),
                "totalAfterMerge": len(all_data),
                "uniqueItems": 0,
                "duplicatesRemoved": len(all_data)
            })

    except Exception as error:
        print(f"Error processing warehouse data: {error}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal Server Error",
                "details": str(error)
            }
        