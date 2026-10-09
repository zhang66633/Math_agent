# NB_project 问题清单与解决方案（多人协作版）

> **文档用途**：项目完善工作的统一入口。第一部分按模块分类列出问题，第二部分按编号给出对应解决方案，第三部分为协作防冲突规则（认领表 + 文件互斥表）。
>
> **更新规则**：认领/完成任务时更新第三部分认领表；问题修复后不要把条目从文档删除，在状态列标注 `✅ 已完成 + commit`。
>
> **关联文档**：[RULES.md](../../RULES.md)（硬约束）、[资源与路线图](../roadmap.md)（历史路线图）

---

# 第一部分：问题清单

> 编号规则：`分类字母 + 序号`（如 A1）。优先级 P0 = 数据丢失/安全问题，P1 = 影响使用，P2 = 体验优化，P3/远期 = 功能扩展。
> 「涉及文件」列为解决方案的改动边界，认领任务前**必须**核对第三部分互斥表。

## A. 工程质量与测试

| 编号 | 优先级 | 问题 | 现状证据 | 涉及文件 |
|------|--------|------|----------|----------|
| A1 | P0 | 后端零自动化测试，核心链路回归全靠人肉 | `backend/tests/` 四个子目录全空（0 个 .py） | `backend/tests/**`（新建） |
| A2 | P1 | 前端无组件/逻辑测试 | package.json 无 test 脚本、无 Vitest | `frontend/package.json`、`frontend/vite.config.ts`、`frontend/src/**/__tests__/**`（新建） |
| A3 | P1 | 无 CI，改动无门禁 | `.github/workflows/` 不存在 | `.github/workflows/ci.yml`（新建） |
| A4 | P1 | biome 装了但无 lint/format 脚本；typecheck 仅 build 时跑 | `frontend/package.json` scripts 仅 dev/build/preview | `frontend/package.json`、`frontend/biome.json` |
| A5 | P1 | 仓库卫生差，违反 RULES.md 目录约定 | `backend/_err.txt`（错误转储）、`backend/_start.bat`、`backend/sandbox_wrapper.py` 散落根部；`frontend/package-lock.json` 与 `pnpm-lock.yaml` 并存；`backend/.env` 含真实 API key | 删除/迁移上述文件；密钥轮换 |
| A6 | P2 | 前端类型逃逸 70+ 处 `as any`，后端无统一 response schema | `frontend/src/pages/knowledge/index.vue`（60+ 处）、`tool/renderers/*`、`useStreamChat.ts`、`chatSession.ts` | `frontend/src/pages/knowledge/index.vue`、`frontend/src/components/tool/renderers/*`、`frontend/src/types/*`、`frontend/src/composables/useStreamChat.ts`、`frontend/src/stores/chatSession.ts` |

## B. 数据持久化与用户体系（隐性硬伤，最优先）

| 编号 | 优先级 | 问题 | 现状证据 | 涉及文件 |
|------|--------|------|----------|----------|
| B1 | P0 | **学习进度完全不落盘**：BKT 掌握度/练习记录/复习提醒重启后全部归零 | `mastery_tracker.py:48` 纯内存字典 + 全局单例，无任何 save/load | `backend/app/learning/mastery_tracker.py`、新建 `backend/app/services/learning_store.py` |
| B2 | P0 | 用户体系没打通：OAuth 已做，但学习/画像/成就全部共享 `"default"` 用户 | `profile_routes.py:43,105` 硬编码 user_id（自带 TODO）；`learning_routes.py` 无鉴权依赖；`achievement_service.py:80` TODO 未接存储 | `backend/app/api/profile_routes.py`、`backend/app/api/learning_routes.py`、`backend/app/services/achievement_service.py`、`backend/app/auth/dependencies.py` |
| B3 | P1 | 沙箱图表重启/清 tmp 后失效（历史会话 404） | `executor.py:73` 输出写 `tempfile.gettempdir()` | `backend/app/sandbox/executor.py`（output_dir 区域）、`backend/app/api/files.py` |

## C. 上下文管理与提示词

