# MathModelAgent — 数学建模多智能体学习与辅助平台

基于 FastAPI + LangGraph + Vue 3 的数学建模全流程平台，覆盖「学 → 练 → 做」完整闭环，学习过程中随时可以「问 AI」。7 位智能体各司其职，服务于建模手、编程手、论文手三人团队。

---

## 🚀 快速开始（三步装好）

### 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | ≥ 3.11 | 后端 |
| Node.js | ≥ 18 | 前端（CI 使用 Node 22） |
| pnpm | ≥ 10 | 前端包管理器（`npm i -g pnpm` 或 `corepack enable`） |
| Docker | 可选 | 仅沙箱硬隔离需要；`install --docker` 可构建沙箱镜像 |

### 1. 克隆

```bash
git clone https://github.com/zhang66633/NB_project.git
cd NB_project
```

### 2. 一键安装

```bat
python start.py install     REM Windows / Linux / macOS 通用
```

```bash
python3 start.py install          # 可选 --docker 构建沙箱镜像并启用硬隔离
```

脚本自动完成：环境检查 → 创建 `.venv` → 安装后端依赖 → 生成 `backend/.env`（随机 `JWT_SECRET`、端口 8002、沙箱默认 subprocess）→ 安装前端依赖。

### 3. 启动

```bat
start.bat                  REM Windows 一键启动前后端（等价 python start.py）
```

```bash
python3 start.py           # Linux / macOS；stop 用 python start.py stop
```

打开 **http://localhost:5174** → 首页「API Key」输入框粘贴你的 DeepSeek / OpenAI 兼容 Key 即可开始使用（Key 仅保存在本机 `backend/data`，不上传）。

### 手动安装（可选）

```bash
cd backend
cp .env.example .env           # 可选；建议把 JWT_SECRET 改为随机值
python -m venv .venv && .venv/bin/pip install -e .
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002

cd ../frontend
pnpm install
pnpm dev                       # http://localhost:5174（/api 代理到 127.0.0.1:8002）
```

### 常见问题

- **没配 API Key 能用吗**：能——学习中心与题库完全可用；AI 对话、方案生成、知识库向量化需要先配 Key（网页首页粘贴，或 `backend/.env` 填 `OPENAI_API_KEY`）。
- **不登录能用吗**：能——访客模式免登录全功能可用，对话、任务、学习记录都持久化在本机（访客数据共享一个默认桶）；GitHub 登录仅限项目贡献者白名单（多端同步用）。
- **数据存哪 / 会丢吗**：对话、任务、学习记录、Key 全部落盘在 `backend/data/`（SQLite / JSON）；聊天另存浏览器 localStorage 并自动同步到服务端，清缓存、换浏览器也不丢。
- **沙箱是什么模式**：一键安装默认 subprocess（网络阻断 + 60s 超时 + 内存限制，适合个人与可信输入）；执行 `python start.py install --docker` 构建镜像后切换 Docker 硬隔离（`--network=none` 等），公开部署推荐此模式。
- **向量索引要手动建吗**：不用——首次启动自动检测缺失并在后台重建。
- **PDF OCR**：沙箱镜像已内置 tesseract 与 poppler；手动安装（主机模式）如需本地 OCR 请自行安装这两个系统依赖。

---

## 🧑‍🤝‍🧑 智能体团队

每个智能体都有名字、emoji 和教学风格，学生始终知道「哪位老师在教我」：

| | 智能体 | 职责 | 教学风格 |
|---|--------|------|----------|
| 🧭 | **导航员** | 诊断水平 · 规划路径 · 调度智能体 | "别急，先看看你在哪、要去哪" |
| 🔍 | **分析师** | 问题拆解 · 题意分析 · 假设提炼 | "把大问题拆成小问题" |
| 🧩 | **建模师** | 模型原理 · 方法选择 · 公式推导 | "数学就是把世界装进方程里" |
| 💻 | **求解器** | 代码实现 · 算法调试 · 数据处理 | "公式漂亮没用，跑得通才算" |
| 🔬 | **检验员** | 模型验证 · 灵敏度分析 · 找漏洞 | "好模型经得起拷问" |
| ✍️ | **编辑** | 论文写作 · 图表制作 · 排版润色 | "你的模型很厉害，但得让人看得懂" |
| 📊 | **管家** | 进度追踪 · 遗忘提醒 · 成就记录 | "你的每一点进步，我帮你记" |

智能体不是冷冰冰的工具——选中文档文字可以随手「问AI」，智能体立刻解释；听不懂时它会推荐 B 站视频、GitHub 仓库、教材章节。

---

