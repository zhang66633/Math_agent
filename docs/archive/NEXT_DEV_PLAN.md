# 后续开发计划与双人分工（NEXT_DEV_PLAN）

> 版本 v1.0 · 2026-08-14 · 基线 commit `29707f0`
> 用途：代码审查修复收尾后的完成度评估 + 后续方向 + **双人开发代码分区（互不重叠）**。
> 权威依据：`RULES.md`（硬约束）、`PLAN.md`、`../roadmap.md`、`.mstar/plans/audit-2026-08-14/README.md`（本次审计结论）。

---

## 一、完成度评估

### 1.1 已交付且已修复（✅ 稳定）

| 模块 | 状态 | 说明 |
|------|------|------|
| 论文工作台（chat/teach/solution/knowledge/apikeys/settings） | ✅ | SSE 对话、多智能体流水线、知识库 CRUD、OAuth 登录 |
| 学习中心（learn/learn:unitId/practice/qa/progress） | ✅ | 三栏学习单元、训练场、答疑室、成长档案 |
| 7 智能体 + persona | ✅ | 名字/emoji/教学风格 |
| 学习内容（61 单元,文件化 content/<角色>/<unit>.md + 富化模板） | ✅ | 7 大方法类别 |
| 知识库混合检索（向量+BM25+RRF+MMR+LLM精排） | ✅ | 排序数学已抽 `knowledge/ranking.py` 并修双重反转 |
| 贝叶斯知识追踪 + 艾宾浩斯遗忘 | ✅ | 衰减已幂等化（`peak_mastery` 派生） |
| 沙箱代码执行 | ✅ | Docker 默认硬隔离 + 无 Docker 回退告警 |
| 数据文件预计算 + 附件提取 | ✅ | parquet 秒级加载 |
| Web 搜索 / 澄清交互 | ✅ | DuckDuckGo / ask_user 选项卡片 |
| GitHub OAuth + JWT | ✅ | 已加 state 防 CSRF、会话按用户隔离 |
| 测试基线 + CI + lint | ✅ | 9 套件 33 用例、GitHub Actions、vue-tsc/biome 接线 |
| 安全加固 | ✅ | 路径穿越/SSRF/XSS/沙箱/暴露面全修复（见审计索引） |

### 1.2 半成品（⚠️ 代码在但未接线 / 未验证）

| 模块 | 现状 | 缺口 |
|------|------|------|
| docker 全栈部署 | compose/nginx/Dockerfile 断点已修 | **未真机验证**（`docker compose up` 未跑通） |
| 成就系统 | `achievement_service.py` 已实现 | 纯内存、重启清零，未接 SQLite 与 `/progress` 展示 |
| 论文质检 | `scripts/paper_quality_check.py`（12 项评分） | 未接入 API/前端，仅手工脚本 |
| DDA 动态难度 | README 声称、`mastery_tracker` 有部分支撑 | 需核验是否完整实现难度自适应 |

### 1.3 未实现（❌ 待立项）

| 方向 | 依据 | 优先级建议 |
|------|------|-----------|
| 导师模式（教师查看学生进度） | ARCHITECTURE 明示二期 | P2 |
| 智能体插话协作 | ARCHITECTURE Phase 4 | P3 |
| LaTeX 论文导出 | `export_routes.py` 已有 DOCX 管线，相邻可能 | P1 |
| 对话导出 / 论文模板选择 / 多模型对比 | RESOURCES 5.2 功能缺口 | P3-P4 |

### 1.4 技术债遗留（非缺陷，低优先）

- `noExplicitAny` 107 处（warn 级，需专门类型化轮）
- `poetry.lock`（在装 poetry 的环境执行 `poetry lock` 入库）
- 真机验证 4 项：`pnpm build`、`docker compose config`、OAuth 登录、curl 路径穿越 400

---

## 二、后续开发方向（按优先级）

