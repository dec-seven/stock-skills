"""
新闻数据库操作模块 - SQLite存储 + 自动去重
"""
import sqlite3
import json
import os
from typing import List, Dict, Optional
from contextlib import contextmanager

class NewsDB:
    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "data", "news.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                time TEXT,
                source TEXT DEFAULT 'sina',
                importance INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON news(created_at)")
            conn.commit()
    
    def insert_news(self, news: Dict) -> Optional[int]:
        source_id = news.get("source_id") or news.get("id")
        if not source_id:
            return None
        with self._get_conn() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO news (source_id, title, content, time, source, importance, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(source_id), news.get("title", ""), news.get("content", ""),
                     news.get("time", ""), news.get("source", "sina"), news.get("importance", 0),
                     news.get("created_at", ""))
                )
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                return None
    
    def insert_batch(self, news_list: List[Dict]) -> int:
        inserted = 0
        for news in news_list:
            if self.insert_news(news):
                inserted += 1
        return inserted
    
    def get_latest(self, limit: int = 50) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, source_id, title, content, time, source, importance, created_at FROM news ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(row) for row in rows]
    
    def get_since(self, since_id: int, limit: int = 100) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, source_id, title, content, time, source, importance, created_at FROM news WHERE id > ? ORDER BY id ASC LIMIT ?",
                (since_id, limit)
            ).fetchall()
            return [dict(row) for row in rows]
    
    def get_last_id(self) -> int:
        with self._get_conn() as conn:
            row = conn.execute("SELECT MAX(id) as max_id FROM news").fetchone()
            return row["max_id"] or 0
