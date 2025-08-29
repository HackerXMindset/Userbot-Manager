from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncpg

class BaseModel:
    """Base model class with common CRUD operations"""
    
    def __init__(self, db):
        self.db = db
        self.table_name = None  # Must be set by subclasses
    
    async def create(self, data: Dict[str, Any]) -> asyncpg.Record:
        """Create a new record"""
        if not self.table_name:
            raise NotImplementedError("table_name must be set")
        
        columns = list(data.keys())
        placeholders = [f"${i+1}" for i in range(len(columns))]
        values = list(data.values())
        
        query = f"""
            INSERT INTO {self.table_name} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING *
        """
        
        return await self.db.fetchrow(query, *values)
    
    async def get_by_id(self, record_id: int) -> Optional[asyncpg.Record]:
        """Get record by ID"""
        query = f"SELECT * FROM {self.table_name} WHERE id = $1"
        return await self.db.fetchrow(query, record_id)
    
    async def update(self, record_id: int, data: Dict[str, Any]) -> Optional[asyncpg.Record]:
        """Update record by ID"""
        if not data:
            return await self.get_by_id(record_id)
        
        set_clauses = []
        values = []
        param_idx = 1
        
        for key, value in data.items():
            set_clauses.append(f"{key} = ${param_idx}")
            values.append(value)
            param_idx += 1
        
        values.append(record_id)
        
        query = f"""
            UPDATE {self.table_name} 
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = ${param_idx}
            RETURNING *
        """
        
        return await self.db.fetchrow(query, *values)
    
    async def delete(self, record_id: int) -> bool:
        """Delete record by ID"""
        query = f"DELETE FROM {self.table_name} WHERE id = $1"
        result = await self.db.execute(query, record_id)
        return result.split()[-1] == '1'
    
    async def list_all(self, limit: int = 100, offset: int = 0) -> List[asyncpg.Record]:
        """List all records with pagination"""
        query = f"""
            SELECT * FROM {self.table_name} 
            ORDER BY created_at DESC 
            LIMIT $1 OFFSET $2
        """
        return await self.db.fetch(query, limit, offset)
    
    async def count(self) -> int:
        """Count total records"""
        query = f"SELECT COUNT(*) FROM {self.table_name}"
        return await self.db.fetchval(query)