| # | 方向 | 落点 | 工作量 | 依赖 |
|---|------|------|--------|------|
| 1 | docker 部署真机验证补全 | 后端/部署 | S | 无 |
| 2 | 论文质检闭环（接入 `/solution` 完成反馈） | 跨层 | M | 无 |
| 3 | LaTeX 论文导出 | 后端 API | S | 无 |
| 4 | 成就系统持久化 + `/progress` 展示 | 跨层 | M | 无 |
| 5 | 导师模式 | 跨层 | L | 4 |
| 6 | DDA 核验与补全 | 后端学习 | S | 无 |
| 7 | noExplicitAny 类型化清理 | 前端 | M | 无 |
| 8 | 智能体插话 / 对话导出 / 多模型对比 | 跨层 | L | 视需 |

---

## 三、双人开发分工（域切分，文件级互不重叠）

> 核心原则：**按「业务域」切分**，每人只改自己名下的目录/文件；跨域依赖「只用不改」；跨层功能「接口契约先行」。
>
> 分配（方案 A）：**开发者 A = 建模管线（后端）**，**开发者 B = 学习平台（后端服务层）+ 前端全部**。

### 3.1 开发者 A —— 建模管线（core / sandbox / knowledge / tools）

**独占目录（B 不得改动）**：

```
backend/app/core/**        # 编排（nodes/workflow/state/router/prompts/llm/node_helpers）
backend/app/sandbox/**     # 代码沙箱
backend/app/knowledge/**   # 知识库检索（loader/embedder/retriever/ranking/schemas/chain/…）
backend/app/tools/**       # 工具（math/kb/interaction/web_search/base）
backend/app/api/chat_routes.py
backend/app/api/tasks.py
backend/app/api/files.py
backend/app/api/export_routes.py
backend/app/api/knowledge_routes.py          # 含 knowledge_shared/search/crud 拆分件
backend/app/api/knowledge_import_routes.py
backend/app/api/apikeys.py
backend/app/api/ws.py
backend/app/api/schemas/request.py            # 建模/对话相关请求模型
backend/scripts/**
backend/knowledge_base/**                      # 知识库 YAML 源数据
docker-compose.yml
nginx.conf
backend/Dockerfile*
backend/pyproject.toml
backend/pytest.ini
backend/tests/test_*（建模/检索/路径/SSRF/oauth/导出/nodes 相关）
```

**A 负责的方向**：#1 docker 部署、#2 论文质检后端 API、#3 LaTeX 导出、#6 DDA（如需动 learning 内代码则与 B 协调）。

### 3.2 开发者 B —— 学习平台服务层 + 前端全部

**独占目录（A 不得改动）**：

```
backend/app/learning/**    # 学习系统（schemas/path_generator/unit_content/knowledge_graph/mastery_tracker）
backend/app/services/**    # 服务层（session/sqlite_session_store/working_memory/episodic_memory/
                           #         achievement_service/result_packager/kb_extractor/redis_pubsub）
backend/app/auth/**        # 认证（github/dependencies/schemas）
backend/app/api/learning_routes.py
backend/app/api/profile_routes.py
backend/app/api/session_routes.py
backend/app/api/schemas/response.py            # 学习/画像/会话相关响应模型
backend/tests/test_*（学习/session 相关）

frontend/src/**            # 全部前端（pages/components/stores/composables/apis/utils/config）
frontend/package.json
frontend/pnpm-lock.yaml
frontend/biome.json
frontend/tailwind.config.js
frontend/vite.config.ts
frontend/tsconfig*.json
```

**B 负责的方向**：#2 论文质检前端展示、#4 成就持久化（后端 services + `/progress` 前端）、#5 导师模式（后端 + 前端）、#7 noExplicitAny 清理、#8 智能体插话/对话导出前端。

### 3.3 跨域依赖规则（只用不改）

本代码库存在少量跨域引用，一律「**消费方只读，改动归 owner**」：

| 依赖方向 | owner |
|----------|-------|
| A 的 `core/nodes.py`、`api/tasks.py` 用到 `services/session.py`、`services/redis_pubsub.py`、`services/result_packager.py` | B |
| A 的 `api/knowledge_import_routes.py` 用到 `services/kb_extractor.py` | B |
| B 的 `services/episodic_memory.py`、`working_memory.py` 用到 `knowledge/`（向量库/嵌入） | A |

若 A 需要改 B 的服务接口，或 B 需要改 A 的 knowledge 接口：**先在本文档「接口契约」登记变更 → owner 实施 → 消费方更新**，不在对方目录直接改代码。

### 3.4 共享文件（改动须对方知会，禁止静默改）

