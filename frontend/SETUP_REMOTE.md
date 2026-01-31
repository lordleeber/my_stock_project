# Frontend 遠端啟動指南

## 在另一台電腦使用 Docker 啟動 Frontend

### 前置條件

1. 另一台電腦已安裝 Docker 和 Docker Compose
2. 兩台電腦都已安裝並登入 Tailscale

### 步驟一：複製 Frontend 資料夾

將整個 `frontend/` 資料夾複製到另一台電腦：

```bash
# 方法1: 使用 rsync (如果兩台電腦在同一網路)
rsync -av --progress frontend/ user@remote-computer:/path/to/frontend/

# 方法2: 使用 scp
scp -r frontend/ user@remote-computer:/path/to/frontend/

# 方法3: 使用 USB 隨身碟或網路共享資料夾
```

### 步驟二：確認設定檔

在另一台電腦上，確認 `frontend/docker-compose.yml` 的內容：

```yaml
services:
  frontend:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      # 這裡的 IP 是這台 Mac 的 Tailscale IP
      - NEXT_PUBLIC_API_URL=http://100.103.191.79:8000
    volumes:
      - .:/app
      - /app/node_modules
```

### 步驟三：啟動 Frontend

在另一台電腦上執行：

```bash
# 1. 進入 frontend 目錄
cd /path/to/frontend

# 2. 建置並啟動容器
docker compose up -d --build

# 3. 查看日誌確認啟動成功
docker compose logs -f frontend
```

### 步驟四：開啟瀏覽器

在另一台電腦的瀏覽器開啟：

```
http://localhost:3000
```

## 測試連線

1. 切換到「爆量掃描器」tab
2. 選擇日期：`2025-10-03`
3. 點擊「開始掃描」
4. 應該會看到掃描結果和股票列表

## 常見問題

### Q1: 無法連接到 backend？

**檢查事項：**
```bash
# 在另一台電腦上測試 Tailscale 連線
curl http://100.103.191.79:8000/health

# 應該返回：
# {"status":"ok","db_connection":"success","result":1}
```

### Q2: Frontend 容器啟動失敗？

**檢查日誌：**
```bash
docker compose logs frontend
```

**常見解決方法：**
```bash
# 清除舊容器和重建
docker compose down
docker compose up -d --build --force-recreate
```

### Q3: 圖表無法顯示？

**確認步驟：**
1. 打開瀏覽器開發者工具 (F12)
2. 查看 Console 是否有錯誤
3. 查看 Network tab，確認 API 請求成功

### Q4: 想修改 Backend IP？

**編輯 docker-compose.yml：**
```yaml
environment:
  - NEXT_PUBLIC_API_URL=http://新的IP:8000
```

**重新啟動：**
```bash
docker compose down
docker compose up -d
```

## 停止服務

```bash
# 停止但保留容器
docker compose stop

# 停止並移除容器
docker compose down

# 停止並移除容器、映像檔
docker compose down --rmi all
```

## 更新 Frontend

當 Frontend 程式碼更新時：

```bash
# 1. 同步新的程式碼到另一台電腦
rsync -av --progress frontend/ user@remote:/path/to/frontend/

# 2. 在另一台電腦上重建
cd /path/to/frontend
docker compose up -d --build
```

## 效能最佳化 (選用)

如果要在另一台電腦上以 production 模式執行：

**修改 Dockerfile 最後一行：**
```dockerfile
# 開發模式 (hot reload)
CMD ["npm", "run", "dev"]

# 改為 production 模式
CMD ["npm", "run", "build", "&&", "npm", "start"]
```

或建立一個新的 `Dockerfile.prod`：

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3000
CMD ["npm", "start"]
```

使用 production 版本：
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## 網路架構圖

```
另一台電腦                     這台 Mac
┌─────────────────┐           ┌─────────────────┐
│  Frontend       │           │  Backend        │
│  localhost:3000 │  Tailscale│  :8000          │
│                 ├───────────┤                 │
│  Docker         │           │  Docker         │
└─────────────────┘           │  PostgreSQL     │
                              └─────────────────┘
      ↑                              ↑
      │                              │
   瀏覽器訪問                   API 請求透過
   localhost:3000              Tailscale VPN
```
