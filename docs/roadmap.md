# MathModelAgent — 资源库与开发路线图

> 最后更新: 2026-07-25 (方案模式质量大修 + 路线图同步已完成项)
> 状态: 活跃开发中

---

## 一、开源算法与代码库

| 项目 | 说明 | 链接 | 与系统的关系 |
|------|------|------|-------------|
| **Algorithms_MathModels** | 国赛+美赛核心算法 MATLAB 实现，覆盖 AHP、元胞自动机、神经网络、遗传算法等 | [gitcode 镜像](https://gitcode.com/gh_mirrors/al/Algorithms_MathModels) | 可作为知识库 `methods/` 的补充来源，提取算法原理→YAML 方法卡片 |
| **math-modeling-resources** | 8 大类模型 × 27 个 Python/MATLAB 算法 × 4 个赛事指南，含 AI 辅助工具集 | [GitHub](https://github.com/sixtdreanight/math-modeling-resources) | Python 代码可直接用于 `run_code` 沙箱验证；赛事指南可导入知识库 |
| **modeling-skills-git** | 数学建模技能知识库：题目分析、模型选型、因果推断、科研可视化、论文写作 | [GitHub](https://github.com/halsun2048/modeling-skills-git) | 与 `templates/` 目录高度互补，可提取为分析/建模/写作 Agent 的 prompt 参考 |
| **whut_mcm2020** | 武汉理工大学 2020 集训资料，含美赛 F 奖/华中赛省二等实战经验 | [GitHub](https://github.com/khan-yin/whut_mcm2020) | 实战经验可转化为 `papers/` 条目，供 `search_similar_papers` 检索 |

### 待补充的算法类别（当前知识库缺口）

当前 `knowledge_base/methods/` 已覆盖: 优化(LP/NLP/IP/GA/PSO/SA/DP)、预测(ARIMA/BP/灰色)、评价(AHP/TOPSIS/DEA/熵权/模糊)、统计(PCA/蒙特卡洛)、分类(SVM)、聚类(KMeans)、图论(最短路)。

**尚缺的高频建模方法:**

| 类别 | 缺失方法 | 优先级 |
|------|---------|--------|
| 时间序列 | LSTM、Prophet、小波分析 | 高 |
| 评价 | 层次分析法变体(ANP)、CRITIC、组合赋权 | 高 |
| 优化 | 多目标优化(NSGA-II)、列生成、分支定界 | 中 |
| 预测 | XGBoost、LightGBM、Transformer 时序 | 中 |
| 统计 | 回归分析(多元/Logistic)、假设检验、方差分析 | 高 |
| 图论 | 网络流、最小生成树、PageRank | 中 |
| 机器学习 | 随机森林、DBSCAN、GMM | 中 |
| 微分方程 | SIR/SEIR 传染病模型、Lotka-Volterra、偏微分方程数值解 | 中 |
| 仿真 | Agent-Based Modeling、系统动力学、离散事件仿真 | 低 |

---

## 二、模板资源（LaTeX + Word）

| 类型 | 资源 | 说明 | 集成方式 |
|------|------|------|---------|
| **LaTeX** | [mathmodel-latex-skill](https://github.com/wangling-miao/mathmodel-latex-skill) | MCM/ICM + 国赛双模板，含 XeLaTeX/latexmk 配置、BibTeX、PDF 预检 | 写作 Agent 输出 LaTeX 源码时参考此模板结构 |
| **LaTeX** | [LaTeX Template for CUMCM](https://github.com/personqianduixue/Math_Model) | 国赛标准模板，含封面、摘要、正文结构 | 同上 |
| **Word** | 各大高校模板 | 一般学校数模协会提供 | 用户自行使用，系统输出 Markdown 可转 Word |

### 当前论文输出能力

- 写作 Agent 输出 **Markdown + LaTeX 公式**（KaTeX 渲染）
- 前端支持 **导出 PDF**（浏览器打印对话框）和 **复制 Markdown 源**
- **缺失**: 直接生成 `.docx` / `.tex` 文件下载、LaTeX 编译为 PDF、论文模板选择

---

## 三、真题与优秀论文

### 官方渠道

| 来源 | 内容 | 链接 |
|------|------|------|
| 全国大学生数学建模竞赛官网 | 国赛真题 + 部分优秀论文 | [mcm.edu.cn](http://www.mcm.edu.cn/) |
| COMAP 官网 | 美赛 MCM/ICM 真题 + 官方解答（2000 年至今） | [comap.com](https://www.comap.com/) |
| MCM/ICM 中文站 | 中文翻译版真题 | [mcmicm.org.cn](https://mcmicm.org.cn/) |

### 整理版资源

| 来源 | 内容 | 链接 |
|------|------|------|
| 欧新宇教授网站 | 1998-2015 年真题，带题型分类 + 知识点标签 | [mathmodeling.ouxinyu.cn](http://mathmodeling.ouxinyu.cn/Competition.html) |
| 韩学长 | 国赛 + 美赛历年资料存档 | [GitHub](https://github.com/jshn9515/mathworks2) |

### 当前知识库论文覆盖

`knowledge_base/papers/` 现有 4 篇:
- 国赛: 2020C 信贷决策、2023A 定日镜场、2023C 蔬菜定价
- 美赛: 2021F 高等教育
- 华中赛: 2019 共享单车

**缺口**: 论文数量严重不足（仅 4 篇），`search_similar_papers` 检索效果有限。建议批量导入 20+ 篇覆盖主要题型（优化/预测/评价/统计）的 O 奖/M 奖论文。

---

## 四、系统当前能力矩阵

| 能力 | 状态 | 说明 |
|------|------|------|
| 自由问答 (chat) | ✅ 完成 | SSE 流式、多轮上下文、滑动窗口截断 |
| 教学引导 (teach) | ✅ 完成 | 苏格拉底式提问、不直接给答案 |
| 建模流水线 (solution) | ✅ 完成 | 5 阶段 LangGraph 流水线、WS 实时进度 |
| KB 检索工具 | ✅ 完成 | 方法卡片/真题论文/分析模板，ChromaDB 混合检索 |
| 数学计算工具 | ✅ 完成 | SymPy 符号计算 + cvxpy 凸优化 |
| 澄清交互 (ask_user) | ✅ 完成 | LLM 自主判断、选项卡片、单选/多选 |
| 代码执行 (run_code) | ✅ 完成 | 沙箱隔离、matplotlib 图表、文件引用 |
| 文件上传 | ✅ 完成 | CSV/Excel/TXT/PDF 等，沙箱内可直接读取 |
| 图表内联显示 | ✅ 完成 | run_code 生成的 PNG 直接在气泡中渲染 |
| Web 搜索 | ✅ 完成 | DuckDuckGo 免费搜索，无需 API Key |
| 论文导出 | ⚠️ 基础 | 仅浏览器打印 PDF + 复制 Markdown |
| 用户认证 | ✅ 完成 | GitHub OAuth + JWT + 访客模式 |
| API Key 管理 | ✅ 完成 | 多 Key、多 Provider、按用途分类 |
| 知识库管理 | ✅ 完成 | CRUD + 上传 + LLM 提取 + 向量索引 |

### 4.1 代码沙箱运行环境

`run_code` 工具在独立子进程中执行用户代码，与主进程完全隔离。

**预装可用库:**

| 库 | 版本约束 | 用途 |
|---|---|---|
| matplotlib | 随主环境 | 绑图（自动 Agg 后端，无需 `plt.show()`） |
| numpy | 随主环境 | 数值计算、矩阵运算 |
| scipy | 随主环境 | 科学计算（优化、插值、信号、统计） |
| pandas | 随主环境 | 数据清洗、DataFrame 操作 |
| sympy | 随主环境 | 符号数学（与 `sympy_compute` 工具共享） |
| cvxpy | 随主环境 | 凸优化建模（与 `solve_optimization` 工具共享） |

**未安装（需要时 `pip install` 到主环境即可）:**

seaborn、scikit-learn、statsmodels、xgboost、lightgbm、torch、tensorflow、networkx、pulp、ortools。沙箱继承主进程 site-packages，装完即生效，无需改沙箱代码。

**硬约束:**

| 约束 | 值 | 实现方式 |
|---|---|---|
| 执行超时 | 60s | `subprocess.run(timeout=60)` |
| 内存上限 | 512MB | `RLIMIT_AS`（仅 Unix） |
| CPU 时间 | 60s | `RLIMIT_CPU`（仅 Unix） |
| 单文件大小 | 50MB | `RLIMIT_FSIZE`（仅 Unix） |
| 子进程 | 禁止 fork | `RLIMIT_NPROC=0`（仅 Unix） |
| 网络 | 完全阻断 | socket.connect monkey-patch + 代理环境变量清除 |
| 环境变量 | 仅保留 PATH/PYTHONPATH/TEMP 等 | 不泄露 API Key、数据库连接串 |
| stdout 截断 | 5000 字符 | 超出部分丢弃 |
| stderr 截断 | 2000 字符 | 超出部分丢弃 |

**Windows 注意:** `resource` 模块不存在，`preexec_fn` 返回 None，上述 rlimit 全部不生效。Windows 下沙箱仅靠超时 + 网络阻断 + 环境清洗保护。生产部署建议用 Linux/Docker。

**matplotlib 自动保存机制:** 沙箱包装代码在用户代码执行后自动遍历 `plt.get_fignums()`，将每个 figure 以 `figure_{i}.png`（dpi=150, bbox_inches="tight"）保存到输出目录。用户代码无需手动 `savefig`，也无需 `plt.show()`（Agg 后端无 GUI）。前端通过 `/api/images/{run_id}/{filename}` 访问生成的图片。

**文件引用:** 用户上传的文件（CSV/Excel/TXT 等）通过 `file_ids` 参数传入，沙箱执行前将文件复制到工作目录，代码中直接用文件名读取（如 `pd.read_csv("data.csv")`）。

---

## 五、缺失环节与改进方向

### 5.1 记忆与上下文（参考 memory-context-guide.md）

memory-context-guide.md 提供了 Agent Xi 项目的实战经验，以下模式尚未在 math_agent 中落地:

| 模式 | 来源章节 | 当前状态 | 建议 |
|------|---------|---------|------|
| **工作记忆（问题状态文档）** | §5.1 | ✅ 已实现 | `app/services/working_memory.py`：problem_doc 整体重写 + 每阶段 checkpoint JSON，支持断点续做 |
| **情景记忆（历史建模经验）** | §1.2 | ✅ 已实现 | `app/services/episodic_memory.py`：solution 完成 → LLM 经验摘要 → embed 入 ChromaDB |
| **整体重写用户画像** | §1.1 | ⚠️ 部分 | `app/api/profile_routes.py` 有诊断与画像接口；「整体重写」策略未实现 |
| **快照与版本控制** | §1.4 | ✅ 已实现 | working_memory 重写前快照 `problem_doc.N.bak`，保留 10 份 |
| **Token 预算分配** | §2.1 | ⚠️ 部分 | chat 有滑动窗口(20条)，但无 token 级预算控制；solution 流水线无上下文管理 |
| **贪心截断** | §2.2 | ❌ 未实现 | 当前是固定条数截断，应改为 token 预算 + 贪心逆序填充 |
| **长程任务检查点** | §3.2, §5.3 | ✅ 已实现 | `data/sessions/{id}/checkpoints/1_classify.json … 7_writing.json` |
| **多 Agent 上下文隔离** | §3.4, §5.2 | ⚠️ 部分 | LangGraph state 传递了上下文，但无结构化摘要，子 Agent 可能收到过多无关信息 |

### 5.2 功能缺口

| 功能 | 优先级 | 说明 |
|------|--------|------|
| **docker 全栈部署补全** | P1 | compose/nginx 三处断点已列入修复计划（审计 DIR-1），修通后为产品化第一步 |
| **论文质检接入闭环** | P1 | `scripts/paper_quality_check.py`（12 项评分）已存在，待接入 /solution 完成后自动反馈（审计 DIR-2） |
| **LaTeX 论文导出** | P1 | export_routes.py 已有 DOCX 管线 + path_generator 已产 LaTeX，加导出路由即达（审计 DIR-6） |
| **成就系统持久化** | P2 | `services/achievement_service.py` 已实现但纯内存（重启清零），接 SQLite 后 /progress 可积累（审计 DIR-5） |
| **导师模式** | P2 | ARCHITECTURE 明示二期；MasteryTracker 已按 user_id 隔离，成本被摊薄（审计 DIR-3） |
| **智能体插话协作** | P3 | ARCHITECTURE Phase 4 计划，未交付（审计 DIR-4 确认） |
| **对话导出** | P4 | 导出 chat/teach 对话为 Markdown/PDF，方便复习 |
| **论文模板选择** | P4 | 写作 Agent 支持国赛/美赛 LaTeX 模板，输出可编译的 .tex |
| **DOCX 导出** | P4 | 论文/对话导出为 Word 格式 |
| **批量论文导入** | P3 | 从 PDF/URL 批量导入优秀论文到知识库 |
| **对话分支/重试** | P3 | 对 agent 回答不满意时可重新生成 |
| **多模型对比** | P2 | 同一问题用不同 LLM 回答，对比效果 |
| **代码执行结果持久化** | P3 | run_code 的图表/输出保存到会话，刷新不丢失 |
| **知识库自动扩充** | P2 | web_search 结果经 LLM 筛选后自动写入知识库 |
| **协作模式** | P1(远期) | 多人共享一个建模会话，分工协作 |

### 5.3 工程质量

| 方面 | 当前状态 | 建议 |
|------|---------|------|
| **测试** | 仅 4 个手动脚本，无 pytest | 建立 `tests/` 目录，核心路径(工具调用/SSE/沙箱)需单元测试 |
| **类型安全** | 后端 Pydantic 较完整，前端 TS 有 `as any` 逃逸 | 消除前端 `as any`，补充后端 response schema |
| **错误处理** | 工具调用有 try-catch，但前端错误提示较粗糙 | 统一错误码 + 前端 toast 通知 |
| **日志** | 后端有 logging，前端仅 console.error | 前端接入 Sentry 或自建错误上报 |
| **CI/CD** | 无 | GitHub Actions: lint + typecheck + build + 基础测试 |
| **Docker** | compose 已合并为单文件（profile 区分 dev 全栈/云端单后端），`docker compose config` 双模式验证通过；未做运行时真机验证（无守护进程） | 有 Docker 环境后 `docker compose --profile dev up` 全栈走一遍 |
| **安全** | 沙箱有 rlimit+网络阻断，但 Windows 下 rlimit 不生效 | Windows 沙箱替代方案（Docker 容器或 WASM） |

### 5.4 知识库质量

| 方面 | 当前状态 | 建议 |
|------|---------|------|
| 方法卡片数量 | ~15 个 YAML | 补充到 30+，覆盖 §一 中列出的缺失方法 |
| 论文数量 | 4 篇 | 批量导入 20+ 篇 O 奖/M 奖论文 |
| 模板数量 | 3 个框架模板 | 增加题型专用模板（预测类/优化类/评价类/统计类） |
| 向量化 | ChromaDB 已建索引 | 新增/修改 YAML 后需重新 embed（目前无自动触发） |
| 检索质量 | BM25 + 向量 + rerank | 增加元数据过滤（按题型/方法类别），提高精准度 |

---

## 六、开发路线图

### 已完成

- [x] 基础架构: FastAPI + Vue3 + LangGraph + Redis + ChromaDB
- [x] 三模式: chat / teach / solution
- [x] 安全加固: 沙箱 rlimit + 网络阻断 + WS 鉴权 + JWT 校验
- [x] P1: ask_user 澄清 + run_code 代码执行 + ClarifyCard 选项卡片
- [x] P2: 文件上传 + 图表内联显示 + 沙箱文件引用
- [x] P3: Web 搜索 (DuckDuckGo)
- [x] UI 修复: 白屏/三点常驻/滚动/工具调用排序/进度条冗余
- [x] RAG 升级: 多路召回 + RRF 融合 + LLM 精排 + 时间衰减 + 查询扩展
- [x] 安全审查修复: XSS(DOMPurify) / 路径穿越 / 事件循环阻塞(asyncio.to_thread) / JWT 7天过期 / runningMode 持久化
- [x] 上传加固: 20MB 大小限制 + 扩展名白名单 + 流式校验
- [x] SSE 取消: AbortController + chat/teach 停止按钮
- [x] 对话导出: Markdown 下载 + printAsPdf
- [x] DOCX 导出: `POST /api/export/docx` (python-docx)
- [x] Retriever 缓存: 模块级单例，BM25 索引只建一次
- [x] 启动自动建索引: 检测 chroma.sqlite3 不存在则后台 rebuild
- [x] 端口可配置: vite loadEnv 读 .env.local，WS 走代理（多人开发兼容）
- [x] 方案模式质量大修: writing max_tokens 65536 + 续写兜底 / 求解发 tool_call 事件(代码+图表) / 摘要 280→800

### 近期 (P4)

**论文模板选择 (LaTeX)**

- 后端: 新增 `POST /api/export/latex`，接收 solution 最终论文 Markdown + 模板 ID（cumcm/mcm），用 Jinja2 渲染为 `.tex` 源码返回
- 模板存放: `backend/templates/latex/cumcm.tex.j2`、`mcm.tex.j2`，参考 mathmodel-latex-skill 项目结构
- 前端: solution 完成页加"导出 LaTeX"按钮，下载 `.tex` 文件
- 依赖: `jinja2`（已有）；LaTeX 编译由用户本地完成，系统不装 TeX Live
- 涉及文件: 新建 `backend/app/api/export_routes.py`、`backend/templates/latex/`

**代码结果持久化**

- 当前问题: run_code 图片存 `tempfile.gettempdir()/mathmodel_outputs/{run_id}/`，系统重启或清理 tmp 后丢失
- 方案: 执行完成后将图片复制到 `backend/data/code_outputs/{session_id}/{run_id}/`，URL 改为 `/api/images/{session_id}/{run_id}/{fn}`
- 消息持久化: chat 消息目前仅存前端内存 + SSE 流，需后端存 Redis hash 或 SQLite（`chat_history:{session_id}`）
- 涉及文件: `sandbox/executor.py`（输出路径）、`chat_routes.py`（图片路由）、新建 `backend/app/services/chat_persistence.py`

**分析质量提升 (prompt 优化)**

- 现状: 分析/建模阶段输出偏简短（temperature=0.3 保守 + 缺 few-shot 示例）
- 方案: analysis/modeling prompt 增加 1-2 个 few-shot 示例引导深度；temperature 微调到 0.4-0.5
- 写作图表: 考虑让 writing agent 用 `\includegraphics` 引用 solving 阶段已生成的 matplotlib 图片，替代纯 TikZ（前端 Markdown 渲染器无法显示 TikZ）
- 涉及文件: `backend/app/core/prompts/analysis.py`、`modeling.py`、`writing.py`、`config.py`(temperature)

### 中期 (P5)

**工作记忆 (问题状态文档 + checkpoint)**

- 设计: 每个 solution 会话维护一个 `problem_doc.md`（Markdown），5 阶段各写入对应章节
- 存储: `backend/data/sessions/{session_id}/problem_doc.md` + `checkpoint_{1-5}.json`
- 写入时机: LangGraph 每个节点完成后，Orchestrator 调 LLM 将本阶段输出摘要追加到文档（整体重写模式，参考 MEMORY_CONTEXT_GUIDE §1.1）
- 断点续做: 用户重新打开 solution 页 → 读最新 checkpoint → 从下一阶段继续
- 涉及文件: `backend/app/graph/nodes/`（各节点末尾写 checkpoint）、新建 `backend/app/services/working_memory.py`
- 快照: 每次重写 problem_doc 前存 `.bak`，保留 10 份

**情景记忆 (历史建模经验)**

- 存储: 复用 ChromaDB，新建 collection `episodic_memory`，每条记忆 = {session_id, problem_type, method_used, outcome, timestamp}
- 写入: solution 完成后，LLM 生成一条经验摘要（"2023C 蔬菜定价用了灰色预测+ARIMA组合，MAPE 8.2%"）
- 召回: 新 solution 开始时，用题目描述做向量检索 top_k=3，注入 Orchestrator system prompt 尾部
- 涉及文件: 新建 `backend/app/services/episodic_memory.py`、修改 `graph/nodes/analyze.py`（注入召回结果）

**知识库批量导入**

- 后端: `POST /api/kb/batch-import`，接收 PDF 文件列表或 URL 列表
- 流程: PDF → `PyMuPDF` 提取文本 → LLM 结构化提取（方法名/适用场景/公式/步骤）→ 生成 YAML → 写入 `knowledge_base/methods/` 或 `papers/` → 触发 ChromaDB embed
- 依赖: `pip install pymupdf`
- 涉及文件: 新建 `backend/app/api/kb_import_routes.py`、`backend/app/services/kb_extractor.py`

**对话重试**

- 前端: Bubble 组件 hover 时显示"重新生成"按钮（仅最后一条 assistant 消息）
- 后端: 无需新接口，前端截断 messages 到最后一条 user 消息，重新调 `streamChat`
- 涉及文件: `Bubble.vue`（按钮）、`useStreamChat.ts`（retry 方法，删除旧 assistant 消息再重发）

**Token 预算截断**

- 替换 `chat_routes.py` 中 `MAX_HISTORY_MESSAGES = 20` 硬编码
- 实现: 启发式计数（中文 1.5 token/字，英文 1.3 token/词，安全系数 1.1x），从最新消息逆序贪心填充，预算 = 模型 max_tokens - system - tools - reserved_output
- 参考: MEMORY_CONTEXT_GUIDE §2.2 的 `select_within_budget` 代码可直接复用
- 涉及文件: 新建 `backend/app/core/token_budget.py`、修改 `chat_routes.py`

### 远期 (P6+)

**用户画像 (teach 模式)**

- 整体重写模式: teach 会话结束时 LLM 读旧画像 + 本次对话 → 输出新画像（学生知识水平、薄弱点、偏好）
- 存储: `backend/data/profiles/{user_id}/teach_profile.md`，快照保留 20 份
- 注入: teach 模式 system prompt 尾部追加画像内容
- 涉及文件: 新建 `backend/app/services/user_profile.py`、修改 teach system prompt

**多模型对比**

- 前端: 输入框旁加模型选择器（多选），发送后并行调多个 LLM，结果左右/上下对比展示
- 后端: `POST /api/chat/compare`，接收 model_ids 列表，asyncio.gather 并行请求，SSE 分 channel 返回
- 涉及文件: 新建 `compare_routes.py`、前端新建 `CompareView.vue`

**知识库自动扩充**

- web_search 结果经 LLM 评分（相关性 > 0.8 + 信息密度判断）→ 自动写入 `knowledge_base/papers/` 或 `methods/`
- 需人工审核队列: 自动入库标记为 `status: pending_review`，管理页面可批准/拒绝
- 涉及文件: `web_search_tools.py`（结果后处理）、新建审核 API

**测试体系**

- 后端: `backend/tests/`，pytest + httpx.AsyncClient（SSE 测试）+ 沙箱单元测试
- 前端: `frontend/src/__tests__/`，Vitest + @vue/test-utils（ClarifyCard/Bubble 组件测试）
- CI: GitHub Actions workflow — lint(ruff) + typecheck(mypy) + pytest + vitest + vite build
- 涉及文件: 新建 `tests/`、`.github/workflows/ci.yml`

**Windows 沙箱**

- 方案 A: Docker 容器执行（`docker run --rm --network=none --memory=512m python:3.11-slim -c "..."`）
- 方案 B: WASM 沙箱（Pyodide / wasmtime），轻量但库支持有限
- 推荐方案 A，与生产部署一致
- 涉及文件: `sandbox/executor.py` 增加 Docker 模式分支（配置项 `sandbox_backend: subprocess | docker`）

**协作模式**

- 多人共享 solution 会话: Redis PubSub 广播阶段进度，前端 WebSocket 同步
- 权限: 房主可编辑，协作者只读 + 评论
- 远期目标，当前架构（单用户 session）需较大改造

---

## 七、设计参考

### memory-context-guide.md 核心模式速查

| 模式 | 一句话 | 适用场景 |
|------|--------|---------|
| 整体重写 | 会话结束时 LLM 读旧文档+对话→输出新文档 | 用户画像、问题状态文档 |
| 情景记忆 | 向量库存显式记忆，top_k=3 注入 system prompt 尾部 | 历史建模经验召回 |
| 贪心截断 | 从最新消息往回装，装满 token 预算为止 | 多轮对话上下文管理 |
| 原子写入 | 先写 .tmp 再 rename | 所有持久化操作 |
| 快照回滚 | 修改前存 .bak，保留 20 份 | 问题状态文档、用户画像 |
| 检查点 | 每阶段完成存独立 JSON | solution 5 阶段断点续做 |
| 结构化摘要 | 子 Agent 返回 JSON 摘要而非全文 | 多 Agent 上下文传递 |

### 工具链速查

| 工具 | 用途 | 当前状态 |
|------|------|---------|
| `search_method_cards` | 查方法原理/公式/适用场景 | ✅ |
| `search_similar_papers` | 查竞赛真题/优秀论文 | ✅ (论文数量不足) |
| `get_analysis_template` | 查评价/解题框架模板 | ✅ |
| `sympy_compute` | 符号数学(求导/积分/方程/ODE/特征值) | ✅ |
| `solve_optimization` | 凸优化(LP/QP/IP/SOCP) | ✅ |
| `ask_user` | 澄清需求(选项卡片) | ✅ |
| `run_code` | 沙箱代码执行(含文件引用+图表) | ✅ |
| `web_search` | DuckDuckGo 互联网搜索 | ✅ |
| `file_upload` | 用户上传数据文件 | ✅ |
| **待加**: `export_paper` | 论文导出(LaTeX/DOCX/PDF) | ❌ |
| **待加**: `recall_experience` | 召回历史建模经验 | ❌ |
| **待加**: `update_problem_doc` | 更新问题状态文档(工作记忆) | ❌ |

---

## 八、技术细节备查

### 8.1 SSE 流式协议

chat/teach 模式通过 `POST /api/chat` 返回 `text/event-stream`，帧格式:

```
data: {"delta": "增量文本"}\n\n
data: {"tool_call": {"name": "run_code", "args": {...}}}\n\n
data: {"tool_result": {"name": "run_code", "preview": "前200字符..."}}\n\n
data: {"clarify": {"questions": [{"question":"...", "options":[...], "multiSelect":false}]}}\n\n
data: {"code_exec": {"status": "running"}}\n\n
data: {"code_exec": {"status": "done", "stdout": "...", "images": ["/api/images/abc123/figure_1.png"]}}\n\n
data: [DONE]\n\n
data: {"error": "错误信息"}\n\n
```

前端解析: `chatApi.ts` 用 fetch + ReadableStream 按 `\n\n` 分帧，逐帧 JSON.parse。收到 `clarify` 帧时流立即结束（LLM 等待用户选择后重新发送）。

### 8.2 后端核心依赖

| 包 | 用途 | 备注 |
|---|---|---|
| fastapi + uvicorn | Web 框架 + ASGI 服务器 | |
| langchain-core / langchain-openai | LLM 调用 + 工具绑定 | tool_call_chunks 增量累加模式 |
| langgraph | solution 5 阶段状态机 | |
| redis | PubSub（solution 进度广播）+ 缓存 | 需本地/容器运行 Redis |
| chromadb | 向量检索（方法卡片/论文/模板） | 持久化到 `backend/data/chroma/` |
| sympy / cvxpy | 数学计算工具 | |
| duckduckgo-search | Web 搜索 | 免费无 Key，偶发限流 |
| python-multipart | 文件上传 | |
| pyjwt | JWT 签发/校验 | |
| httpx | GitHub OAuth token 交换 | |

### 8.3 前端核心依赖

| 包 | 用途 |
|---|---|
| vue 3 + vite 6 | 框架 + 构建 |
| pinia | 状态管理（auth/chat/task store） |
| tailwindcss | 样式 |
| lucide-vue-next | 图标 |
| marked + katex | Markdown 渲染 + 数学公式 |
| axios | 非流式 API 请求 |

包管理: pnpm。dev server 端口 5174，代理 `/api` → `localhost:8002`。

### 8.4 API 端点清单

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat` | SSE 流式对话（chat/teach） |
| POST | `/api/solution/start` | 启动建模流水线（WS 推进度） |
| WS | `/api/solution/ws/{session_id}?token=JWT` | 建模进度 WebSocket |
| POST | `/api/files/upload` | 文件上传，返回 file_id + filename |
| GET | `/api/images/{run_id}/{filename}` | 沙箱生成的图片 |
| POST | `/api/auth/github` | GitHub OAuth 回调 |
| POST | `/api/auth/guest` | 访客登录 |
| GET | `/api/auth/me` | 当前用户信息 |
| CRUD | `/api/keys` | API Key 管理 |
| CRUD | `/api/kb/methods` | 知识库方法卡片 |
| CRUD | `/api/kb/papers` | 知识库论文 |
| POST | `/api/kb/reindex` | 重建向量索引 |

### 8.5 部署架构

```
┌─────────────┐     ┌──────────────────────────────────┐
│  Vue3 SPA   │────▶│  FastAPI (uvicorn :8000)          │
│  (vite :5174│     │  ├─ /api/chat (SSE)              │
│   dev proxy)│     │  ├─ /api/solution (WS + REST)    │
└─────────────┘     │  ├─ /api/files, /api/images      │
                    │  └─ /api/auth, /api/kb, /api/keys│
                    └───────┬────────────┬─────────────┘
                            │            │
                    ┌───────▼──┐  ┌──────▼──────┐
                    │  Redis   │  │  ChromaDB   │
                    │ (PubSub) │  │ (向量检索)   │
                    └──────────┘  └─────────────┘
```

生产部署: docker-compose（FastAPI + Redis + ChromaDB + Nginx 静态前端）。`docker-compose.yml` 已存在但未完整验证。

### 8.6 已知坑与注意事项

| 坑 | 原因 | 规避 |
|---|---|---|
| LangChain tool_call_chunks 首片有 name 无 args | 增量分片设计 | 必须 `full_message + chunk` 累加后从 `.tool_calls` 取完整调用 |
| v-else 跟最近 v-if 配对 | Vue 模板编译规则 | 中间不能插独立 v-if，否则断链 |
| 外层 overflow-y-auto 吃内层滚动 | CSS 滚动容器继承 | 外层改 overflow-hidden |
| Windows 下 rlimit 不生效 | 无 resource 模块 | 生产用 Linux/Docker |
| duckduckgo-search 偶发 429 | 免费接口限流 | 前端 tool_result 显示"搜索暂时不可用"，不阻断对话 |
| module-level os.environ 读空值 | import 在 load_dotenv 之前 | 用 lazy getter 函数 |
| matplotlib 中文乱码 | 沙箱无中文字体 | 用户代码需 `plt.rcParams['font.sans-serif'] = ['SimHei']` 或系统装字体 |

---

*本文档随开发推进持续更新。*