| 编号 | 优先级 | 问题 | 现状证据 | 涉及文件 |
|------|--------|------|----------|----------|
| C1 | P1 | 聊天历史固定 20 条截断，无 token 预算管理 | `chat_routes.py:41` `MAX_HISTORY_MESSAGES = 20`、`:165` 切片 | `backend/app/api/chat_routes.py`、新建 `backend/app/core/token_budget.py` |
| C2 | P2 | LangGraph 侧 teach 模式是占位符死代码，误导后续开发 | `nodes.py:1128` 「教学模式 — 引导式对话待实现」 | `backend/app/core/nodes.py`、`backend/app/core/prompts/`（teach 相关） |
| C3 | P1 | 分析/建模输出偏简短，prompt 无 few-shot，temperature 保守 | `prompts/analysis.py`、`prompts/modeling.py`；`config.py:55` temperature=0.3 | `backend/app/core/prompts/analysis.py`、`modeling.py`、`backend/app/config.py` |

## D. 错误处理、可观测性与安全

| 编号 | 优先级 | 问题 | 现状证据 | 涉及文件 |
|------|--------|------|----------|----------|
| D1 | P1 | 前端错误处理粗糙：无统一错误码、401 不处理、无 toast | `request.ts:27-30` 拦截器直接 reject；页面大量 console.error | `frontend/src/utils/request.ts`、新建 `frontend/src/utils/errorHandler.ts`、`frontend/src/stores/auth.ts` |
| D2 | P1 | 后端只有 print + traceback，无结构化日志、无 LLM token 用量统计（成本无法核算） | `main.py:116-118` 异常处理器只 print | `backend/app/main.py`、新建 `backend/app/services/logging.py` |
| D3 | P1 | **无任何限流**：访客模式可无限调用 LLM，等于白嫖你的 DeepSeek key | 全局搜索无 rate limit 实现 | 新建 `backend/app/api/rate_limit.py`、`backend/app/main.py`（注册中间件） |
| D4 | P1 | 无健康检查端点、无数据备份策略 | docker-compose 无 healthcheck 可依赖的端点 | 新建 `backend/app/api/health_routes.py`、`backend/app/api/router.py`、`backend/scripts/backup.py` |
| D5 | P1 | 遗忘衰减无定时任务，复习提醒时效性无保障 | `mastery_tracker.py:94` 注释「应在每日定时任务中调用」但无 scheduler | 新建 `backend/app/services/scheduler.py`、`backend/app/main.py`（lifespan 挂载） |

## E. 知识库与内容

| 编号 | 优先级 | 问题 | 现状证据 | 涉及文件 |
|------|--------|------|----------|----------|
| E1 | P2 | 高频方法卡片仍有缺口（LSTM/Prophet、ANP/CRITIC、NSGA-II、XGBoost/LightGBM、DBSCAN 等）；模板仅 3 个 | 见 ../roadmap.md 第一节缺口表 | `backend/knowledge_base/methods/**`、`templates/**`（纯新增 yaml） |
| E2 | P1 | 检索缺元数据过滤（按题型/年份/赛制/难度），召回精度受限 | `knowledge/retriever.py` 无 where 过滤参数 | `backend/app/knowledge/retriever.py`、`embedder.py`、`backend/app/api/knowledge_routes.py` |

## F. 部署与运维

| 编号 | 优先级 | 问题 | 现状证据 | 涉及文件 |
|------|--------|------|----------|----------|
| F1 | P2 | Windows 下 subprocess 沙箱无 rlimit；Docker 分支已写未验证未文档 | `executor.py:96` `_run_docker` 存在但无测试 | `backend/app/sandbox/executor.py`（仅 `_run_docker` 区域）、`backend/Dockerfile.sandbox`、README |
| F2 | P1 | docker-compose 自认未验证；frontend 容器仍暴露 5174（dev 风格）；nginx.conf 写了没接入 | `docker-compose.yml`、../roadmap.md §8.5 | `docker-compose.yml`、`nginx.conf`、`frontend/Dockerfile`、`backend/Dockerfile` |

## G. 功能扩展

