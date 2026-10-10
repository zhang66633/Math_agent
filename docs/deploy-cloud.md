# MathModelAgent 云服务器部署指南

## 部署包内容

| 文件 | 说明 |
|------|------|
| backend/Dockerfile | 云化镜像：pip 安装 + tesseract 中英文 + poppler + Noto CJK，HOST=0.0.0.0:8002，沙箱 subprocess |
| docker-compose.yml | 统一编排：`docker compose up -d` 即仅启动后端（cloud 模式）；`--profile dev` 才带前端/redis/chromadb |
| backend/.env.production.example | 密钥模板（DeepSeek / GitHub OAuth / JWT），复制为 backend/.env 填写 |
| docs/deploy-cloud.md | 本文档 |

## 服务器部署步骤（4 步）

    # 1. 拉取代码
    git clone https://github.com/zhang66633/Math_agent.git && cd Math_agent

    # 2. 准备密钥（生产变量直接写 backend/.env）
    cp backend/.env.production.example backend/.env
    # 编辑 backend/.env：填 DEEPSEEK_API_KEY / GITHUB_CLIENT_ID/SECRET / JWT_SECRET / HOST=0.0.0.0

    # 3. 一键构建启动（仅后端，含健康检查；数据落 backend/data + backend/knowledge_base）
    docker compose up -d --build

    # 4. 健康检查
    curl http://127.0.0.1:8002/api/health

> 注：2026-10 起 docker-compose.cloud.yml 合并进 docker-compose.yml（backend 为无
> profile 的默认服务，云端即「up 即后端」）；原 cloud 文件的 ./data、./knowledge_base
> 根目录挂卷统一为 ./backend/data、./backend/knowledge_base，与原 dev 编排一致。

## 对外访问（当前生产拓扑）

- 容器端口仅绑 127.0.0.1:8002（备案期不开放公网端口）
- 对外入口：Cloudflare 隧道 nb.sgweb.asia → 127.0.0.1:8002（HTTPS，wss 同域名可用）
- 前端构建时把 API 地址指向 https://nb.sgweb.asia（临时可用 http://<服务器IP>:8002，需放开端口绑定）

## 常用运维

    docker compose logs -f --tail 100   # 看日志
    docker compose restart              # 重启
    docker compose down                 # 停止（挂卷数据保留）
