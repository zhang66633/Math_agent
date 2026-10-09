# MathModelAgent — Agent 工作约定

数学建模多智能体学习与辅助平台。FastAPI + LangGraph 后端（`backend/`），Vue 3 + Vite + TS 前端（`frontend/`）。

## 权威文档

- `RULES.md` — 硬约束（技术栈/架构红线/Git 规范/目录约定）
- `PLAN.md` — 实施计划（权威）
- `docs/README.md` — 文档索引：`docs/` 为现行文档，`docs/archive/` 为历史归档（记录决策与踩坑，不作开发依据）

## 常用命令

```bash
# 后端（端口 8002，默认 127.0.0.1）
cd backend && pip install -e ".[dev]"
python -m pytest -q                  # 测试（须在 backend/ 目录）
uvicorn app.main:app --host 127.0.0.1 --port 8002   # 不带 --reload（RULES）

# 前端（5174，代理 /api → 127.0.0.1:8002）
cd frontend && pnpm install
pnpm dev
pnpm typecheck                      # vue-tsc --noEmit
pnpm lint                           # biome check src
```

## 提交规范

`type: 中文描述`（feat/fix/chore/docs/refactor）。直接推 main，先 pull 再 push；禁止 force-push / rebase。

## 安全红线（修复后现状）

- 服务默认仅本机监听（`.env` HOST=127.0.0.1）；沙箱默认 Docker 硬隔离（无 Docker 回退 subprocess 仅限可信输入）
- 路径参数一律 `_validate_path_segment`（拒绝点号段）+ `is_relative_to` containment；会话/任务按用户隔离
- LLM 内容渲染必须过 DOMPurify（含 MathML profile）；OAuth 必须带 state 校验
- 自定义 base_url 仅 https 且拒内网（SSRF）