| 编号 | 优先级 | 问题 | 现状证据 | 涉及文件 |
|------|--------|------|----------|----------|
| G1 | P2 | 对话不满意无法重新生成 | 无 retry 入口 | `frontend/src/composables/useStreamChat.ts`、`frontend/src/stores/chatSession.ts`、`frontend/src/components/bubble/Bubble.vue`（或 ChatArea.vue） |
| G2 | P3 | 无法同题多模型对比 | 无 compare 端点 | `backend/app/api/chat_routes.py`（新增端点）、`frontend/src/pages/chat/index.vue`、`ChatInput.vue` |
| G3 | P2 | 论文只能导出 DOCX，无 LaTeX | `export_routes.py` 仅 DOCX | `backend/app/api/export_routes.py`、新建 `backend/templates/latex/*.j2` |
| G4 | P3 | web_search 结果无法沉淀为知识库内容 | 无入库/审核流程 | `backend/app/tools/web_search_tools.py`、新建 `backend/app/api/kb_auto_routes.py` |
| G5 | 远期 | 多人共享同一建模会话（协作模式） | 架构级改造 | 独立立项，**不并入本期并行开发** |

---

# 第二部分：解决方案

> 每条方案 = 编号（对应第一部分）+ 步骤 + 验收标准 + 冲突提示。改动范围严格限定在「涉及文件」内，**不要顺手重构无关代码**。

## A 组：工程质量与测试

### A1 后端测试体系（P0）
1. 新建 `backend/tests/conftest.py`：fixtures（mock LLM 调用、临时 data 目录、内存/临时 Chroma）。
2. 按优先级写单测：沙箱执行器（超时/断网/输出截断/图表生成）、知识库检索（RRF/MMR/元数据过滤）、数学工具（sympy/cvxpy）、token 预算（C1 合入后）。
3. API 测试用 `httpx.AsyncClient`：chat SSE 流、文件上传校验、apikeys CRUD、solution 启动。
4. `backend/pyproject.toml` 增加 `[tool.pytest.ini_options]`（asyncio_mode），仅此段落。
- **验收**：`pip install -e ".[dev]" && pytest` 一条命令全绿；核心文件覆盖 ≥ 60%。
- **冲突提示**：新建目录，无冲突；可随时开工。

### A2 前端组件测试（P1）
1. 安装 `vitest` + `@vue/test-utils` + `happy-dom`。
2. `frontend/vite.config.ts` 增加 test 配置块；`frontend/package.json` scripts 增加 `"test": "vitest run"`。
3. 先测纯逻辑（chatSession / onboarding stores），再测组件渲染（Bubble 各消息类型、ClarifyCard 选项选择、Markdown XSS 防护）。
- **验收**：`pnpm test` 可跑；核心组件 ≥ 20 个用例。
- **冲突提示**：`package.json` 与 A4 同文件 → **与 A4 同人串行**。

### A3 CI/CD（P1）
1. 新建 `.github/workflows/ci.yml`：backend（pip install + ruff + pytest）+ frontend（pnpm install + biome check + vue-tsc + vitest + vite build）。
2. 分支保护规则同步（禁止 force push 已有）。
- **验收**：push 自动跑全绿才可合并。
- **冲突提示**：唯一新建文件；**依赖 A1/A2/A4 先行**，建议最后认领。

### A4 lint/typecheck/format 脚本（P1）
1. `frontend/package.json` scripts 增加 `lint`（biome check src）、`format`（biome format --write src）、`typecheck`（vue-tsc -b --noEmit）。
2. 首次全量修复存量问题**单开一个 commit**，避免与并行改动混在一起。
- **验收**：三条命令全绿；commit 历史可区分「加脚本」和「修存量」。
- **冲突提示**：`package.json` 与 A2 同文件 → **与 A2 同人串行**；存量修复会触碰很多 src 文件，与 A6/G1/D1 的改动可能重叠，**修复存量时先跑 `git pull`，且只做格式修复不改逻辑**。

### A5 仓库卫生（P1）
1. 确认 `backend/sandbox_wrapper.py` 是否被 `executor.py` 引用（先 grep），引用则迁移到 `scripts/`，无引用则删除。
2. 删除 `backend/_err.txt`；`_start.bat` 与根目录 `start.bat` 功能重复则删除并同步 README。
3. 删除 `frontend/package-lock.json`（保留 pnpm-lock.yaml）。
4. 密钥处置：`git log --all --oneline -- backend/.env` 确认从未入库；轮换当前 key 并写入 `backend/.env`（不入库）。
- **验收**：backend 根部只剩 `.env`/`.env.example`/`Dockerfile*`/`pyproject.toml`；lockfile 唯一；密钥已轮换。
- **冲突提示**：纯删除/迁移，无代码冲突；**建议第一个做**，为其他人清场。