## 🗺️ 功能导览

### 论文工作台 — 实战解题

| 模式 | 入口 | 说明 |
|------|------|------|
| 💬 自由问答 | `/chat` | SSE 流式对话，多轮上下文，工具调用 |
| 📋 方案模式 | `/solution` | 多智能体流水线（分类→检索→计划→分析→建模→数据预处理→求解→验证→结果导出→论文写作），WebSocket 实时进度 |

另有知识库管理（`/knowledge`）、API Key 管理（`/apikeys`）、设置（`/settings`）。

### 学习中心 — 从入门到竞赛

面向**建模手 · 编程手 · 论文手**三人团队的个性化学习系统：

| 入口 | 路由 | 说明 |
|------|------|------|
| 🎯 学习工位 | `/learn` | 技能树导航 + 智能体对话式讲解 + 61 个真实学习单元 |
| 🎯 学习单元 | `/learn/:unitId` | Markdown 文档（划词→问AI）+ 目录 + AI 助手 + 单元自测 |
| ✏️ 训练场 | `/practice` | 183 道选择题题库 + 错题本 + AI 侧边答疑 |
| 📈 成长档案 | `/progress` | 学习统计、热力图、成就勋章、待复习提醒 |

#### 学习机制

| 机制 | 说明 |
|------|------|
| 🕸️ 技能树 | 61 个学习单元按角色 × 类别组织，含前置依赖与相关卡片关联 |
| 🧠 掌握度追踪 | 练习与学习表现动态升降，艾宾浩斯遗忘衰减（e^(−天数/20)）自动提醒复习 |
| ✏️ 错题本 | 答错自动收录、重做正确自动移除，支持手动增删与「专练错题」 |

#### 学习内容

61 个真实 Markdown 学习单元：

| 类别 | 单元数 | 示例 |
|------|--------|------|
| 优化 | 12 | 线性规划、整数规划、遗传算法、模拟退火 |
| 预测 | 6 | 时间序列、回归分析、灰色预测、神经网络 |
| 评价 | 7 | 层次分析法、模糊综合评价、TOPSIS、熵权法 |
| 统计 | 4 | 假设检验、方差分析、相关分析、主成分分析 |
| 图论 | 3 | 最短路径、网络流、最小生成树 |
| 微分方程 | 2 | 常微分方程、偏微分方程建模 |
| 综合（建模手） | 4 | 排队论、博弈论、元胞自动机、组合模型 |
| 编程实践 | 13 | Python 科学计算、Pandas 数据处理、Matplotlib 可视化、scipy.optimize |
| 论文写作 | 10 | 摘要撰写、论文结构、图表设计 |

每个单元包含 Markdown 文档（公式、代码示例、应用场景）+ 单元自测 + 智能体互动讲解。

---

## ⚙️ 核心能力

- **代码执行沙箱**: Python 数据科学生态（numpy/pandas/matplotlib/sympy/cvxpy/scipy），图表自动内联显示；网络阻断 + 超时/内存限制；可选 Docker 硬隔离
- **竞赛数据文件**: 真题附件（xlsx/csv）自动提取表结构并复制到本地，沙箱内 `pd.read_parquet()` 秒级加载
- **文件上传**: CSV/Excel/TXT/PDF/DOCX 等上传后沙箱内直接读取（20MB、扩展名白名单）
- **联网搜索**: DuckDuckGo 免费搜索，智能体可推荐 B站视频/GitHub仓库/教材资源
- **澄清交互**: LLM 自主判断信息不足时弹出选项卡片，用户选择后继续
- **知识库**: 47 张方法卡片 / 16 篇论文拆解 / 27 道竞赛真题 / 3 套框架模板，多路召回（向量 + BM25 + 标签）→ RRF 融合 → MMR 重排 → 时间衰减
- **交付物导出**: Markdown / Word / Excel / CSV / ZIP 打包下载；PDF 打印导出，图表内联
- **选择题题库**: 183 题覆盖建模/编程/论文三角色，错题本 + AI 答疑
- **用户认证**: GitHub OAuth（贡献者白名单）+ JWT（7天过期）+ 访客模式

---

## 📁 项目结构

