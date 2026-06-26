#!/bin/bash
# 启动后端服务

cd "$(dirname "$0")/.."

echo "🔍 检查虚拟环境..."
if [ ! -d ".venv" ]; then
    echo "❌ 未找到虚拟环境，请先运行: python3 -m venv .venv"
    exit 1
fi

echo "📦 激活虚拟环境..."
source .venv/bin/activate

echo "📦 检查依赖..."
pip3 install -q fastapi uvicorn pydantic python-multipart

echo ""
echo "🚀 启动 FastAPI 服务..."
echo "📍 API 地址: http://localhost:8000"
echo "📖 API 文档: http://localhost:8000/docs"
echo ""

python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