### A6 前端类型安全清理（P2）
1. `frontend/src/types/*` 补齐知识库实体类型（MethodCard/Paper/Problem/Template）与工具输出类型（替代 renderers 里的对象 any）。
2. `knowledge/index.vue` 用类型守卫替代 `(detailData.data as any)` 链。
3. `useStreamChat.ts`、`chatSession.ts` 的局部 any 改为具体类型。
- **验收**：`grep -rn "as any" src` 剩余 < 10 处且均有注释说明；`pnpm typecheck` 全绿。
- **冲突提示**：`useStreamChat.ts`/`chatSession.ts` 与 G1 同文件 → **G1 需等 A6 合入**；`knowledge/index.vue` 与 E2 的前端筛选 UI 有关 → **E2 的后端部分先行，筛选 UI 由本任务顺带实现或与 A6 同人**。

## B 组：数据持久化与用户体系（最优先）

### B1 学习进度持久化（P0）★
1. 新建 `backend/app/services/learning_store.py`：`LearningStore` 类，数据存 `backend/data/learning/{user_id}.json`，**原子写**（先写 .tmp 再 os.replace，参考 ../memory-context-guide.md）。
2. 修改 `mastery_tracker.py`：`MasteryTracker.__init__` 注入 store（默认实例）；`update_from_event`、`apply_decay` 变更后自动 `store.save()`；启动时 `store.load()` 恢复。
3. **保持 `get_mastery_tracker()` 单例签名不变**，路由层零改动（learning_routes.py 留给 B2）。
- **验收**：学习→重启后端→进度完整保留；数据文件合法 JSON；中断写入不损坏数据。
- **冲突提示**：`mastery_tracker.py` 独占；`backend/data/learning/` 加入 `.gitignore`；**B2 依赖本任务**。

### B2 用户体系打通（P0）★
1. `auth/dependencies.py` 新增 `get_current_user_optional`（有效 JWT 返回真实用户；无/无效 token 生成持久化的 `guest-{随机ID}`）。
2. `profile_routes.py`：删除全部 `"default"`，从依赖取 user_id；`_profiles` 内存字典改文件持久化（`backend/data/profiles/{uid}.json`，原子写）；`:105` 的 `total_units: 45` 改为从学习路径动态统计。
3. `learning_routes.py`：所有接口挂鉴权依赖，数据读写按 user_id 隔离（复用 B1 的 store）。
4. `achievement_service.py`：成就事件按 user_id 存取，接 B1 的 store 或独立 JSON。
- **验收**：两个账号学习互不可见；访客与登录用户数据隔离；重启不丢画像；前端登录态下行为不变。
- **冲突提示**：所涉 4 个文件本组独占；**依赖 B1 先合入**；前端无需改动（token 已由 request.ts 携带）。

### B3 沙箱图表持久化（P1）
1. `executor.py` 的 `output_dir` 改为 `backend/data/code_outputs/{session_id}/{run_id}/`（**只改 __init__/output_dir/相关路径拼接区域**）。
2. `files.py` 图片路由：URL 保持兼容（`/api/images/...`），增加 session 归属校验（未登录访客仅能访问自己 session）。
3. 旧输出清理：在 `files.py` 惰性清理 7 天前目录，或提供 `scripts/clean_code_outputs.py`（**不要碰 main.py 的 lifespan**）。
- **验收**：重启后历史图表可访问；跨 session 越权访问被拒绝。
- **冲突提示**：`executor.py` 与 F1 同文件（不同区域）→ **B3 先行**，F1 合并时注意 import 区人工检查；`backend/data/code_outputs/` 加入 `.gitignore`。

## C 组：上下文管理与提示词

