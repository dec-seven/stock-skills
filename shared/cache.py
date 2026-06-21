#!/usr/bin/env python3
"""数据缓存模块"""
import os
import json
import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

class DataCache:
    """SQLite 数据缓存"""
    
    def __init__(self, cache_dir: str = None):
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(__file__), '..', 'data', 'cache'
        )
        os.makedirs(self.cache_dir, exist_ok=True)
        self.db_path = os.path.join(self.cache_dir, 'cache.db')
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                source TEXT
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_expires 
            ON cache(expires_at)
        ''')
        conn.commit()
        conn.close()
    
    def _generate_key(self, data_type: str, params: Dict) -> str:
        """生成缓存键"""
        param_str = json.dumps(params, sort_keys=True)
        param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
        return f"{data_type}:{param_hash}"
    
    def get(self, data_type: str, params: Dict = None) -> Optional[Dict]:
        """获取缓存数据"""
        key = self._generate_key(data_type, params or {})
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT data, expires_at FROM cache 
            WHERE key = ?
        ''', (key,))
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        data, expires_at = row
        
        # 检查是否过期
        if expires_at:
            expires = datetime.fromisoformat(expires_at)
            if datetime.now() > expires:
                self.delete(key)
                return None
        
        return json.loads(data)
    
    def set(self, data_type: str, data: Dict, 
            params: Dict = None, ttl: int = 3600, source: str = None):
        """设置缓存数据"""
        key = self._generate_key(data_type, params or {})
        expires_at = (datetime.now() + timedelta(seconds=ttl)).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO cache 
            (key, data, expires_at, source)
            VALUES (?, ?, ?, ?)
        ''', (key, json.dumps(data, ensure_ascii=False), expires_at, source))
        conn.commit()
        conn.close()
    
    def delete(self, key: str):
        """删除缓存"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cache WHERE key = ?', (key,))
        conn.commit()
        conn.close()
    
    def clear_expired(self):
        """清理过期缓存"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM cache 
            WHERE expires_at < ?
        ''', (datetime.now().isoformat(),))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
    
    def get_stats(self) -> Dict:
        """获取缓存统计"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM cache')
        total = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM cache 
            WHERE expires_at > ?
        ''', (datetime.now().isoformat(),))
        valid = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_entries': total,
            'valid_entries': valid,
            'expired_entries': total - valid,
        }


# 全局缓存实例
_cache = None

def get_cache() -> DataCache:
    """获取全局缓存实例"""
    global _cache
    if _cache is None:
        _cache = DataCache()
    return _cache
