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
                base_min = max(1, settings.db_pool_min)
                base_max = max(base_min, settings.db_pool_max)

                # Try the configured max size first, then progressively smaller pools.
                fallback_sizes = []
                for candidate in (base_max, 8, 6, 4, 3, 2, 1):
                    if candidate >= 1 and candidate not in fallback_sizes:
                        fallback_sizes.append(candidate)

                last_exc: Optional[Exception] = None
                for max_size in fallback_sizes:
                    min_size = min(base_min, max_size)
                    try:
                        self.pool = await asyncpg.create_pool(
                            settings.supabase_pooler_url,
                            min_size=min_size,
                            max_size=max_size,
                            command_timeout=60,
                        )
                    except (asyncio.TimeoutError, asyncpg.PostgresError) as exc:
                        # Supabase session-mode poolers will raise either a timeout or a
                        # MaxClientsInSessionMode error when too many connections are requested.
                        message = str(exc)
                        if isinstance(exc, asyncio.TimeoutError) or "MaxClientsInSessionMode" in message:
                            logger.warning(
                                "Database pool creation failed for max_size=%s (min_size=%s): %s",
                                max_size,
                                min_size,
                                message,
                            )
                            last_exc = exc
                            continue
                        raise
                    except Exception:
                        # Any other error should bubble up immediately.
                        raise
                    else:
                        if max_size != base_max:
                            logger.warning(
                                "Database pool max_size reduced from %s to %s due to connection limits",
                                base_max,
                                max_size,
                            )
                        logger.info("Database pool created (min_size=%s, max_size=%s)", min_size, max_size)
                        await self.run_migrations()
                        return

                # All attempts failed – surface the last error for visibility.
                if last_exc:
                    raise last_exc
                raise RuntimeError("Failed to create database pool for unknown reasons")
    
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

        try:
            async with self.pool.acquire() as conn:
                yield conn
        except asyncpg.exceptions.InterfaceError as e:
            if 'pool is closing' in str(e):
                logger.warning("Database pool is closing, skipping operation")
                # Return None to signal graceful shutdown in progress
                yield None
            else:
                raise
    
    async def execute(self, query: str, *args) -> str:
        """Execute query without returning results"""
        async with self.acquire() as conn:
            if conn is None:
                logger.debug("Skipping execute during shutdown")
                return "SKIPPED"
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetch multiple rows"""
        async with self.acquire() as conn:
            if conn is None:
                logger.debug("Skipping fetch during shutdown")
                return []
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch single row"""
        async with self.acquire() as conn:
            if conn is None:
                logger.debug("Skipping fetchrow during shutdown")
                return None
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args) -> Any:
        """Fetch single value"""
        async with self.acquire() as conn:
            if conn is None:
                logger.debug("Skipping fetchval during shutdown")
                return None
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
