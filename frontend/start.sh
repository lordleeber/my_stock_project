#!/bin/bash

# Frontend 快速啟動腳本

echo "🚀 啟動 Frontend..."
echo ""

# 檢查 Docker 是否運行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未運行，請先啟動 Docker"
    exit 1
fi

echo "✓ Docker 已運行"

# 檢查 Tailscale 連線
echo ""
echo "📡 測試 Backend 連線..."
if curl -s http://100.103.191.79:8000/health > /dev/null 2>&1; then
    echo "✓ Backend 連線成功 (http://100.103.191.79:8000)"
else
    echo "⚠️  無法連接到 Backend"
    echo "   請確認："
    echo "   1. 另一台電腦的 Tailscale 已啟動"
    echo "   2. Backend 服務正在運行"
    echo "   3. IP 位址正確 (100.103.191.79)"
    echo ""
    read -p "是否繼續啟動 Frontend? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 停止舊容器
echo ""
echo "🛑 停止舊容器..."
docker compose down

# 建置並啟動
echo ""
echo "🔨 建置並啟動 Frontend..."
docker compose up -d --build

# 等待啟動
echo ""
echo "⏳ 等待服務啟動..."
sleep 5

# 檢查狀態
if docker compose ps | grep -q "Up"; then
    echo ""
    echo "✅ Frontend 已成功啟動！"
    echo ""
    echo "📍 訪問位址: http://localhost:3000"
    echo ""
    echo "📊 功能測試建議："
    echo "   1. 開啟瀏覽器: http://localhost:3000"
    echo "   2. 切換到「爆量掃描器」tab"
    echo "   3. 選擇日期: 2025-10-03"
    echo "   4. 點擊「開始掃描」"
    echo ""
    echo "📋 查看日誌: docker compose logs -f frontend"
    echo "🛑 停止服務: docker compose down"
else
    echo ""
    echo "❌ Frontend 啟動失敗"
    echo ""
    echo "查看日誌："
    docker compose logs frontend
    exit 1
fi
