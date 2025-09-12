import asyncio
import asyncpg
from asyncpg import Pool
from typing import Optional, Dict, Any, List
import logging
from contextlib import asynccontextmanager
from app.config import settings

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool: Optional[Pool] = None
        self._lock = asyncio.Lock()
    
    async def connect(self):
        """Create connection pool"""
        async with self._lock:
            if self.pool is None:
                self.pool = await asyncpg.create_pool(
                    settings.supabase_pooler_url,
                    min_size=settings.db_pool_min,
                    max_size=settings.db_pool_max,
                    command_timeout=60
                )
                logger.info("Database pool created")
                await self.run_migrations()
    
    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Database pool closed")
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire connection from pool"""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            yield conn
    
    async def execute(self, query: str, *args) -> str:
        """Execute query without returning results"""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetch multiple rows"""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch single row"""
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args) -> Any:
        """Fetch single value"""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)
    
    async def run_migrations(self):
        """Run database migrations"""
        try:
            async with self.acquire() as conn:
                # Check if migrations table exists
                exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public'
                        AND table_name = 'migrations'
                    )
                """)
                
                if not exists:
                    await conn.execute("""
                        CREATE TABLE migrations (
                            id SERIAL PRIMARY KEY,
                            name TEXT UNIQUE NOT NULL,
                            applied_at TIMESTAMPTZ DEFAULT NOW()
                        )
                    """)
                    logger.info("Created migrations table.")

                # Get all migration files
                import os
                migration_files = sorted([f for f in os.listdir('migrations') if f.endswith('.sql')])

                for migration_file in migration_files:
                    migration_name = migration_file.rsplit('.', 1)[0]
                    
                    applied = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM migrations WHERE name = $1)",
                        migration_name
                    )

                    if not applied:
                        logger.info(f"Running migration: {migration_name}")
                        with open(f'migrations/{migration_file}', 'r') as f:
                            await conn.execute(f.read())
                        await conn.execute(
                            "INSERT INTO migrations (name) VALUES ($1)",
                            migration_name
                        )
                        logger.info(f"Migration {migration_name} completed")
                    else:
                        logger.debug(f"Migration {migration_name} already applied.")

        except Exception as e:
            logger.error(f"Migration error: {e}")
            raise

db = Database()