| 文件 | 规则 |
|------|------|
| `backend/app/config.py` / `backend/app/main.py` | 双方都可能加配置键/中间件，改动先沟通 |
| `backend/app/api/router.py` | 路由聚合器（A 加管线路由、B 加学习路由，极小文件低冲突） |
| `backend/app/api/schemas/__init__.py` | 双方共用 |
| `RULES.md` / `AGENTS.md` / `.gitignore` | 只能由提议方改动并同步告知对方 |
| `NEXT_DEV_PLAN.md`（本文档） | 每次分工/状态变更由双方共同更新 |
| 根文档（README/PLAN/RESOURCES_AND_ROADMAP） | A 改后端相关、B 改前端/学习相关，冲突时沟通 |

### 3.5 跨层功能的协作协议（避免「代码重复」）

对于同时涉及前后端的功能（质检、成就、导师模式），按此顺序：

1. **后端 owner 先定义接口契约**：在实现路由的同时，把请求/响应 JSON 结构写进本文档「接口契约」小节，并给出可 `curl` 的 mock 响应示例。
2. **前端（B）照契约并行开发**：不等待后端完成，用契约里的 JSON 结构写 `frontend/src/apis/` 调用层 + 页面，先用本地 mock 数据联调。
3. **合流**：双方各自提交，联调只发生在「接口路径 + 字段名」这个契约层，不产生代码重叠。

**铁律**：同一功能的前后端代码分属两人目录，天然不重复；唯一共享的「契约文本」由后端 owner 起草、前端引用，不作为可执行代码重复实现。

---

## 四、接口契约（本轮优先落定）

> 方向 #2 论文质检 与 #3 LaTeX 导出的契约，A 先按此定稿，B 据此并行。

### 4.1 论文质检

```
POST /api/export/quality-check        # 或复用 /api/tasks/{task_id}/quality
请求: { "markdown": "论文全文 markdown" }
响应: {
  "total": 100,
  "scores": { "问题重述": 16, "模型假设": 12, ... },   // 12 项，按 paper_quality_check.py
  "suggestions": ["建议1", "建议2"]
}
```

### 4.2 LaTeX 导出

```
POST /api/export/latex
请求: { "markdown": "论文全文", "title": "标题" }
响应: { "latex": "\\documentclass...", "download_url": "/api/export/latex/{id}.tex" }
```

### 4.3 成就

```
GET  /api/profile/achievements        # 用户已解锁成就 + 进度
响应: { "achievements": [ {"id":"first_solve","name":"首次求解","unlocked":true,"progress":1} ] }
```

> 以上契约为草案，A 落地时若有调整，**先在本文档更新**再改后端，B 以文档为准。

---

## 五、协作纪律（沿用 RULES）

- 直接推 `main`，**先 `git pull` 再 `git push`**；冲突本地 merge 解决，禁止 force-push / rebase。
- 提交格式 `type: 中文描述`（feat/fix/chore/docs/refactor）。
- 不改对方目录；共享文件改动必须先沟通。
- 后端改动跑 `cd backend && python -m pytest`；前端改动跑 `cd frontend && pnpm typecheck && pnpm lint`。
- 每个方向功能完成后，双方在本文档「完成度评估」对应行打勾并更新 `../roadmap.md`。

### 4.4 SSE 聊天工具事件协议 v2.1（A 已实现，B 面板照此渲染）

```json
// 工具调用开始（id 字段：tool_result / code_exec 回声同一 id，精确配对）
{"tool_call": {"id": "call_xxx", "name": "search_method_cards", "args": {...}}}

// 工具结果（v2.1：新增 id 回声；ok / duration_ms / error 自 v2 起）
{"tool_result": {"id": "call_xxx", "name": "...", "preview": "摘要(≤200字)", "ok": true, "duration_ms": 1234, "error": "可选，失败时才有"}}

// 代码执行（v2.1：新增 id 回声）
{"code_exec": {"status": "running", "id": "call_xxx"}}
{"code_exec": {"status": "done", "id": "call_xxx", "stdout": "...", "images": [...], "ok": true, "duration_ms": 5678}}
```