### C1 token 预算截断（P1）
1. 新建 `backend/app/core/token_budget.py`：启发式计数（中文 1.5 token/字、英文 1.3 token/词 × 1.1 安全系数），从最新消息**逆序贪心填充**，预算 = 模型上下文 − system − tools − 预留输出。
2. `chat_routes.py:165` 的 `MAX_HISTORY_MESSAGES` 切片替换为预算函数调用；常量 `:41` 降级为兜底上限。
- **验收**：配合 A1 单测覆盖边界；长对话不再超限报错，短对话窗口利用率提高。
- **冲突提示**：`chat_routes.py` 与 G2 同文件 → **C1 先行，G2 串行**。

### C2 teach 占位符清理（P2）
1. 确认 `nodes.py` 中 `_format_teach_response` 无调用方（grep 全仓）。
2. 确认后删除死代码；若 `prompts/` 下有仅服务于 LangGraph-teach 的未使用提示词一并删除；README/架构文档注明 `/teach` 仅走 SSE 纯对话。
- **验收**：全仓 grep 无「待实现」占位串；`/teach` 功能回归正常。
- **冲突提示**：`nodes.py` 独占；与 C3 虽同属 prompts 目录但文件不同（C3 只碰 analysis/modeling），**可并行**。

### C3 分析/建模 prompt 质量（P1）
1. `prompts/analysis.py`、`prompts/modeling.py` 各加 1–2 个优质 few-shot 示例（从 knowledge_base/papers 的获奖论文结构提炼）。
2. `config.py` 的 `default_temperature` 0.3 → 0.4（**config.py 仅本任务可改**）。
3. 用 `scripts/` 现成的 2023C 测试脚本对比前后输出质量，保留对比记录。
- **验收**：同题输出结构更完整、推导更深；无新增幻觉公式。
- **冲突提示**：`config.py` 独占（D3/D5 参数一律直读环境变量，不碰 config.py）；与 C2 可并行。

## D 组：错误处理、可观测性与安全

### D1 前端统一错误处理（P1）
1. 新建 `frontend/src/utils/errorHandler.ts`：后端错误码映射表（detail/type 字段）→ 用户可读文案。
2. `request.ts` 响应拦截器分流：401 清 token + 跳登录页；422 提取字段错误 toast；5xx 统一 toast；网络错误单独提示。
3. `stores/auth.ts` 增加 logout 方法供 401 复用。
- **验收**：所有 axios 错误有用户可见提示；401 自动登出不白屏。
- **冲突提示**：`request.ts`、`auth.ts` 独占，可并行。

### D2 后端结构化日志（P1）
1. 新建 `backend/app/services/logging.py`：JSON 行格式（时间/级别/模块/request_id/message），统一 get_logger。
2. `main.py`：全局异常处理器改用 logger；新增请求日志中间件（路径/耗时/状态码/用户）。
3. LLM 调用打点：在 core/llm/factory.py 记录 model、耗时、usage（token 用量）→ 支持按天核算成本。
- **验收**：单请求可凭 request_id 串起全链路日志；能统计每日 token 消耗。
- **冲突提示**：`main.py` 与 D3/D5 同文件 → **D2 → D3 → D5 严格串行（或同一人一次做完三个）**；factory.py 独占。

### D3 API 限流（P1）
1. 新建 `backend/app/api/rate_limit.py`：令牌桶，按 `user_id`（登录）+ `IP`（访客）双维度；参数**直接读环境变量**（RATE_LIMIT_PER_MIN、RATE_LIMIT_PER_DAY），不碰 config.py。
2. `main.py` 注册中间件，仅对 LLM 类接口（/api/chat、/api/solution、/api/learn 相关生成类）生效；429 返回 Retry-After。
3. `.env.example` 补充限流参数说明。
- **验收**：压测可触发 429；登录用户与访客额度独立；静态资源/图片不受影响。
- **冲突提示**：`main.py` 串行组内；`rate_limit.py` 独占。

