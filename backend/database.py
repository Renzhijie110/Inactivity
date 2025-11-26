"""Database connection and pool management."""
import asyncpg
from typing import Optional, List, Dict, Any
from .config import settings


class Database:
    """Database connection pool manager."""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self) -> None:
        """Create database connection pool."""
        if self.pool is None:
            if not settings.postgres_url:
                raise ValueError("POSTGRES_URL environment variable is not set")
            
            try:
                print("Connecting to database...")
                self.pool = await asyncpg.create_pool(
                    settings.postgres_url,
                    min_size=1,
                    max_size=10
                )
                print("✅ Database connection pool created successfully")
            except Exception as e:
                print(f"ERROR: Failed to create database connection pool: {e}")
                raise
    
    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self.pool:
            try:
                await self.pool.close()
                print("✅ Database connection pool closed")
            except Exception as e:
                print(f"Error closing database pool: {e}")
    
    async def get_pool(self) -> asyncpg.Pool:
        """Get database connection pool."""
        if self.pool is None:
            await self.connect()
        return self.pool
    
    async def get_consjob_list(self) -> List[Dict[str, Any]]:
        """Get all consjob records from database."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    id,
                    tracking_number,
                    order_id,
                    warehouse,
                    zone,
                    driver_id,
                    current_status,
                    nonupdated_start_timestamp,
                    created_at,
                    updated_at
                FROM consjob
                ORDER BY created_at DESC
            """)
            return [dict(row) for row in rows]
    
    async def save_consjob_data(self, items: List[Dict[str, Any]]) -> int:
        """Save warehouse data to consjob table.
        
        Args:
            items: List of item dictionaries from external API
            
        Returns:
            Number of records inserted/updated
        """
        if not items:
            return 0
        
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            # Create table if not exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS consjob (
                    id SERIAL PRIMARY KEY,
                    tracking_number VARCHAR(255),
                    order_id VARCHAR(255),
                    warehouse VARCHAR(50),
                    zone VARCHAR(50),
                    driver_id VARCHAR(100),
                    current_status VARCHAR(100),
                    nonupdated_start_timestamp VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tracking_number, order_id, warehouse)
                )
            """)
            
            # Create index on warehouse for faster queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_consjob_warehouse 
                ON consjob(warehouse)
            """)
            
            # Insert or update records
            count = 0
            for item in items:
                try:
                    await conn.execute("""
                        INSERT INTO consjob (
                            tracking_number,
                            order_id,
                            warehouse,
                            zone,
                            driver_id,
                            current_status,
                            nonupdated_start_timestamp,
                            updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP)
                        ON CONFLICT (tracking_number, order_id, warehouse)
                        DO UPDATE SET
                            zone = EXCLUDED.zone,
                            driver_id = EXCLUDED.driver_id,
                            current_status = EXCLUDED.current_status,
                            nonupdated_start_timestamp = EXCLUDED.nonupdated_start_timestamp,
                            updated_at = CURRENT_TIMESTAMP
                    """,
                        item.get('tracking_number'),
                        item.get('order_id'),
                        item.get('warehouse'),
                        item.get('zone'),
                        item.get('driver_id'),
                        item.get('current_status'),
                        item.get('nonupdated_start_timestamp')
                    )
                    count += 1
                except Exception as e:
                    print(f"Error saving consjob item: {e}")
                    continue
            
            return count


# Global database instance
db = Database()