```
NB_project/
├── start.py                      # 统一入口：install / start / stop 三个子命令
├── start.bat                     # Windows 转发器（纯 ASCII，逻辑都在 start.py）
├── docker-compose.yml           # 全栈容器化编排（可选）
├── nginx.conf                   # 生产反向代理配置模板（compose 未挂载，按需使用）
├── PLAN.md / RULES.md           # 现行开发权威文档
│
├── backend/                     # FastAPI + LangGraph 后端
│   ├── app/
│   │   ├── main.py              # 入口（启动时自动检测向量索引）
│   │   ├── config.py            # 配置（各 agent 角色模型、沙箱参数）
│   │   ├── api/                 # router(认证/健康/沙箱状态)、chat、tasks、files、ws、
│   │   │                        # knowledge(search/crud/import)、learning(含 quiz)、
│   │   │                        # profile、conversations、export、apikeys
│   │   ├── core/                # LangGraph 流水线：11 节点（分类/检索/规划/分析/建模/
│   │   │                        # 数据预处理/求解/验证/结果导出/论文写作/响应格式化）
│   │   ├── knowledge/           # 混合检索（向量+BM25+标签 → RRF → MMR → 时间衰减）
│   │   ├── sandbox/             # 代码沙箱（subprocess 网络阻断 / Docker 硬隔离双后端）
│   │   ├── tools/               # KB/数学/交互/搜索/代码执行工具
│   │   ├── learning/            # 学习系统：61 单元内容 + 路径生成 + 技能树 + 掌握度追踪 + 题库
│   │   └── services/            # Redis PubSub（fakeredis 回退）+ 会话/成就/记忆等服务
│   ├── knowledge_base/          # 知识数据（YAML 真源，入库 git）
│   │   ├── methods/             # 方法卡片（47 张）
│   │   ├── papers/              # 优秀论文拆解（16 篇）
│   │   ├── problems/            # 竞赛真题（27 道，含附件信息）
│   │   └── templates/           # 解题框架模板（3 套）
│   ├── data/                    # 运行时数据（gitignore：SQLite/JSON/ChromaDB/上传文件）
│   ├── scripts/                 # 工具脚本（真题导入/预计算/端到端测试等）
│   └── tests/                   # 测试套件（pytest + ruff，CI 执行）
│
└── frontend/                    # Vue 3 + Vite + TailwindCSS
    └── src/
        ├── pages/               # index(首页/Key入口) / login / auth-callback /
        │   │                    # chat / solution / knowledge / apikeys / settings /
        │   │                    # learn / learn/[unitId] / practice / progress
        ├── components/          # ChatArea / Bubble / ClarifyCard / ProgressTimeline /
        │   │                    # GuidedCardSelection / LearningDoc / SkillGraph /
        │   │                    # UnitQuizBlock / PaperToolbar / PaperViewer ...
        ├── composables/         # useStreamChat（SSE 流式编排）/ useTypewriter
        ├── stores/              # Pinia: chatSession / task / auth / learning / practice / profile
        ├── apis/                # API 层: learningApi / chatApi / ...
        ├── config/              # navItems（论文工作台 + 学习中心分组导航）
        └── utils/               # markdown(marked+DOMPurify) / exportPaper(打印导出)
```

---

## 🛠️ 技术栈

- **前端**: Vue 3 + Vite 6 + TypeScript + TailwindCSS + Pinia + reka-ui + marked/KaTeX/highlight.js + @tanstack/vue-virtual；图表由后端 matplotlib 生成图片、前端直接展示
- **后端**: FastAPI + LangGraph + LangChain + uvicorn
- **实时**: SSE（对话流式）+ WebSocket（任务进度，Redis PubSub / fakeredis 回退）
- **知识库**: YAML 真源 + ChromaDB（本地持久化，可选 HTTP 模式）+ BM25 + RRF + MMR
- **存储**: SQLite / JSON 本地持久化，无外部数据库依赖
- **LLM**: DeepSeek（默认）/ 任意 OpenAI 兼容接口，按 agent 角色配置模型，写作与求解节点 384K max_tokens
- **安全**: DOMPurify（XSS）+ 路径校验 + JWT 7天过期 + Key base_url SSRF 校验 + 沙箱隔离
- **工程化**: CI（GitHub Actions）= 后端 ruff + pytest / 前端 vue-tsc + biome

---

## 📝 备注

- `backend/data/`（apikeys/sessions/learning.db/practice.db/chroma_db/uploads）含本地运行时数据，已被 `.gitignore` 排除。
- `backend/knowledge_base/` 的 YAML 源文件在 git 中，clone 后启动即自动建索引。
- 默认分支为 `main`。
- 开发以 [PLAN.md](./PLAN.md) 与 [RULES.md](./RULES.md) 为准；其余文档在 `docs/` 分级存放（现行 + 历史归档），索引见 [docs/README.md](./docs/README.md)；早期架构蓝图 [docs/archive/ARCHITECTURE.md](./docs/archive/ARCHITECTURE.md) 已归档（勿作开发依据）。
