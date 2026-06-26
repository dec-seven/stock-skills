"""
新浪财经7x24新闻抓取 - 长轮询版本
API: https://zhibo.sina.com.cn/api/zhibo/feed/
"""
import requests
import time
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.news_db import NewsDB

SINA_API = "https://zhibo.sina.com.cn/api/zhibo/feed/"

def fetch_news(since_id: int = 0, page_size: int = 50) -> list:
    """
    长轮询抓取新闻
    since_id: 上次最后一条新闻的 ID，只返回 ID 大于此值的新消息
    """
    params = {
        "page": 1,
        "page_size": page_size,
        "zhibo_id": "152",
        "tag_id": "0",
        "type": "0",
        "since_id": since_id,  # 关键参数：只获取 ID > since_id 的消息
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn/7x24/",
    }
    
    try:
        resp = requests.get(SINA_API, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        news_list = []
        for item in data.get("result", {}).get("data", {}).get("feed", {}).get("list", []):
            # 时间字段是 create_time，格式: "2026-06-26 18:54:47"
            create_time = item.get("create_time", "")
            time_str = create_time.split(" ")[-1] if " " in create_time else create_time  # 只取时间部分 "18:54:47"
            
            news = {
                "source_id": item.get("id"),
                "title": item.get("rich_text", "").replace("<b>", "").replace("</b>", "")[:100],
                "content": item.get("rich_text", "").replace("<b>", "").replace("</b>", ""),
                "time": time_str,  # 正确的时间
                "source": "sina",
                "importance": item.get("level", 0),
                "created_at": create_time,  # 完整时间戳
            }
            news_list.append(news)
        
        return news_list
    except Exception as e:
        print(f"抓取失败: {e}")
        return []

def get_last_news_id() -> int:
    """从数据库获取最后一条新闻的 source_id"""
    import sqlite3
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, "data", "news.db")
    
    if not os.path.exists(db_path):
        return 0
    
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT MAX(CAST(source_id AS INTEGER)) as max_id FROM news").fetchone()
        return row[0] or 0
    finally:
        conn.close()

def main():
    db = NewsDB()
    
    if "--once" in sys.argv:
        # 单次抓取（测试用）
        news_list = fetch_news()
        inserted = db.insert_batch(news_list)
        print(f"抓取 {len(news_list)} 条，新增 {inserted} 条")
        return
    
    # 长轮询模式
    since_id = get_last_news_id()
    print(f"开始长轮询，起始 ID: {since_id}")
    
    while True:
        news_list = fetch_news(since_id=since_id)
        
        if news_list:
            inserted = db.insert_batch(news_list)
            # 更新 since_id 为最新消息的 ID
            since_id = max(int(n.get("source_id", 0)) for n in news_list)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 新增 {inserted} 条，当前 ID: {since_id}")
        else:
            # 没有新消息，等待 5 秒
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 无新消息，等待中...")
        
        time.sleep(5)  # 无新消息时等待 5 秒

if __name__ == "__main__":
    main()