### D4 健康检查与备份（P1）
1. 新建 `backend/app/api/health_routes.py`：`GET /api/health` 检查 LLM key 配置、Chroma 可达、Redis/fakeredis 状态。
2. `api/router.py` 挂载该路由（**改 router.py 而非 main.py**，避免串行组冲突）。
3. 新建 `backend/scripts/backup.py`：打包 `data/`（chroma_db、learning、profiles、uploads）+ `knowledge_base/` 为带时间戳压缩包，支持一键还原说明。
4. `docker-compose.yml` 的 backend 服务加 healthcheck（与 F2 协调，F2 尚未认领时先写独立 health 端点即可）。
- **验收**：health 端点可用；备份脚本执行后能按文档还原。
- **冲突提示**：`router.py`、`health_routes.py` 独占；compose 的 healthcheck 若与 F2 并行，**只允许 F2 改 docker-compose.yml**。

### D5 复习提醒定时任务（P1）
1. 新建 `backend/app/services/scheduler.py`：asyncio 每日任务（间隔读环境变量），遍历全用户 `apply_decay` 并落盘（依赖 B1）。
2. `main.py` lifespan 挂载/卸载调度器。
- **验收**：服务运行中每日自动衰减；进度页数据与定时结果一致。
- **冲突提示**：`main.py` 串行组内，**依赖 B1、D2 先合入**。

## E 组：知识库与内容

### E1 方法卡片/模板扩充（P2）
1. 按 ../roadmap.md 第一节缺口表补充：LSTM/Prophet、ANP/CRITIC、NSGA-II、XGBoost/LightGBM、DBSCAN/GMM、随机森林、传染病模型等（≥10 张）。
2. 每张 yaml 严格对齐现有卡片结构（principle/formulas/applicable_when/code_snippets 等），新增 1–2 个模板（如统计类、图论类框架）。
3. 导入后用 `scripts/paper_quality_check.py` 或现有校验脚本过一遍，再调 `/api/kb/reindex`。
- **验收**：reindex 后新条目可被检索命中；YAML 全部合法。
- **冲突提示**：纯新增文件，无冲突；**注意与 E2 并行时 reindex 需等双方内容都合入后统一执行一次**。

### E2 检索元数据过滤（P1）
1. `embedder.py`：确保每类文档写入 category/type/year/competition/difficulty 等 metadata（补齐缺失项）。
2. `retriever.py`：检索接口增加 filter/where 参数透传。
3. `knowledge_routes.py`：查询接口暴露过滤参数（题型/年份/赛制/难度）。
4. 前端筛选 UI：**由 A6 顺带实现**（knowledge/index.vue 归 A6 所有），本任务只交付后端 + API 文档。
- **验收**：`按 type=problem&year=2023 过滤` 能显著缩小召回范围且结果正确。
- **冲突提示**：retriever/embedder/knowledge_routes 三文件独占；与 E1 可并行（见 E1 冲突提示）。

## F 组：部署与运维

### F1 Windows 沙箱 Docker 分支验证（P2）
1. 构建 `Dockerfile.sandbox` 镜像，验证 `--rm --network=none --memory` 参数在 Windows 生效。
2. `executor.py` 仅完善 `_run_docker` 区域：docker 不可用时给出**明确错误提示**（当前是静默/隐晦失败），输出路径与 B3 保持一致。
3. README 补充 Windows 下 `SANDBOX_BACKEND=docker` 的使用说明与镜像构建命令。
- **验收**：Windows 上 Docker 模式跑通 matplotlib 出图、断网生效、超时生效。
- **冲突提示**：`executor.py` 与 B3 同文件不同区域 → **B3 先合入**；合并时人工核对 import 区。

### F2 docker-compose / nginx 验证（P1）
1. `frontend/Dockerfile`：构建静态产物 → nginx 托管（不再暴露 5174）。
2. `nginx.conf`：接管 80 端口，反代 `/api`、`/ws`；`docker-compose.yml` 增加 nginx 服务并调整端口映射。
3. chroma 数据卷路径与本地模式对齐；`backend/.env` 改由环境变量注入（compose 不依赖本地 .env 文件存在）。
4. README 补部署章节（含 D4 healthcheck 链路）。
- **验收**：一条 `docker compose up` 全栈可用，浏览器经 nginx 完成对话 + 出图。
- **冲突提示**：compose/nginx/Dockerfile 四文件独占；与 D4 并行时 compose 的 healthcheck 由本任务负责。

## G 组：功能扩展

