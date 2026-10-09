# 数学建模多智能体系统 — 实施计划

> ⚠️ **蓝图说明**：`docs/archive/ARCHITECTURE.md` 为早期废弃方案（Next.js + MUI），**一律不作参考**，以本文档为准。
> 版本: v0.4 | 日期: 2026-07-23 | 项目目录: `math_agent/`（原 NB_project 已并入，GitHub 远程 `zhang66633/NB_project`）
>
> ### 📌 当前进度对齐（2026-09 校正快照；此前 2026-07-23 快照的 agent 数与页面清单已与实际脱节）
> | 维度 | 状态 | 说明 |
> |------|------|------|
> | 后端核心编排 `workflow.py` | ✅ 完成 | 11 节点 StateGraph（classify/retrieve/plan + 7 个 agent 节点 + format_response）+ WS 推送 |
> | Agent 节点 `nodes.py` | ✅ 完成 | 真实 LLM 调用：classify / retrieve / plan / analysis / modeling / data_preprocessing / solving / verification / export_results / writing / format_response |
> | 知识库 RAG（代码） | ✅ 就绪 | 混合检索（向量+BM25+标签→RRF→MMR→时间衰减）+ Chroma + Tool 封装 + chain 均已实现 |
> | 知识库（源数据） | ✅ P0 达标 | 47 张方法卡片 + 16 篇论文 + 27 道真题 + 3 个模板（YAML 真源入库） |
> | WebSocket 进度推送 | ✅ 完成 | `ws.py` 订阅 Redis 转发；`task_end`/final_response 已推送 |
> | 前端页面 | ✅ 完成 | 首页 / Chat / Solution / Knowledge / APIKeys / Settings / Login / 学习中心（learn + learn/:unitId）/ practice / progress |
> | 学习系统 | ✅ 完成 | 61 个学习单元 + 183 题题库 + 掌握度追踪（BKT+艾宾浩斯衰减）+ 成就 + 技能树 |
> | 认证 / 密钥管理 | ✅ 完成 | GitHub OAuth + `pages/apikeys` + `/api/apikeys`（支持多服务商） |
> | 自由问答 SSE | ✅ 完成 | `/api/chat` 流式输出，chat/learning 多模式（teach 模式为 API 能力，无独立页面） |
> | **LLM 工具调用** | ✅ 完成 | chat LLM 主动调用 KB 检索 + 数学计算（SymPy + cvxpy LP/QP/IP/SOCP）+ 联网搜索 |
> | **端到端联调** | ✅ 完成 | REST + WS + SSE 全部打通；全链路验证输出完整 LaTeX 论文 |

---

## Context

构建一个 **Web 版** 多智能体数学建模辅助系统：

