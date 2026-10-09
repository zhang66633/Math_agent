# 五模块智能体链路审查报告（2026-08-24）

> 审查方式：4 路并行深读（代码+图表 / 方案 / 聊天 / 教学）+ 本地交叉查证 + 定向外部调研。
> 分级：P0=污染所有用户的正确性缺陷 · P1=功能失效或明显错误 · P2=质量/健壮性改进。

---

## 🔴 P0（3 个，全部是「单道赛题硬编码污染通用管线」同源问题）

| # | 位置 | 问题 |
|---|---|---|
| P0-1 | `backend/app/core/prompts/solving.py:89-128` | 通用求解 prompt 内嵌某年国赛 B/C 题专属数据说明（parquet 文件名、预计算列、"对问题1/2/3/4 必须调 run_code"）——任何题目都会被诱导读不存在的文件、烧掉工具轮次 |
| P0-2 | `app/core/prompts/solving.py` PAPER_SECTIONS + `nodes.py:1101-1170` | 论文章节结构被写死为该定价题专属标题（"品类级定价与补货优化"），交通/评价类题也被强行套用 |
| P0-3 | `frontend/src/pages/learn` 完成闭环 + `learning_routes.py:77` | 单元完成接口全前端零调用 → 61 个单元 status 永 pending → 前端映射为锁定图标、进度恒 0（锁是假的但体验是坏的） |

## 🟠 P1 清单（21 条，按模块）

### 代码+图表
| 位置 | 问题 |
|---|---|
| `Dockerfile.sandbox:26-37` vs `config.py:89` | docker 默认沙箱缺 seaborn/openpyxl/xlsxwriter，而 preprocessing/solving prompt 强制使用 →「模式越安全越跑不通」倒挂 |
| `sandbox/executor.py:432,593` | stderr 截断保头不保尾——traceback 的异常类型/行号在末尾被切掉，LLM 自修复循环拿到的是文件头不是错误本体 |
| `nodes.py:862-875` + `interaction_tools.py:178-208` | 长 stdout 截断时把拼在末尾的"错误："段整体丢掉 |
| `interaction_tools.py:193-205` + `files.py:150` | 工具回传的 `/api/task_files/{run_id}/...` 链接天生 404（路由只认 task_id），正确的持久 URL 返回值被丢弃不改写 |
| `writing.py:10` + `executor.py:256-290` | 论文永久保留 `/api/images/{run_id}` 但图片按 24h/最新50目录清理 → 旧任务论文必然裂图；docx 导出同样只查临时路径 |
| `nodes.py:838-854,1546-1562` | per-tool 超时后 `ThreadPoolExecutor shutdown(wait=True)` 仍无限 join 卡死线程，节点无总时限——超时是假象，编排器可无限挂起 |

### 方案生成
| 位置 | 问题 |
|---|---|
| `nodes.py:1637` | `preprocessed_data` 是悬空字段：EDA 报告写入 state 后无任何下游读取，结论实际被丢弃 |
| `nodes.py:419-426` + `router.py:58-68` | planner 输出无白名单校验，幻觉步骤名会静默跳过后续所有步骤（含写作）直接收尾 |
| `nodes.py:315-330` + `tasks.py:300-305` | 语义检索命中的"别的真题"会把它带的数据文件误挂载进本题沙箱 |
| `writing.py:157` + `nodes.py:1252-1275` | 并行分章每章都收到全量图链接且都被要求"用尽每一张"→ 多章重复引同一批图 |
| `nodes.py:101,130-133` | 分类结果无枚举校验无重试，解析失败静默空类型 → 标签检索整体跳过 |
| 三处口径不一 | writing 相关 `max_tokens` 绑定 131072/196608/393216——deepseek-chat 超 8192 直接 HTTP 400（已调研实锤），换 key 即全线报错 |

### 聊天
| 位置 | 问题 |
|---|---|
| `chat_routes.py:355-361` + `useStreamChat.ts:241-253` | clarify 问答丢失问题上下文：澄清问题不入历史，用户点选项后 LLM 不知道自己在问什么 |
| `chatApi.ts:133` + `chat_routes.py:49-64,299-320` | RAG 预检索是死代码（无人传 useRag），且两处 retriever 构造配置漂移 |
| `chat_routes.py:327,466` | LLM 流式调用无任何超时，上游挂起则 SSE 连接与 worker 永久占用 |
| `chatApi.ts:164,243-248` + `chatSession.ts:447,470` | 取消后气泡永久卡"生成中"，标记随持久化写入、刷新复活 |