**v2.1 变更要点（A 已完成）**：
- `tool_result` / `code_exec` 回声 `tool_call` 的 `id`；前端**优先按 id 精确配对**，旧数据无 id 时退化为「最近同名未完成」匹配。修复并发同名工具（如两个 run_code 并行）结果错配气泡的问题。
- 工具为**并行执行**（KB/数学/搜索并发，run_code 独立沙箱目录同样并发），每工具带超时（web_search 30s，其余 60s）。
- 面板渲染同一张工具卡片两段更新：tool_call（running）→ tool_result（success/error + 耗时 + 预览），即「调用与输出内联成组」，不再调用在后、输出在前。

### 4.5 沙箱模式状态（A 已实现）

```
GET /api/sandbox/status
→ {"backend": "subprocess"|"docker", "configured": "docker", "docker_available": false, "note": "..."}
```

面板可在设置/首页展示当前沙箱模式（docker 硬隔离 vs subprocess 回退）。

### 4.6 方案模式事件协议 v2.1（A 已实现，B 面板照此渲染）

solution 模式事件经 **WebSocket**（`/api/ws/task/{task_id}`）推送，与 §4.4 的 SSE 共用同一套事件语义；自 v2.1 起**所有事件同时落盘** `data/task_events/{task_id}.jsonl`（dsh 式 durable 事件流）：

```
GET /api/tasks/{task_id}/events?after=0&limit=500
→ {"task_id": "...", "events": [...], "total": N, "after": 0, "has_more": bool}
```

- `plan` 事件：`{"event":"plan","data":{"plan":["analysis","modeling",...],"step_count":N}}` — 动态执行计划，前端按**真实计划**渲染时间线（不再写死 7 步；支持 skipped / rollback / 重复步骤）。
- `tool_call`：`data={"tool_call_id":"...","tool_name":"...","input":{...},"status":"running"}` — 先建卡片（执行态）。
- `tool_result`：`data={"tool_call_id":"...","preview":"...","ok":true,"duration_ms":123,"images":[...],"error":"可选"}` — 同一卡片回填（id 配对）。
- `code_exec`：`data={"status":"running"|"done","id":"...","stdout":"...","images":[...],"ok":...,"duration_ms":...}` — run_code 执行态与结果。
- `node_end`：`data={"stage":"...","title":"...","summary":"...","output_length":N,"passed":bool?,"rollback_target":"..."?}`。
- `task_end`：`data={"status":"completed"|"error","final_response_preview":"...","final_response_length":N}`。
- 刷新恢复：进会话时先 `GET .../events` 回放（after 游标增量），再连 WS 收实时事件。

### 4.7 前端体验改进清单（A 给 B 的竞赛演示优化点）

基于工具事件协议 v2.1（§4.4/§4.6）与当前痛点，B 侧可落地的体验项：

1. **工具状态徽标**：利用 tool_result 的 ok/duration_ms/error 渲染成功/失败/耗时徽标（ToolStatusBadge 已有雏形），失败红色 + 错误摘要，演示时「智能体在干活」的观感强很多。
2. **执行态进度**：code_exec running → 骨架屏/脉冲动画；写作节点 node_progress 事件（stage: outline/section/abstract/red_team）→ 顶部进度条展示 6 阶段。
3. **首字延迟**：发送后立即渲染「正在思考…」占位（已有 thinking 事件可驱动）；RAG 预检索期间发 pending 状态。
4. **错误恢复**：SSE error 帧显示「重试」按钮（复用删除掉的 handleUserSendWithRetry 思路，但要加幂等守卫）。
5. **沙箱模式徽章**：调用 §4.5 GET /api/sandbox/status，在设置页/首页显示「沙箱: Docker 硬隔离」或「subprocess 回退」。
6. **写作加速提示**：写作阶段并发后，node_progress 的 section 事件会在全部完成后批量到达，建议展示「并行生成 6 章节…」而非逐节等待。
7. **动态时间线（波次 2）**：消费 §4.6 的 plan 事件渲染真实计划；tool_call/tool_result 两段式卡片；events 端点回放恢复进度。

后端已就绪（A 侧完成）。用户决策：前端六项由 A 直接实现，不再分配给 B。波次 1（协议 v2.1 + 编排层）由 A 实现并验证；波次 2（动态时间线/交付物面板等显示层）待波次 1 实测后推进。