- **前端**: 复刻 [MathModelAgent](https://github.com/jihe520/MathModelAgent) 开源项目的前端风格（Vue 3 + shadcn-vue + Tailwind），适配我们自己的后端 API
- **后端**: 自研 **LangChain + LangGraph** 多智能体编排 + FastAPI Web API + WebSocket 实时推送（不参考 MathModelAgent 后端架构）
- **多智能体**: 1 个主编排器 + 7 个子智能体（分析→建模→数据预处理→求解→验证→结果导出→写作），动态编排 + 验证回退
- **双模式**: 教学模式（苏格拉底式引导）+ 方案输出模式（完整方案）

---

## Technology Stack

| 类别 | 选型 | 说明 |
|------|------|------|
| **前端** | Vue 3.5 + Vite 6 + TypeScript 5.7 | 与源项目一致 |
| **前端 UI** | **shadcn-vue** (Reka UI 2.0) + Tailwind CSS 3 | 与源项目一致，非 Element Plus |
| **前端包管理** | pnpm 10.6 | 与源项目一致 |
| **前端状态** | Pinia 3 + pinia-plugin-persistedstate | 持久化会话 |
| **前端渲染** | Marked + KaTeX + highlight.js + md-editor-v3 | LaTeX 公式 + 代码高亮 + Markdown 编辑 |
| **前端 Notebook** | render-jupyter-notebook-vue | Jupyter 风格代码单元格渲染 |
| **前端图标** | lucide-vue-next | 轻量开源图标 |
| **前端代码质量** | Biome (lint + format) | 与源项目一致 |
| **后端框架** | FastAPI + Uvicorn | 异步 Web + 原生 WebSocket |
| **实时通信** | WebSocket + Redis Pub/Sub (fakeredis 回退) | 解耦 agent 执行与消息推送 |
| **Agent 框架** | **LangGraph >= 0.2.0** (Command API) | LangChain 官方多智能体方案 |
| **LLM 抽象** | LangChain >= 0.3.0 | 统一 ChatModel/Tool/Prompt/Retriever |
| **LLM 提供商** | LLMFactory（国产模型优先：DeepSeek / Qwen / GLM / 豆包） | 每 agent 独立模型配置 |
| **向量数据库** | ChromaDB (langchain-chroma) | 本地零运维 |
| **知识库** | YAML + Pydantic 校验 | 人可读，Git 版本控制 |
| **代码沙箱** | subprocess → Docker 升级路径 | 渐进式安全策略 |
| **Python 包管理** | Poetry | 依赖锁定 |
| **部署** | Docker Compose + 本地开发双模式 | 灵活适配 |

---

## Project Structure

```
math_agent/
├── AGENTS.md                        # Agent 工作约定
├── PLAN.md                          # 本文件：实施计划（权威）
├── README.md
├── RULES.md                         # 项目协作红线规则
├── docs/                            # 开发文档（现行 + archive 历史归档，见 docs/README.md 索引）
├── docker-compose.yml
├── start.py                        # 统一入口：install / start / stop 子命令
├── start.bat                       # Windows 转发器（纯 ASCII，逻辑在 start.py）
│
├── backend/                         # FastAPI + LangGraph 后端
│   ├── pyproject.toml
│   ├── .env                         # 环境变量（含 GitHub OAuth、LLM Key）
│   ├── .env.example
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口
│   │   ├── config.py                # 配置管理 (Pydantic Settings)
│   │   ├── api/                     # HTTP + WebSocket 接口
│   │   │   ├── router.py            # 主路由注册（含 auth）
│   │   │   ├── apikeys.py           # API Key CRUD
│   │   │   ├── tasks.py             # 任务 CRUD
│   │   │   ├── files.py             # 文件上传/下载
│   │   │   ├── chat_routes.py       # SSE 流式对话 (chat/teach 双模式)
│   │   │   ├── knowledge_routes.py  # 知识库 CRUD + 搜索
│   │   │   ├── ws.py                # WebSocket 实时推送
│   │   │   └── schemas/             # Pydantic 请求/响应模型
│   │   ├── core/                    # LangGraph 多智能体核心
│   │   │   ├── workflow.py          # StateGraph 构建
│   │   │   ├── state.py             # AgentState 定义
│   │   │   ├── nodes.py             # 图节点函数
│   │   │   ├── router.py            # Command 路由逻辑
│   │   │   ├── agents/              # 5 个子智能体实现
│   │   │   ├── prompts/             # Prompt 模板（按 agent 分文件）
│   │   │   └── llm/                 # LLM 工厂 + 多提供商支持
│   │   ├── tools/                   # LangChain Tool 定义（LLM bind_tools）
│   │   │   ├── __init__.py
│   │   │   ├── kb_tools.py          # 知识库搜索: search_method_cards / search_similar_papers / get_analysis_template
│   │   │   └── math_tools.py        # 数学计算: sympy_compute (SymPy) / solve_optimization (cvxpy LP/QP/IP/SOCP)
│   │   ├── knowledge/               # 知识库子系统
│   │   │   ├── __init__.py
│   │   │   ├── schemas.py           # Pydantic 数据模型
│   │   │   ├── loader.py            # YAML 加载器
│   │   │   ├── embedder.py          # 向量化管道（可配置 embedding）
│   │   │   ├── indexer.py           # 增量索引构建
│   │   │   └── retriever.py         # 混合检索器（语义+标签+MMR+关键词兜底）
│   │   ├── sandbox/                 # 代码执行沙箱
│   │   │   ├── __init__.py
│   │   │   └── executor.py          # subprocess 执行器
│   │   └── services/                # 服务层
│   │       ├── __init__.py
│   │       ├── redis_pubsub.py      # Redis Pub/Sub（fakeredis 回退）
│   │       └── session.py           # 会话管理
│   ├── knowledge_base/              # 知识数据（Git 跟踪）
│   │   ├── methods/                 # 方法卡片（按类别分子目录）
│   │   │   ├── optimization/        # 优化类：线性规划、整数规划、动态规划、图论、运输问题
│   │   │   ├── prediction/          # 预测类：ARIMA、灰色预测
│   │   │   ├── evaluation/          # 评价类：层次分析法、熵权法
│   │   │   └── statistics/          # 统计类：回归分析
│   │   ├── papers/                  # 真题论文（按竞赛分子目录）
│   │   │   └── 国赛/
│   │   │       └── 2023C_vegetable_pricing.yaml
│   │   ├── templates/               # 模板框架
│   │   │   ├── optimization_framework.yaml
│   │   │   └── prediction_framework.yaml
│   │   └── problems/                # 赛题库（待填充）
│   ├── data/                        # 运行时数据（.gitignore）
│   │   ├── apikeys.json             # API Key 存储
│   │   ├── sessions.json            # 会话存储
│   │   └── chroma_db/               # 向量持久化
│   └── tests/
│
└── frontend/                        # Vue 3 + Vite 前端
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── biome.json
    ├── components.json              # shadcn-vue 配置
    ├── index.html
    └── src/
        ├── main.ts                  # Vue 入口
        ├── App.vue
        ├── router/index.ts          # 路由配置（11 条路由）
        ├── pages/                   # 页面视图
        │   ├── index.vue            # 首页（工作台：模式选择 + 模块入口 + 知识库统计）
        │   ├── login/index.vue      # 登录页（GitHub OAuth）
        │   ├── auth/callback.vue    # OAuth 回调处理
        │   ├── chat/index.vue       # 自由问答（SSE 流式）
        │   ├── teach/index.vue      # 教学模式（SSE 流式，苏格拉底引导）
        │   ├── solution/index.vue   # 方案模式（WebSocket 实时进度）
        │   ├── example/[id].vue     # 例题详情
        │   ├── archive/[id].vue     # 历史归档详情
        │   ├── knowledge/index.vue  # 知识库管理（CRUD + 搜索 + 浏览）
        │   ├── apikeys/index.vue    # API Key 管理（多服务商支持）
        │   └── settings/index.vue   # 设置页
        ├── components/              # 业务组件
        │   ├── ui/                  # shadcn-vue 组件（精简后保留 22 个）
        │   ├── AppLayout.vue        # 应用布局（含侧边栏）
        │   ├── AppSidebar.vue       # 侧边栏导航
        │   ├── NavUser.vue          # 用户信息（头像/登出）
        │   ├── ChatArea.vue         # 对话区域
        │   ├── Bubble.vue           # 消息气泡
        │   ├── UserStepper.vue      # 用户步骤引导
        │   ├── VersionSwitcher.vue  # 版本切换
        │   ├── ServiceStatus.vue    # 服务状态指示
        │   ├── ThemeToggle.vue      # 主题切换
        │   └── ArrayEditor.vue      # 可复用数组编辑器
        ├── composables/             # 组合式函数
        │   ├── useStreamChat.ts     # chat/teach 共用 SSE 流式逻辑
        │   ├── useTypewriter.ts     # 打字机效果
        │   └── useTheme.ts          # 主题管理
        ├── stores/                  # Pinia 状态管理
        │   ├── auth.ts              # 认证状态
        │   ├── chatSession.ts       # 聊天会话
        │   ├── task.ts              # 任务状态
        │   └── archive.ts           # 历史归档
        ├── apis/                    # HTTP API 调用
        │   ├── authApi.ts
        │   ├── chatApi.ts
        │   ├── apiKeyApi.ts
        │   ├── knowledgeApi.ts
        │   └── commonApi.ts
        ├── types/                   # TypeScript 类型定义
        │   ├── interface.ts
        │   ├── enum.ts
        │   ├── const.ts
        │   └── response.ts
        ├── config/                  # 配置文件
        │   └── styles.ts            # 统一 Tailwind 样式常量
        ├── utils/                   # 工具函数
        │   └── request.ts           # axios 请求封装
        ├── lib/                     # shadcn 工具
        │   └── utils.ts
        └── assets/                  # 静态资源
```

---

## LangGraph Multi-Agent Architecture

### AgentState

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    mode: Literal["teach", "execute"]
    session_id: str

    # 问题理解
    problem_raw: str
    problem_type: str              # optimization/prediction/evaluation/...
    problem_complexity: Literal["simple", "composite", "innovative"]
    data_dependency: Literal["theoretical", "given_data", "self_collect"]

    # KB 上下文（tag 精确匹配 + 语义近邻互补）
    kb_methods: list[dict]
    kb_papers: list[dict]
    kb_templates: list[dict]
    kb_problems: list[dict]

    # 动态执行计划
    execution_plan: list[str]      # ["analysis", "modeling", "solving", ...]
    current_step_index: int
    retry_count: int
    max_retries: int

    # 各 Agent 输出
    analysis_output: str | None
    model_output: str | None
    preprocessed_data: str | None  # 数据预处理节点输出
    solving_output: str | None
    verification_output: str | None
    writing_output: str | None

    # 回退控制
    verification_passed: bool | None
    verification_feedback: str | None
    rollback_target: str | None

    # 用户 API Key 配置 / 题目数据附件 / 导出文件
    api_key_config: dict | None
    data_files: list[dict]
    data_files_dir: str
    export_files: list[dict] | None

    # 最终输出
    final_response: str | None
```

> 进度事件不走 State——由 `node_helpers._pub_event` 直接发 Redis Pub/Sub（WS 推送）+ 事件日志文件。

### 图拓扑

```
START → classify_problem → retrieve_knowledge → plan_execution
                                                       │
                                    route_to_first_agent（条件边）
                                                       │
     ┌──────────────┬──────────────┬───────────────┼───────────────┬──────────────┬──────────────┐
     ▼              ▼              ▼               ▼               ▼              ▼              ▼
analysis_agent modeling_agent data_preprocessing solving_agent verification_ agent export_results writing_agent
                                       _agent                          agent
     │              │              │               │               │              │              │
     └──────────────┴──────────────┴───────────────┼───────────────┴──────────────┴──────────────┘
                                                       │
                          after_agent_router（每个 agent 完成后的条件边）:
                            → 按 plan 到下一个 agent
                            → rollback_target 非空且未超重试上限: 回退一次
                            → plan 完成: format_response
                                                       │
                                                       ▼
                                              format_response → END
```

> 路由真源：`core/router.py` 的 plan 步骤名 → 节点名映射，`workflow.py` 与
> `after_agent_router` 共用同一张表，加 agent 只改一处。

### Tool 分配

实际工具集（`backend/app/tools/`，共 8 个）：

| 工具 | 说明 |
|-------|------|
| `search_method_cards` / `search_similar_papers` / `get_analysis_template` | 知识库检索（kb_tools.py，LLM bind_tools） |
| `sympy_compute` | 符号/数值计算：求导、积分、代数/ODE 求解、极限、泰勒、矩阵（math_tools.py） |
| `solve_optimization` | LP/QP/IP(MIP)/SOCP 求解（cvxpy，含 SymPy→cvxpy 桥接） |
| `run_code` | 沙箱代码执行（subprocess/Docker 双后端，网络阻断 + 超时/内存限制） |
| `ask_user` | 澄清交互（信息不足时弹出选项卡片） |
| `web_search` | DuckDuckGo 联网搜索 |

> chat 模式通过 `llm.bind_tools()` 全量挂载；solution 流水线的 solving/verification
> 节点使用 `run_code` + 数学工具。早期计划中的 `compare_methods` /
> `install_package` / `generate_synthetic_data` 未实现。

---

## 后端 API 设计

### REST

| Method | Path | 说明 |
|--------|------|------|
| `POST` | `/api/tasks` | 创建建模任务 |
| `GET` | `/api/tasks/{id}` | 获取任务详情 |
| `GET` | `/api/tasks/{id}/messages` | 获取历史消息 |
| `POST` | `/api/tasks/{id}/cancel` | 取消任务 |
| `GET` | `/api/tasks` | 任务列表 |
| `POST` | `/api/files/upload` | 上传文件 |
| `GET` | `/api/files/{id}` | 下载文件 |
| `GET` | `/api/apikeys` | API Key 列表 |
| `POST` | `/api/apikeys` | 添加 API Key |
| `DELETE` | `/api/apikeys/{id}` | 删除 API Key |
| `GET` | `/api/apikeys/mine` | 获取当前激活的 Key |
| `POST` | `/api/apikeys/quick` | 快速激活 Key |
| `GET` | `/api/knowledge/search` | 知识库搜索（query expansion + LLM rerank + 结果缓存） |
| `GET` | `/api/knowledge/stats` | 知识库统计 |
| `POST` | `/api/knowledge/reindex` | 触发重新索引 |
| `GET` | `/api/knowledge/methods\|papers\|templates\|problems` | 知识库内容列表/详情/raw |
| `POST` | `/api/knowledge/upload` | 上传资料（PDF/OCR/Excel/DOCX 解析 → LLM 提取） |
| `GET` | `/api/health` | 服务健康检查 |
| `GET` | `/api/sandbox/status` | 沙箱执行模式（docker / subprocess） |
| `POST` | `/api/chat` | SSE 流式对话（chat/learning 多模式，含 LLM 工具调用：KB 检索 + 数学计算 + 联网搜索） |

### 学习系统 / 画像 / 会话 / 导出（2026-07 后新增，共 30+ 路由）

| 分组 | 路径前缀 | 说明 |
|------|---------|------|
| 学习 | `/api/learning/*` | 学习路径生成、单元内容、下一条推荐、题库（bank/practice/answer/mistakes） |
| 画像 | `/api/profile/*` | 学习画像、进度统计、掌握度、成就 Ack |
| 会话 | `/api/conversations/*` | 会话 CRUD + 消息同步（SQLite 持久化，懒加载） |
| 导出 | `/api/export/*` | 交付物导出（Markdown / Word / Excel / CSV / ZIP） |

### WebSocket

| Path | 说明 |
|------|------|
| `WS /api/ws` | 实时推送 agent 执行消息 |

### Auth

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/auth/login` | 获取 GitHub 授权 URL |
| `GET` | `/api/auth/callback` | GitHub OAuth 回调（交换 code 获取 token） |
| `GET` | `/api/auth/user` | 获取当前登录用户信息 |
| `POST` | `/api/auth/logout` | 登出 |

---

## 前端页面清单

| 路径 | 页面 | 功能 | 状态 |
|------|------|------|------|
| `/` | 首页 | 模式选择 + 模块入口 + 知识库统计 + API Key 快速配置 | ✅ |
| `/login` | 登录 | GitHub OAuth 登录 | ✅ |
| `/auth/callback` | OAuth 回调 | 处理 GitHub 授权码，获取用户信息 | ✅ |
| `/chat` | 自由问答 | SSE 流式对话，支持多轮上下文 + 工具调用 | ✅ |
| `/solution` | 方案模式 | WebSocket 实时显示 agent 执行进度 + 论文工作台 | ✅ |
| `/knowledge` | 知识库 | 方法卡片/论文/模板/真题的 CRUD + 搜索 + 浏览 + 导入 | ✅ |
| `/apikeys` | API Key 管理 | 多服务商支持，含预设配置和自定义 | ✅ |
| `/settings` | 设置 | 用户偏好设置 | ✅ |
| `/learn` | 学习工位 | 技能树导航 + 智能体对话式讲解（61 个学习单元） | ✅ |
| `/learn/:unitId` | 学习单元 | Markdown 文档（划词→问AI）+ 目录 + AI 助手 + 单元自测 | ✅ |
| `/practice` | 训练场 | 183 道选择题题库 + 错题本 + AI 侧边答疑 | ✅ |
| `/progress` | 成长档案 | 学习统计、热力图、成就勋章、待复习提醒 | ✅ |

> 说明：早期计划的 `/teach`（教学模式）、`/example/:id`（例题）、`/archive/:id`（历史归档）三个页面**从未实现或已废弃**——teach 模式是 `/api/chat` 的 mode 参数能力；example 页面无后端接口支撑，已于 2026-09 作为死代码删除（git 历史可查）；历史归档由侧边栏会话列表承担。

---

## 实施阶段

### Phase 0 — 脚手架 + 知识库骨架 (已完成 ✅)

**目标**: 前后端骨架可启动 + 知识库可检索

1. ✅ 后端: Poetry + FastAPI 骨架，`backend/app/main.py` 可启动
2. ✅ 前端: pnpm 安装全部依赖，Vite 可启动
3. ✅ shadcn-vue 初始化 + 精简 UI 组件（清理死代码后保留 22 个）
4. ✅ 知识库 Schema (Pydantic) + Loader (YAML) + Embedder + Indexer + Retriever
5. ✅ 首批知识内容: 20 张方法卡片 + 5 篇论文 + 3 个模板（**P0 目标已达标**）
6. ✅ ChromaDB 向量化管道（含增量索引）
7. ✅ Docker Compose 文件 (backend + frontend + redis)
8. ✅ 启动脚本 `start.py`（install/start/stop 三合一）+ `start.bat` 转发

**可交付**: `docker-compose up` 全栈启动；`GET /api/health` 返回 200

### Phase 1 — 前端壳 + 后端编排核心 (已完成 ✅)

**目标**: 前端主要页面能渲染，后端 LangGraph 图能走通分类→检索→分析

**前端**: Router + 路由配置 / 首页 / Chat 页面 / Teach 页面 / Login 页面 / WebSocket 基础连接 / 知识库管理 / API Key 管理

**后端**: AgentState + StateGraph / classify_problem / retrieve_knowledge / plan_execution / analysis_agent / WebSocket 端点 / tasks CRUD / SSE 流式对话

**可交付**: 前端输入问题 → WS 推送分类结果 → Chat/Teach 页面展示输出

### Phase 2 — 建模 + 求解 + Notebook (已完成 ✅)

**目标**: 完整的建模流水线 + Notebook 渲染

**前端**: Solution 工作区页面（实时进度可视化）/ NotebookArea + NotebookCell / Files + Tree

**后端**: modeling_agent / sandbox / solving_agent (ReAct) / 代码执行结果推送

**可交付**: 建模问题 → 前端展示模型公式 + 代码 + 执行结果（Notebook 格式）

### Phase 3 — 验证 + 写作 + 回退 (已完成 ✅)

**目标**: 全部 5 Agent 就位，验证回退循环，论文输出

**后端**: verification_agent / Command 回退逻辑 / writing_agent / 论文 LaTeX 渲染

**前端**: 论文预览页面 / 回退状态展示 / 消息下载功能

**可交付**: 全流程 — 问题 → 实时展示进度 → 验证(含回退) → 论文

### Phase 4 — 双模式完善 + 知识库扩充 (预计 3-4 天)

**目标**: 教学模式深度可用，知识库已达到 P0 标准（✅ 2026-07-23）

1. 教学模式 prompt 精细化（苏格拉底式追问策略）
2. 前端模式切换体验打磨
3. ✅ 知识库扩充至 **20 张方法卡片 + 5 篇论文 + 3 个模板**（已完成）
4. Example 页面（3 道例题 + 配图）
5. 索引构建与冒烟验证

**可交付**: `/teach` 引导式提问质量达标；`/solve` 完整方案输出；知识库检索有效

### Phase 5 — 持续完善

1. 知识库扩充（P1/P2 → 40-50 张卡片）
2. LLMFactory 多提供商性能调优
3. 性能优化（LLM 缓存、并行检索）
4. Docker 沙箱升级
5. 测试覆盖
6. **工具集扩充**：数学计算 ✅（SymPy + cvxpy）；候选 P1 — 数据获取（WorldBank/FRED）/ 网络检索（firecrawl MCP）/ 数值仿真（ODE/PDE 求解器）

### P0 数学计算工具（2026-07-23 上线）

为补足 LLM 在精确符号与数值计算上的短板，新增两个 LangChain BaseTool，chat/teach 模式通过 `llm.bind_tools()` 自动挂载：

| 工具 | 输入 | 输出 | 适用 |
|------|------|------|------|
| `sympy_compute` | expression / operation / variable / extra | LaTeX + 文本双形式结果 | 求导、积分（不定/定）、代数/ODE 求解、极限、泰勒展开、化简、因式分解、展开、矩阵特征值 |
| `solve_optimization` | problem_type (LP/QP/IP/SOCP) / sense / objective / variables / constraints | 状态、最优值、每变量数值 | 资源分配、运输问题、投资组合、排产调度、整数规划(MIP) |

**关键设计**：
1. **结构化输入**（Pydantic schema）— LLM 不会被 Python 语法坑（变量声明、import、循环）
2. **错误友好** — 任何解析/求解异常被捕获，转可读消息回灌给 LLM，让 LLM 自我修正
3. **SymPy → cvxpy 桥接** — `_sympy_to_cvxpy()` 把 LLM 写的数学表达式自动转 cvxpy，LLM 不必懂 cvxpy API
4. **IP 求解器自适应** — cvxpy 1.5+ 内置 SCIPY(HiGHS)；优先级 SCIPY → ECOS_BB → SCIP → SCS；缺求解器时给出明确 pip 安装指引

**P0 不做 MCP**：math_agent 作为 MCP server 价值低（KB 检索已通过 LangChain Tool 暴露）；候选 MCP 客户端方向：`firecrawl-search` / `arxiv` / `fetch`（P1 阶段考虑）

---

## 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 前端 UI | shadcn-vue + Tailwind（非 Element Plus） | 与源项目一致，现代设计，Tree-shaking 好 |
| 前端包管理 | pnpm | 与源项目一致 |
| 后端 | LangGraph + FastAPI（自主设计） | 动态编排+回退远优于源项目的顺序调用 |
| 路由方式 | 条件边 + plan 驱动的节点映射（`core/router.py` 单一真源） | 加 agent 只改一处；Command API 在 7 节点规模下条件边更直读 |
| Agent 数量 | 7 个 + 编排节点（classify/retrieve/plan/format） | 分析→建模→数据预处理→求解→验证→结果导出→写作；验证失败可回退一次 |
| WebSocket | Redis Pub/Sub 解耦 | 匹配前端 TaskWebSocket；支持水平扩展 |
| 代码沙箱 | subprocess → Docker | 渐进式策略 |
| 启动方式 | `python start.py`（install/start/stop 子命令，跨平台） | 单入口消除三套操作系统脚本的逻辑漂移 |

---

## RAG 知识库子系统设计

> 内存: KB-RAG-001 | 状态: 代码就绪、源数据 P0 达标（✅ 20 卡片 + 5 论文 + 3 模板） | 更新时间: 2026-07-23

> ✅ **数据初始化状态（2026-07-23 更新）**：`knowledge_base/` 已达标 P0 标准（20 张方法卡片 + 5 篇论文 + 3 个模板）。方法卡片覆盖优化(8)、预测(3)、评价(5)、统计(2)、分类(1)、聚类(1)、图论(1)。论文覆盖国赛(3)、美赛(1)、华中赛(1)。`data/chroma_db/` 依赖运行索引构建。检索器已实现混合检索（语义+标签+MMR+关键词兜底）。

### 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户 / 前端                            │
│        ┌──────────────────────────────────────┐         │
│        │  /api/knowledge/*  (管理 API)         │         │
│        │  /api/tasks       (Agent 调用)       │         │
│        └──────────┬───────────────────────────┘         │
└───────────────────┼─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│                 FastAPI 后端                              │
│                                                          │
│  ┌─────────────────┐  ┌──────────────────────────────┐  │
│  │ knowledge/       │  │ core/agents/                 │  │
│  │  schemas.py ✅   │  │  analysis_agent.py           │  │
│  │  loader.py   ✅  │  │  modeling_agent.py           │  │
│  │  embedder.py ✅  │  │  ...                          │  │
│  │  indexer.py  ✅  │  │      ↓ 调用                   │  │
│  │  retriever.py✅  │  │                              │  │
│  │  reranker.py 🆕  │  │  ┌──────────────────────┐   │  │
│  │  chain.py    🆕  │──┤  │ tools/kb_tools.py ✅ │   │  │
│  │  api.py      🆕  │  │  │ search_method_cards  │   │  │
│  └─────────────────┘  │  │ search_similar_papers │   │  │
│                       │  │ get_analysis_framework│   │  │
│                       │  └──────────┬───────────┘   │  │
│                       │             │                │  │
│                       │  ┌──────────▼───────────┐   │  │
│                       │  │ RAG Chain (chain.py)  │   │  │
│                       │  │ 检索 →重排→格式化→生成 │   │  │
│                       │  └──────────────────────┘   │  │
│                       └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│                   数据层                                   │
│  ┌─────────────────┐  ┌──────────────────────────────┐  │
│  │ knowledge_base/  │  │ data/chroma_db/              │  │
│  │  methods/*.yaml  │  │  (向量持久化)                  │  │
│  │  papers/*.yaml   │  │                               │  │
│  │  templates/*.yaml│  │                               │  │
│  └─────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 文件清单

```
backend/app/
├── knowledge/
│   ├── __init__.py          # 导出公共接口
│   ├── schemas.py           # [已有] Pydantic 数据模型
│   ├── loader.py            # [已有] YAML 加载器
│   ├── embedder.py          # [已有] 支持增量索引+可配置 embedding
│   ├── indexer.py           # [已有] 支持 --incremental 模式
│   ├── retriever.py         # [已有] 混合检索 + MMR + 关键词兜底
│   ├── reranker.py          # 🆕 LLM 重排序模块
│   ├── chain.py             # 🆕 RAG Chain (LangChain Runnable)
│   └── api.py               # 🆕 知识库管理 API 路由
│
├── tools/
│   ├── __init__.py          # [已有]
│   └── kb_tools.py          # [已有] 封装为 LangChain Tool
│
├── core/
│   └── prompts/
│       ├── __init__.py      # [已有]
│       ├── analysis.py      # 🆕 分析 Agent Prompt 模板
│       ├── modeling.py      # 🆕 建模 Agent Prompt 模板
│       └── rag.py           # 🆕 通用 RAG 上下文格式化模板
│
└── api/
    ├── router.py            # [已有] 注册 knowledge 路由
    └── knowledge_routes.py  # [已有] 知识库 CRUD + 搜索 API
```

### 实施步骤

#### Step 1: 增强 HybridRetriever `retriever.py` ✅ 已完成

**已实现功能**:
- ✅ 返回结果带相关性分数
- ✅ MMR (Maximum Marginal Relevance) 去重
- ✅ 向量搜索支持元数据过滤 (type/year/competition/quality_rating)
- ✅ 关键词兜底搜索（向量索引不可用时全量子串匹配）

#### Step 2: LLM 重排序 `reranker.py` 🆕 🟡 中优先级

用 LLM 对候选文档做 pairwise 比较，进一步优化检索精度。

```python
class LLMReranker:
    """用 LLM 对检索结果重排序"""

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def rerank(
        self, query: str, documents: list[Document], top_k: int = 5
    ) -> list[Document]:
        """
        流程:
        1. 对每个 doc 构造评分 prompt: "文档与问题的相关性(1-5)"
        2. LLM 批量打分
        3. 按分数降序取 top_k
        """
        ...
```

**评分 Prompt 设计**:
```
评估以下文档与用户问题的相关性 (1-5 分):
用户问题: {query}
---
文档 [{i}]: {doc.page_content[:500]}
---
返回 JSON: [{"index": 0, "score": 4, "reason": "..."}, ...]
```

---

#### Step 3: LangChain Tool 封装 `tools/kb_tools.py` ✅ 已完成

Agent 通过 Tool 调用知识库。已实现 3 个 Tool：

```python
from langchain_core.tools import tool

@tool
def search_method_cards(query: str, problem_type: str = "") -> str:
    """搜索数学建模方法卡片。输入问题描述或关键词，返回最匹配的方法原理、
    适用条件、典型场景和代码示例。
    """
    ...

@tool
def search_similar_papers(query: str, problem_type: str = "") -> str:
    """搜索历年竞赛真题论文。输入问题描述，返回相似赛题的结构化分析。"""
    ...

@tool
def get_analysis_framework(problem_type: str) -> str:
    """获取问题分析框架模板。根据问题类型返回对应的分析步骤框架。"""
    ...
```

**Tool → Agent 绑定**:

```python
# core/nodes.py 中创建 agent 节点时
analysis_llm = llm.bind_tools([
    search_method_cards,
    search_similar_papers,
    get_analysis_framework,
])
```

---

#### Step 4: RAG Chain `chain.py` 🆕 🔴 高优先级

将检索→重排→格式化→生成串联为 LangChain Runnable。

```python
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

def create_rag_chain(
    llm: BaseChatModel,
    retriever: BaseRetriever,
    prompt_template: ChatPromptTemplate,
) -> Runnable:
    """创建标准 RAG 链: 检索 → 格式化上下文 → 注入 Prompt → LLM 生成"""
    return (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough(),
        }
        | prompt_template
        | llm
        | StrOutputParser()
    )

def format_docs(docs: list[Document]) -> str:
    """将检索结果格式化为 LLM 可消费的上下文字符串"""
    type_labels = {
        "method_card": "方法卡片",
        "paper": "真题论文",
        "template": "分析框架",
    }
    parts = []
    for i, doc in enumerate(docs):
        meta = doc.metadata
        label = type_labels.get(meta.get("type", ""), "文档")
        score = meta.get("score", "")
        score_str = f" (相关性: {score:.2f})" if score else ""
        parts.append(
            f"### [{label}] {meta.get('name', '')}{score_str}\n"
            f"{doc.page_content}\n"
        )
    return "\n---\n".join(parts)
```

---

#### Step 5: Prompt 模板 `core/prompts/` 🆕 🟡 中优先级

为每个 Agent 编写含 RAG 上下文的 System Prompt。

```python
# core/prompts/analysis.py
ANALYSIS_SYSTEM_PROMPT = """你是一个数学建模问题分析专家。你的任务是基于知识库上下文，
对用户问题做结构化分析。

## 可用知识库上下文
{context}

## 分析要求
1. **问题类型判定**: 明确问题属于哪种数学建模类型(优化/预测/评价/...)
2. **关键要素提取**: 决策变量、目标函数、约束条件、隐含假设
3. **方法推荐**: 基于知识库推荐 2-3 个可能适用的方法，说明理由
4. **难度评估**: 单模型可解 / 需组合模型 / 需创新建模

## 引用规范
- 引用知识库内容时标注来源，如 [mc_001]、[paper_2023C_01]
- 如果知识库上下文不足以覆盖当前问题，基于你的数学知识补充
"""
```

---

### 与 LangGraph Agent 集成

在 `retrieve_knowledge` 节点中调用检索器，结果写入 AgentState：

```python
def retrieve_knowledge(state: AgentState) -> dict:
    """检索知识库: 语义搜索 + 标签过滤 → 写入 state"""
    problem_type = state["problem_type"]
    query = state["problem_raw"]

    # 并行检索三层知识库
    methods = retriever._get_relevant_documents(
        query, metadata_filter={"type": "method_card"},
        problem_type=problem_type, k=5
    )
    papers = retriever._get_relevant_documents(
        query, metadata_filter={"type": "paper"},
        problem_type=problem_type, k=3
    )
    templates = retriever._get_relevant_documents(
        query, metadata_filter={"type": "template"},
        problem_type=problem_type, k=2
    )

    return {
        "kb_methods": [doc_to_dict(d) for d in methods],
        "kb_papers": [doc_to_dict(d) for d in papers],
        "kb_templates": [doc_to_dict(d) for d in templates],
    }
```

流程示意:
```
classify_problem → 识别 problem_type = "optimization"
        │
        ▼
retrieve_knowledge → 三层检索 (并行)
        │              search_method_cards("资源分配优化", "optimization")
        │              search_similar_papers("资源分配", "optimization")
        │              get_analysis_framework("optimization")
        │              结果写入 state.kb_methods/kb_papers/kb_templates
        ▼
analysis_agent → System Prompt 注入 KB 上下文 → 结构化分析输出
```

---

### 实施优先级与工时

| Step | 内容 | 优先级 | 工时 | 依赖 |
|------|------|--------|------|------|
| Step 1 | `retriever.py` 增强 (分数/MMR/过滤/关键词兜底) | ✅ 完成 | - | 无 |
| Step 3 | `tools/kb_tools.py` LangChain Tool 封装 | ✅ 完成 | - | Step 1 |
| Step 3b | `tools/math_tools.py` 数学计算 (SymPy + cvxpy) | ✅ 完成 | 2026-07-23 | Step 3 |
| Step 4 | `chain.py` RAG Chain | 🟡 中 | 0.5d | Step 1 |
| Step 5 | Prompt 模板 (RAG 上下文格式化) | 🟡 中 | 0.5d | Step 4 |
| Step 2 | `reranker.py` LLM 重排序 | 🟡 中 | 0.5d | Step 1 |
| Step 6 | 知识库数据扩充（20 卡片 + 5 论文 + 3 模板） | ✅ 完成 | 2026-07-23 | 无 |
| Step 7 | 增量索引构建与冒烟验证 | 🔴 高 | 0.5d | Step 6 |

**执行顺序**: Step 6 → Step 7 → Step 4 → Step 5 → Step 2

核心回路 (Step 4→5) 打通后，Agent 即具备完整 RAG 能力。

---

## 如何录入知识

提供三种方式向知识库添加数学建模资料：

### 方式一：LLM 辅助批量导入（推荐）

适合：手头有教材段落、论文摘要、笔记等原始文本

```bash
# 1. 将原始资料 (.txt/.md) 放入 knowledge_base/_import_queue/
#    每个文件放一种方法/一篇论文/一个模板的描述文本

# 2. 运行 LLM 批量提取
cd backend
python -m scripts.import_knowledge --type method --batch    # 批量导入方法卡片
python -m scripts.import_knowledge --type paper --batch     # 批量导入论文
python -m scripts.import_knowledge --type template --batch  # 批量导入模板

# 3. 单文件导入
python -m scripts.import_knowledge --input notes.txt --type method --name "粒子群算法"

# 4. 增量更新向量索引
python -m app.knowledge.indexer --incremental

# 5. 在 /knowledge 页面搜索验证
```

LLM 会自动从原始文本中提取：方法名、原理、公式、适用条件、代码示例等结构化字段。

### 方式二：空白模板生成

适合：想手动编写知识卡片

```bash
cd backend

# 生成方法卡片模板
python -m scripts.generate_template method --name "粒子群算法" --category optimization

# 生成论文模板
python -m scripts.generate_template paper --title "2024国赛A题" --year 2024 --competition 国赛 --problem-id A

# 生成分析框架模板
python -m scripts.generate_template template --name "图论问题分析框架"
```

模板生成后，手动编辑 YAML 文件填写内容，然后运行增量索引。

### 方式三：手动编写 YAML

适合：精确控制内容

目录结构：
```
knowledge_base/
├── methods/                  # 方法卡片（按类别分子目录）
│   ├── optimization/
│   │   └── linear_programming.yaml
│   ├── prediction/
│   │   └── arima.yaml
│   └── evaluation/
│       └── ahp.yaml
├── papers/                   # 真题论文（按竞赛分子目录）
│   └── 国赛/
│       └── 2023C_vegetable_pricing.yaml
├── templates/                # 分析框架
│   └── optimization_framework.yaml
└── _import_queue/            # 待导入的原始文本（临时）
    └── README.md
```

YAML 格式参考已有文件，核心结构：

**方法卡片** `knowledge_base/methods/<类别>/<名称>.yaml`:
```yaml
method_card:
  id: "mc_011"              # mc_ + 三位数字，全局唯一
  name: "方法名"
  category: ["优化", "启发式"]
  principle: |              # 核心原理（支持多行）
    详细描述...
  formulas: []              # 公式列表
  applicable_when: []       # 适用条件
  typical_scenarios: []     # 典型场景
  common_mistakes: []       # 常见误用
  code_snippets: []         # 代码示例
  related_cards: []         # 关联卡片 ID
```

**真题论文** `knowledge_base/papers/<竞赛>/<年份+题号>.yaml`:
```yaml
paper:
  id: "paper_002"
  year: 2024
  competition: "国赛"
  problem_id: "A"
  title: "论文标题"
  tags:
    problem_type: ["优化"]
    core_models: ["方法名"]
  analysis: {...}           # 问题拆解
  model: {...}              # 建模思路
  evaluation: {...}         # 优缺点评价
```

### 完整工作流

```
原始资料 ──→ 方式一 (LLM提取) ──→ 自动生成YAML ──→ indexer --incremental ──→ 可搜索
           │
           ├──→ 方式二 (空模板) ──→ 手动填充 ──→ indexer --incremental ──→ 可搜索
           │
           └──→ 方式三 (手写)   ──→ 直接编写 ──→ indexer --incremental ──→ 可搜索
```

---

## 风险

| 风险 | 缓解 |
|------|------|
| 前端复刻不完整 | 以实际实现为准；缺失组件按需安装 |
| WebSocket 消息格式不匹配 | Phase 1 已做 WS 联调验证 ✅ |
| LLM 数学公式/代码错误 | 验证 Agent 做 gate；求解 Agent ReAct 循环自纠错 |
| 知识库数据不足影响答案质量 | ✅ 已扩充至 P0 标准（20 卡片 + 5 论文 + 3 模板）；端到端任务已验证 |
| 国产模型 API 可用性 | 已锁定国产栈（DeepSeek/Qwen/GLM/豆包），LLMFactory 支持多提供商切换 |

---

## Verification

1. **Phase 0**: `docker-compose up` 全栈启动；`/api/health` 200；`/api/tasks` CRUD 正常；知识库统计 API 返回正确数量
2. **Phase 1**: 前端输入问题 → WS 推送进度 → Chat/Teach 页面展示分析结果；SSE 流式输出正常
3. **Phase 2**: LP 问题 → Notebook 区域展示模型 LaTeX + 代码 + 执行结果
4. **Phase 3**: 人为缺陷模型 → 验证捕获 → 回退提示 → 修正 → 论文输出
5. **Phase 4**: teach 模式无直接答案；solve 模式完整方案；知识库检索返回有效结果；例题页可用
6. **端到端**: 完整国赛真题走通全流程，人工评审输出质量

---

*文档持续更新，随开发进展同步。*