### G1 对话重试（P2）
1. `Bubble.vue`（或 ChatArea.vue）：最后一条 assistant 消息 hover 显示「重新生成」。
2. `useStreamChat.ts` 增加 retry 方法：删除该 assistant 消息 → 用截断后的历史重新 streamChat。
3. `chatSession.ts` 配合更新消息序列。
- **验收**：点击重试后旧回答被替换为新回答；不影响其他消息。
- **冲突提示**：与 A6 同文件 → **等 A6 合入后开工**。

### G2 多模型对比（P3）
1. `chat_routes.py` 新增 `POST /api/chat/compare`（model_ids 列表，asyncio.gather 并行，SSE 分 channel）。
2. 前端 `chat/index.vue` + `ChatInput.vue`：模型多选 + 并排对比视图。
- **验收**：两个模型流式结果并排展示、互不阻塞。
- **冲突提示**：`chat_routes.py` 与 C1 同文件 → **C1 先合入**；前端页面独占。

### G3 LaTeX 导出（P2）
1. 新建 `backend/templates/latex/cumcm.tex.j2`、`mcm.tex.j2`（参考 ../roadmap.md 第二节模板项目）。
2. `export_routes.py` 新增 `POST /api/export/latex`：Markdown → Jinja2 渲染 .tex（标题/公式/表格/图片引用）。
3. 前端 solution 完成页加「导出 LaTeX」按钮。
- **验收**：导出的 .tex 用户本地可编译通过（TeX Live 由用户自备）。
- **冲突提示**：`export_routes.py` 独占；可随时开工。

### G4 知识库自动扩充（P3）
1. `web_search_tools.py` 搜索后增加 LLM 评分（相关性/信息密度）。
2. 新建 `backend/app/api/kb_auto_routes.py`：自动生成 yaml 入库（status: pending_review）+ 审核 API（批准/拒绝）+ 批准后触发 embed。
- **验收**：搜索→候选→审核→检索命中的闭环可用。
- **冲突提示**：`web_search_tools.py` 独占；新建路由文件避免碰 knowledge_routes.py（E2 所有）。

### G5 协作模式（远期）
- 多人共享建模会话：涉及 session 模型、权限、Redis 广播的架构级改造。**独立立项**，不在本期并行清单内。

---

# 第三部分：协作防冲突规则

## 一、铁律（全员）

1. **认领前查互斥表**：下表「同文件」的多个任务**不得并行**，必须串行或同一人完成。
2. **一次 commit 一件事**：提交信息格式 `type: 任务编号 描述`（如 `feat: B1 学习进度持久化`），禁止把多个任务混在一个 commit。
3. **先 pull 再 push**（RULES.md 已有）；开工前 `git pull`，提交前再 `git pull --rebase=false` 合并，遇冲突只解决自己任务涉及的行，拿不准的找任务原主人。
4. 每个任务改动**严格限定**在方案中列出的文件内，顺手重构前先问。

## 二、文件互斥总表（认领必查）

| 文件 | 涉及任务 | 并行策略 |
|------|----------|----------|
| `backend/app/main.py` | D2、D3、D5 | **严格串行：D2 → D3 → D5（或同一人一次完成）** |
| `backend/app/config.py` | C3 | 独占（D3/D5 参数直读 env，禁止改此文件） |
| `backend/app/api/chat_routes.py` | C1、G2 | **串行：C1 → G2** |
| `backend/app/sandbox/executor.py` | B3、F1 | **串行：B3 → F1**（同文件不同区域） |
| `backend/app/learning/mastery_tracker.py` | B1 | 独占（B2 依赖 B1，不直接改此文件） |
| `backend/app/api/profile_routes.py` / `learning_routes.py` | B2 | 独占 |
| `backend/app/services/achievement_service.py` | B2 | 独占 |
| `backend/app/auth/dependencies.py` | B2 | 独占 |
| `backend/app/knowledge/{retriever,embedder}.py`、`knowledge_routes.py` | E2 | 独占 |
| `backend/app/api/export_routes.py` | G3 | 独占 |
| `backend/app/api/router.py` | D4 | 独占 |
| `backend/app/tools/web_search_tools.py` | G4 | 独占 |
| `backend/app/core/llm/factory.py` | D2 | 独占 |
| `frontend/package.json` | A2、A4 | **串行：A2 → A4（或同一人）** |
| `frontend/vite.config.ts` | A2 | 独占 |
| `frontend/src/composables/useStreamChat.ts` | A6、G1 | **串行：A6 → G1** |
| `frontend/src/stores/chatSession.ts` | A6、G1 | **串行：A6 → G1** |
| `frontend/src/pages/knowledge/index.vue` | A6（含 E2 筛选 UI） | 独占 |
| `frontend/src/components/tool/renderers/*` | A6 | 独占 |
| `frontend/src/utils/request.ts`、`stores/auth.ts` | D1 | 独占 |
| `docker-compose.yml`、`nginx.conf`、`frontend/Dockerfile`、`backend/Dockerfile` | F2 | 独占 |
| `backend/knowledge_base/**`（yaml） | E1 | 纯新增，独占 |
| `backend/tests/**`、`.github/workflows/` | A1、A3 | 新建目录，独占 |
| 其余文件 | 单任务 | 无冲突 |