### 教学
| 位置 | 问题 |
|---|---|
| `learning_routes.py:96,309-313` + `profile_routes.py:192-209` | learn 事件双计入掌握度：直写路径无防重放守卫，重放时再计一次，数值随进程存活时间漂移 |
| `path_generator.py:23-33` + `profile_routes.py:35-68` | 因材施教全部悬空：level/goal 参数显式忽略、自评画像无消费方、艾宾浩斯复习提醒没接进推荐 |
| `agent_personas.py:157-200` | 七人智能体 persona 是死代码——精心写的启发式人设从未进过任何 system message |
| `chat_routes.py:151-162` + `useStreamChat.ts:57-67` | 学习导师看不到学生正在读的文档正文与 kb_refs；RAG 关 + 工具结果不入历史 = 讲解与知识库三处全断 |
| `solution/index.vue:443` | teach 分支流水线前端不可达（硬编码 execute），nodes.py 6 处分支 + 5 对 TEACH prompt 属休眠代码 |

## 🟡 P2 摘要（30 条，详见各模块）

跨模块主题：
1. **状态与生命周期**：seaborn set_theme 抹掉中文字体预设；Figure 用 `id(fig)` 去重可复用地址丢图；subprocess 拼 `-c` 命令行有 32K 上限；preprocessing 无截断复用；掌握度时区三套混用（UTC+8 用户每天多衰减 8h）；单元对象全局原地突变；practice 刷新失联
2. **安全面**：API 层接受客户端注入 system role；访客共享桶互相可见可删；WS token 走 query string；取消不传播到沙箱进程
3. **prompt 矛盾**：modeling/analysis 正文禁令与格式模板互斥；分类体系缺 simulation 维度；验证节点只看每段前 2000 字就 PASS/FAIL；teach 流水线仍跑 verdict 自动回退
4. **杂项**：无随机种子要求；推荐未安装的 SweetViz；小节编号重复；Redis client 泄漏；trimSessions 不清理附属 Map；多模态白名单缺图片但工具宣传 OCR

## ✅ 本地查证排除的疑点

- ~~前端内联图跨源裂图~~：nginx `/api/` 通配 + vite proxy 都在
- ~~fakeredis 多 worker 失效~~：`start.py` 写死 `--workers 1`
- ~~SSE 反代掐断~~：nginx `proxy_read_timeout 600s` 兜底
- 用户附件进沙箱：确认只有「文本内联进 problem」一条路（`tasks.py:114-122`），Excel 等数据文件无法以文件形态进沙箱 —— 自定义数据题的数据链路确实残缺

## 🌐 外部调研结论

| 疑点 | 结论 |
|---|---|
| deepseek-chat max_tokens 超限行为 | **HTTP 400 报错而非静默钳制**（官方文档+Aihubmix 实测）。**后续更新**：用户确认 deepseek-chat 已淘汰，现行 v4 系列（flash/pro/vision）输出上限 384K、上下文 1M——项目内三处 max_tokens 绑定值在 v4 下全部合法 |
| 代码默认值停留在淘汰模型 | config.py×9、apikeys.py deepseek 预设、schemas×2、.env.example×7 共 19 处默认 `deepseek-chat`——新用户开箱即拿到已淘汰模型名 → **已统一改为 `deepseek-v4-flash`** |
| LangGraph human-in-the-loop | `interrupt()` + `Command(resume=...)` 是官方标准机制（checkpointer 必配）——教学流水线的「等待学生回应」应改此模式，替代现在的 verdict 自动回退 |
| 苏格拉底式一刀切 | `_shared.py:15` "绝不直接给完整答案"不分水平；业界（Khanmigo 类）按学生水平调节提示梯度——系统已有 level 数据只是没接 |
| BKT 简化版参数 | ±0.15/-0.10/+0.05、e^(-t/20)、阈值 0.6 均为拍定值且线性加减非贝叶斯更新——建议对照 Knowledge Tracing 文献校准或降级为简单加权 |

---

## 建议修复批次

- **批次一（P0，半天量级）**：清除两处赛题硬编码恢复通用模板 + 单元完成闭环接通（自动调 complete 或补按钮）
- **批次二（P1 高价值，1-2 天）**：沙箱镜像补依赖、stderr 保尾、URL 生命周期统一改写（run_id→task_id）、planner 白名单、分类枚举校验、max_tokens 钳制、EDA 结论注入下游、LLM 超时、取消终态、掌握度防双计、persona 接线、因材施教参数落地
- **批次三（P2，按需）**：见上文主题分组
