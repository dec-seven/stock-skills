"""
SSE 推送服务器
"""
import json
import asyncio
from aiohttp import web
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.news_db import NewsDB

clients = set()
last_sent_id = None  # None 表示尚未初始化

async def sse_handler(request):
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }
    )
    await response.prepare(request)
    
    clients.add(response)
    print(f"[SSE] 新客户端连接，当前 {len(clients)} 个")
    
    try:
        db = NewsDB()
        news_list = db.get_latest(20)
        for news in reversed(news_list):
            await response.write(f"data: {json.dumps(news, ensure_ascii=False)}\n\n".encode())
        
        while True:
            await asyncio.sleep(1)
            
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        clients.discard(response)
        print(f"[SSE] 客户端断开，当前 {len(clients)} 个")
    
    return response

async def api_news_handler(request):
    limit = int(request.query.get("limit", "50"))
    db = NewsDB()
    news_list = db.get_latest(limit)
    return web.json_response(news_list)

async def push_new_news():
    global last_sent_id
    db = NewsDB()

    # 初始化时从数据库获取最新 ID
    if last_sent_id is None:
        last_sent_id = db.get_last_id()
        print(f"[SSE] 初始化 last_sent_id = {last_sent_id}")
    
    while True:
        await asyncio.sleep(1)
        
        new_news = db.get_since(last_sent_id)
        if new_news:
            last_sent_id = new_news[-1]["id"]
            
            dead_clients = set()
            for client in clients:
                try:
                    for news in new_news:
                        await client.write(f"data: {json.dumps(news, ensure_ascii=False)}\n\n".encode())
                except (ConnectionResetError, BrokenPipeError):
                    dead_clients.add(client)
            
            clients -= dead_clients
            print(f"[推送] {len(new_news)} 条新新闻，{len(clients)} 个客户端")

async def start_background_tasks(app):
    app["push_task"] = asyncio.create_task(push_new_news())

async def cleanup_background_tasks(app):
    app["push_task"].cancel()
    await app["push_task"]

def main():
    app = web.Application()
    app.router.add_get("/events", sse_handler)
    app.router.add_get("/api/news", api_news_handler)
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    
    port = int(os.environ.get("SSE_PORT", "8765"))
    print(f"SSE 服务器启动: http://localhost:{port}")
    print(f"  SSE 端点: http://localhost:{port}/events")
    print(f"  新闻 API: http://localhost:{port}/api/news")
    
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