## 三、建议开工顺序（Wave 划分）

- **Wave 0（清场，先做）**：A5 → 之后所有人 pull 最新。
- **Wave 1（可同时开工，文件零重叠）**：B1 → B2（依赖链）、A1、A6、C2、C3、D1、D4、E1、E2、G3、F2、A2+A4（同人）、G4。
- **Wave 2（等 Wave 1 合入）**：B3（等 B1 的 data 约定）、C1、F1（等 B3）、G1（等 A6）、G2（等 C1）、A3（等 A1/A2/A4）。
- **Wave 3（main.py 串行组，同一人按序）**：D2 → D3 → D5（D5 依赖 B1）。
- **独立**：G5 远期立项。

## 四、任务认领表（认领/完成时更新）

| 任务 | 优先级 | 认领人 | 状态 | 完成 commit |
|------|--------|--------|------|-------------|
| A1 后端测试体系 | P0 | | ⬜ 待认领 | |
| A2 前端组件测试 | P1 | | ⬜ 待认领 | |
| A3 CI/CD | P1 | | ⬜ 待认领（依赖 A1/A2/A4） | |
| A4 lint/typecheck 脚本 | P1 | | ⬜ 待认领 | |
| A5 仓库卫生 | P1 | | ⬜ 待认领（建议最先） | |
| A6 前端类型清理 | P2 | | ⬜ 待认领 | |
| B1 学习进度持久化 | P0 ★ | | ⬜ 待认领（建议最先） | |
| B2 用户体系打通 | P0 ★ | | ⬜ 待认领（依赖 B1） | |
| B3 沙箱图表持久化 | P1 | | ⬜ 待认领 | |
| C1 token 预算截断 | P1 | | ⬜ 待认领 | |
| C2 teach 占位清理 | P2 | | ⬜ 待认领 | |
| C3 分析/建模 prompt 优化 | P1 | | ⬜ 待认领 | |
| D1 前端错误处理 | P1 | | ⬜ 待认领 | |
| D2 结构化日志 | P1 | | ⬜ 待认领（main.py 组） | |
| D3 API 限流 | P1 | | ⬜ 待认领（main.py 组） | |
| D4 健康检查与备份 | P1 | | ⬜ 待认领 | |
| D5 复习提醒定时任务 | P1 | | ⬜ 待认领（依赖 B1、D2） | |
| E1 方法卡片/模板扩充 | P2 | | ⬜ 待认领 | |
| E2 检索元数据过滤 | P1 | | ⬜ 待认领 | |
| F1 Windows Docker 沙箱验证 | P2 | | ⬜ 待认领（依赖 B3） | |
| F2 docker-compose/nginx | P1 | | ⬜ 待认领 | |
| G1 对话重试 | P2 | | ⬜ 待认领（依赖 A6） | |
| G2 多模型对比 | P3 | | ⬜ 待认领（依赖 C1） | |
| G3 LaTeX 导出 | P2 | | ⬜ 待认领 | |
| G4 知识库自动扩充 | P3 | | ⬜ 待认领 | |
| G5 协作模式 | 远期 | | ⏸ 独立立项 | |
