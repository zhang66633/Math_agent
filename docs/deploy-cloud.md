# MathModelAgent 云服务器部署指南

## 部署包内容

| 文件 | 说明 |
|------|------|
| backend/Dockerfile | 云化镜像：pip 安装 + tesseract 中英文 + poppler + Noto CJK，HOST=0.0.0.0:8002，沙箱 subprocess |
| docker-compose.cloud.yml | 一键编排：data/ + knowledge_base/ 挂卷持久化、健康检查、unless-stopped 自愈 |
| backend/.env.production.example | 密钥模板（DeepSeek / GitHub OAuth / JWT），复制为 .env.production 填写 |
| deploy-cloud.md | 本文档 |

## 服务器部署步骤（4 步）

    # 1. 拉取代码
    git clone https://github.com/zhang66633/NB_project.git && cd NB_project

    # 2. 准备密钥
    cp backend/.env.production.example backend/.env.production
    # 编辑 backend/.env.production：填 DEEPSEEK_API_KEY / GITHUB_CLIENT_ID/SECRET / JWT_SECRET

    # 3. 一键构建启动（含健康检查）
    mkdir -p data knowledge_base
    docker compose -f docker-compose.cloud.yml up -d --build

    # 4. 健康检查
    curl http://127.0.0.1:8002/api/health

## 对外访问（当前生产拓扑）

- 容器端口仅绑 127.0.0.1:8002（备案期不开放公网端口）
- 对外入口：Cloudflare 隧道 nb.sgweb.asia → 127.0.0.1:8002（HTTPS，wss 同域名可用）
- 前端构建时把 API 地址指向 https://nb.sgweb.asia（临时可用 http://<服务器IP>:8002，需放开端口绑定）

## 常用运维

    docker compose -f docker-compose.cloud.yml logs -f --tail 100   # 看日志
    docker compose -f docker-compose.cloud.yml restart              # 重启
    docker compose -f docker-compose.cloud.yml down                 # 停止（挂卷数据保留）