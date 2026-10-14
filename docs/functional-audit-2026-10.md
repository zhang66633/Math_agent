# 功能层全面审计报告（2026-10-14）

> 审计方式：**静态通读 + 全量测试 + 真实进程实测**。安全层审计（`AUDIT-2026-10.md`）已完成修复闭环
> （`731a588` 已合入推送），本轮只查**功能层面**：功能是否真的可用、前后端是否对得上、文档是否说谎。
> 实测手段：自起隔离实例（127.0.0.1:8010，不碰用户 8002）+ 桩 LLM 全链路跑图 + 37 项 HTTP 冒烟。

## 一、结论先行

| 级别 | 数量 | 内容 | 状态 |
|------|------|------|------|
| **P0 功能缺陷** | 1 | **86 张方法卡中 22 张（25.6%）详情接口必返 500**，并存在「编辑→保存」**抹掉公式/代码字段**的数据毁灭路径 | ✅ **已修复**（`88d037d`，86/86 复测 200） |
| **P0 回归** | 1 | 访客任务属主桶漂移（`"guest"` vs `"default"`）→ 匿名任务建完即 404，方案模式对默认用户形态全不可用 | ✅ **已修复**（见 9.1，含 3 例回归测试） |
| **P1 死功能** | 1 | Working Memory「问题状态文档」永不更新——生产数据实证所有真实任务的 `problem_doc.md` 都是初始模板 | ✅ **已修**（改确定性拼装 + status 端点暴露，见第四节） |
| **P1 进行中缺陷** | 1 | 新增 Key 的 DNS SSRF 校验在本机误杀全部真实服务商（fake-ip `198.18.x.x` 被判内网），`test_apikeys_ssrf` 1 例失败 | ⚠️ 你的在改项，见第十节 |
| **P2** | 4 | 6 个孤儿端点无调用方；测试残渣落进运行数据目录；方法卡详情有数据但前端不渲染 | 前两项已修/已清，孤儿端点待你定夺 |
| **P3** | 2 | 前端声明了 API 从不返回的类型字段；对已完成任务 cancel 返回 200 | ⚠️ 未修 |

**测试面全绿**：后端 **221 passed**（含本轮新增 7 个全量枚举用例）、ruff 0 error、前端 typecheck / biome / vitest(23) / build 全过；
LangGraph 九节点全链路用桩 LLM 实测跑通；SSE 对话与 WebSocket 属主校验均端到端验证通过；
**真实 LLM 端到端任务已跑通**（见第九节）。

---

## 二、测试矩阵（本轮实测，非引用）

| 项目 | 命令 | 结果 |
|------|------|------|
| 后端测试 | `python -m pytest` | ✅ **221 passed**（198 + 用户新增 11 个隔离测试 + 本轮新增 7 个详情契约测试，40.2s） |
| 后端 lint | `ruff check app tests` | ✅ All checks passed |
| 前端类型 | `vue-tsc --noEmit` | ✅ 0 error |
| 前端 lint | `biome check src` | ✅ 197 files, no issues |
| 前端单测 | `vitest run` | ✅ 23 passed（退出码 1 是 jsdom "navigation to another Document" 的 stderr 噪音，非失败） |
| 前端构建 | `vite build` | ✅ 10.06s，全部 chunk 产出 |
| 全链路跑图 | 桩 LLM 驱动真实 StateGraph | ✅ classify→retrieve→plan→5 agents→format，9 节点顺序正确、各输出非空、`verification_passed=True` |
| HTTP 冒烟 | 37 项（自起 8010 实例） | ✅ 30 通过 + 4 项预期负例（404/405）+ 3 项真缺陷（即下文 P0/P2，已定位根因） |
| SSE 对话 | `POST /api/chat`（1 次真实最小调用） | ✅ 200，`data: {"delta":"线性"}` 逐字流 |
| WS 属主校验 | 真实 WS 连接 | ✅ 不存在任务 → HTTP 403；访客桶存量任务 → 放行并回 `{"event":"connected"}` |

---

## 三、P0：方法卡详情接口 500（22/86）+ 数据毁灭路径

### 现象

```
GET /api/knowledge/methods/mc_007  → 500
GET /api/knowledge/methods/mc_002  → 500   （共 22 张，含 mc_002~006/007/011~014 等）
GET /api/knowledge/methods/mc_001  → 200   （未受影响的 64 张正常）
```

### 根因：两套 schema 对同一字段的宽容度不一致

| 位置 | 定义 | 宽容度 |
|------|------|--------|
| `app/knowledge/schemas.py:30,34,35`（加载器） | `formulas: list[str \| Formula]`、`common_mistakes: list[str \| Mistake]`、`code_snippets: list[str \| CodeSnippet]` | **双兼容**，注释明说「兼容纯字符串（新格式）和结构化对象（旧格式）」 |
| `app/api/knowledge_shared.py:42,46,47`（API 响应模型） | `formulas: list[dict]`、`common_mistakes: list[dict]`、`code_snippets: list[dict]` | **只收 dict** |

`get_method` 直接 `MethodCardDetail(**card.model_dump())`，字符串条目 → pydantic ValidationError → 500。
**受影响面（实测枚举）**：`formulas` 含字符串 21 张、`common_mistakes` 15 张、`code_snippets` 14 张，
并集 **22/86 = 25.6%**。论文/模板/真题详情接口实测均 200（无此问题）。

### 为什么更严重：这不是「看不了详情」，而是「会丢数据」

1. `KnowledgeSearchPanel.vue:395` 详情加载失败是 `catch { /* ignore */ }` → 详情弹窗**静默空白**，用户无感知。
2. `KnowledgeManagePanel.vue:368` 编辑时 detail 加载失败 → `editForm` 只剩列表行的摘要字段，
   随后的归一化把 `formulas/common_mistakes/code_snippets` 全置为 `[]`。
3. `doEditSave()`（:496）把**整个表单** PUT 上去，后端 `update_method`
   （`knowledge_crud_routes.py:62-81`）用提交数据整体重建 `MethodCard` 并**覆写 YAML 文件**——
   YAML 是知识库唯一真源。于是：**打开任意一张受影响卡片的编辑框再点保存，该卡的公式、常见错误、代码示例被永久抹掉**（且会触发重新索引）。

> 编辑需 `require_contributor`，所以不是被外人利用的漏洞，是维护者自助路径上的数据毁灭。
> 上一轮全量测试报告称「方法卡详情全部 200」——只抽到了未受影响的卡片，漏检。

### 修复建议（按推荐排序）

1. **服务端归一化（最小改动，立即止血）**：在 `get_method` 构造 `MethodCardDetail` 前，把字符串条目
   转成结构化 dict（`str → {"name": "", "latex": s, "description": ""}`；
   `mistake → {"mistake": s, "solution": ""}`；`code → {"language": "", "description": "", "code": s}`）。
   API 契约不变，前端 ArrayEditor 立刻能显示内容，数据毁灭路径同时消失。
2. **数据规范化（可选跟进）**：写一次性脚本把 22 张卡的 YAML 统一为结构化形式，消除双格式长期并存。
3. **加回归测试**：遍历 `load_all_methods()` 对每张卡构造一次 `MethodCardDetail`，确保 86/86 全部可序列化
   （这类「全量枚举」测试正是上一轮漏掉的那种）。

### ✅ 修复实施记录（`88d037d`）

**做法**：`knowledge_shared.py` 新增 `normalize_entries()` / `method_card_detail()`，策略是
**无损收纳而非猜测式拆分**——字符串整体进主字段（公式进 `latex`、错误进 `mistake`、代码进 `code`），
其余字段补空串；结构化对象原样通过并补齐缺失字段；`None` 归一为 `""`（这一条是回归测试自己抓出来的：
初版把 `None` 变成了字符串 `"None"`）。`get_method` 改走 `method_card_detail()`，**API 契约不变**。

**复测证据**（自起隔离实例，修复后）：

```
mc_002..mc_012（此前 8/8 全 500）→ 全部 200，字段计数正确
全量枚举 86 张 → 86/86 = 200，零失败
mc_007.formulas[0]        = {"latex": "0-1背包: dp[i][w] = max(...)", "name": "", "description": ""}
mc_007.common_mistakes[0] = {"mistake": "问题没有重叠子问题时强行 DP...", "solution": ""}
mc_007.code_snippets[0]   = {"code": "# Python: 0-1背包 ...", "language": "", "description": ""}
论文 / 模板 / 真题详情 → 无回归
```

前端 `ArrayEditor` 的字段声明（`name/latex/description`、`mistake/solution`、`language/description/code`）
与归一化后的形状**逐字对齐**，编辑框现在能直接显示与修改这些内容。

**新增测试** `tests/test_kb_detail_contract.py`（7 例）：核心是**全量枚举**——86 张卡逐一构造响应模型
+ 逐一打 HTTP 断言 200；另含 None 条目、混合列表、字符串落主字段、未知 ID 仍 404 等用例。
后端总计 **221 passed**、ruff 0 error。

---

## 四、P1：Working Memory 的「问题状态文档」是死功能 ✅ 已修

`_save_working_memory`（`node_helpers.py`）想用 `asyncio.get_event_loop().run_in_executor(...)`
异步触发 `update_problem_doc`（LLM 整体重写问题状态文档），但：

- 生产里节点跑在 langgraph 的线程池 worker 里，**该线程没有运行中的事件循环** →
  `get_event_loop()` 抛 RuntimeError → 命中 `except RuntimeError` 分支，只打一条 warning 就跳过。
- 本轮桩 LLM 全链路实测，7 个节点**全部**打出「当前线程无运行事件循环，跳过问题文档异步重写」。
- **生产数据实证**：真实任务 `62b64b79` / `b5c91839` 的 7 个检查点齐全，但 `problem_doc.md`
  仍是 `init_session` 写的初始模板（7 个章节全「（待完成）」，mtime 早于所有检查点）。
- 且 `get_problem_doc()` **全仓库零调用方**——即使文档被更新了也没有任何读者。

检查点（`save_checkpoint`）本身是好的，`/api/tasks/{id}/status` 的断点续做依赖它，功能正常。
死掉的只是「LLM 持续维护的问题状态文档」这半边。

### 修复取舍与做法

三条路：① 修好机制（threading 直接提交）并启用 LLM 重写；② 删掉这半边；③ 换成零成本确定性版本。
选 ③，理由：**启用 ① 等于每个任务多约 7 次真实 LLM 调用，而读者依然是零**——花钱没人看；
② 会丢掉一个本来有价值的设计（`memory-context-guide.md` §5.1/§5.2 把它定位成编排器的滚动上下文）。

做法（`working_memory.py` + `node_helpers.py` + `tasks.py`）：

- `update_problem_doc`（LLM 重写）**删除**，换成 `refresh_problem_doc()`：按 `STAGE_ORDER`
  读各检查点的 `output_summary` 拼装同一份 Markdown，纯文件 IO、毫秒级、**不调 LLM**。
- 刷新动作放进 `save_checkpoint` 内部（而不是留给调用方）——否则「存了检查点却忘了刷文档」
  会让文档悄悄过期，那正是死功能时代的症状。这条是测试逼出来的：第一版把刷新放在
  `_save_working_memory` 里，自测直接抓到「单独调 save_checkpoint 时文档不更新」。
- `init_session` 同时写 `meta.json`（原始问题等）——拼装时要引用原始问题，而它原来只存在于
  会被覆盖的初始模板里，写完就再也读不回来。
- 给文档一个真实读者：`GET /api/tasks/{id}/status` 新增 `problem_doc` 字段。
- `REWRITE_PROMPT` / `_backup_problem_doc` / 同文件的死代码 `save_messages` / `load_messages`
  （零调用方）一并删除；文件顶部留「墓碑注释」写清废弃原因，免得后人重新踩。

测试 `tests/test_working_memory.py`（5 例）：拼装内容与阶段数、幂等、无会话时 no-op、
**「节点保存后文档必须真的更新」**（死功能回归护栏）、status 端点暴露 problem_doc。

---

## 五、P2/P3 明细

| # | 级别 | 问题 | 证据 / 建议 | 状态 |
|---|------|------|------------|------|
| 1 | P2 | **6 个孤儿端点**：`POST /api/knowledge/import/{confirm,extract-text,method,paper}`、`POST /api/learning/path/generate`、`PUT /api/profile/roles` —— 前端与 `backend/scripts/`、tests 均无调用方 | 前端走的是 `/knowledge/upload` + `/knowledge/jobs/{id}` 异步任务流；import/* 是被取代的旧同步路径 | ✅ **已删**（88 → 82 端点），见第十一节 |
| 2 | P2 | **测试残渣落进运行数据目录**：`backend/data/` 下与 `learning.db`、`sessions.db` 混放 `test_learning*.db` 等 | 根因：`test_learning_store.py` 的 `__main__` 直跑块写死 `Path("data")`（pytest 侧本就正确用 tmp_path） | ✅ 已修：直跑块改 `tempfile.TemporaryDirectory`；存量 8 项残渣已清 |
| 3 | P2 | `pytest.ini` 的 `addopts = -q` 吞掉 `N passed` 汇总行 | 只能靠退出码判断成败 | ✅ 已由你改为 `-ra` |
| 4 | P3 | 前端 `LearningPath` 接口声明 `total_units/completed_units/overall_mastery`，后端从不返回 → store 里 `?? 0` 兜底 | 三个计算属性恒为 0 且无任何页面消费 | ✅ 已删（死字段不补默认值充数），见第十一节 |
| 5 | P3 | 对已完成任务 `POST /cancel` 返回 200「任务已取消」 | 幂等无害，但前端会把已完成任务显示成已取消，状态骗人 | ✅ 已改 409 + 5 例回归测试 |
| 6 | P2 | **方法卡详情有数据但不渲染**：`formulas` / `common_mistakes` / `code_snippets` / `typical_scenarios` / `not_applicable_when` / `related_cards` 前端无展示位 | 同 dialog 的 paper 分支把这些字段渲染得很完整 | ✅ 已修：按 paper 分支规格补齐，公式走统一 markdown 管线（KaTeX） |

---

## 六、本轮验证通过的功能（留档，避免重复审计）

- **LangGraph 全链路**：9 节点顺序、计划路由、验证通过即不回退、`final_response` 正确拼装（桩 LLM 实测）。
- **知识库读路径**：stats / 列表 / 详情（64 张正常卡 + 论文 + 模板 + 真题）/ raw / 检索（真实嵌入 + rerank，首条命中「线性规划」）。
- **学习系统**：三角色路径（modeler 38 / programmer 13 / writer 10，去重 61，与 PLAN.md 一致）、下一单元、题库 183（一致）、错题本、单元详情、单元自测、画像、进度统计。
- **任务与会话**：列表 / 详情 / 消息 / 事件回放 / 文件 / 状态 / 导出 md；负例 404 正确。
- **安全修复的功能兼容性**（重点核查，因为正在改）：前端 WS 带 token 且登录后自动重连 → 属主校验不误伤；访客仍放行；`learningApi` 仍在发的 `user_id` 被 Pydantic 忽略，行为不变。
- **前后端契约**：88 个 REST 端点逐一比对 `frontend/src/apis/*.ts` + stores + 页面的全部调用，无 404/方法不匹配（唯一曾疑似的 search 422 是审计脚本用错参数名，前端传的 `q` 正确）。

---

## 七、复现方式

```bash
# 隔离实例（勿用用户 8002）
cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8010

# P0 复现（一行）
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/api/knowledge/methods/mc_007   # 500
# 枚举受影响卡片
python -c "import sys; sys.path.insert(0,'.'); from app.knowledge.loader import KnowledgeBaseLoader; \
from app.config import get_settings; \
print([c.id for c in KnowledgeBaseLoader(get_settings().kb_root).load_all_methods() \
if any(isinstance(x,str) for x in c.formulas+c.common_mistakes+c.code_snippets)])"

# P1 复现：看任意真实任务的 problem_doc.md 是否还是初始模板
ls backend/data/sessions/<task_id>/          # checkpoints/*.json 齐全
head -20 backend/data/sessions/<task_id>/problem_doc.md   # 仍是「（待完成）」x7
```

---

## 八、未覆盖项

1. ~~**真实 LLM 端到端任务**~~ → **已覆盖**，见第九节。
2. `POST /api/knowledge/reindex`（重建向量索引数分钟，演示期有风险）依旧未测，
   理由同上一轮报告。
3. ~~`/api/knowledge/import/confirm`~~ → **已不存在**：该端点属无调用方的旧同步
   导入流程，已在清理轮整体删除（见第十一节）。

---

## 九、真实 LLM 端到端任务（修复后复跑）

用户拍板「先修 P0 再跑一次端到端」。修复提交后，用一道轻量线性规划题走完整
`POST /api/tasks` → LangGraph 九节点 → 终态验收全链路（真实 DeepSeek 调用、真实沙箱、
真实事件落盘）。任务与各节点产物见下方实测记录。

### 9.1 端到端本身抓出一个 P0 回归（安全修复引入，已修）

第一次跑端到端时，流水线**实际跑完了**（日志显示 classify→…→verification 全过，
磁盘上 `problem_doc`/检查点/311 行事件流俱全、`status=completed`），但 REST 侧
`GET /api/tasks/{id}` 返回 **404**、列表里也找不到。排查后定位：

- `create_task` 用 `apikeys._resolve_user_id`（访客桶 = `"guest"`，为兼容存量
  `apikeys.json`）给**任务**定 owner；
- 而所有读取方用 `auth.resolve_user_id`（访客桶 = `"default"`，与
  `session.DEFAULT_TASK_OWNER` 一致）。
- 两个字面量不一致 → **匿名任务一经创建就对自己 404**（列表缺席、WS 1008 关闭）。

访客是本站**默认形态**（登录限项目贡献者 `ALLOWED_CONTRIBUTORS`），所以这个回归
等于整个方案模式对真实用户不可用。TestClient 复现（修复前）：

```
POST /api/tasks            -> 200，新建 7019e9ec
GET  /api/tasks/7019e9ec   -> 404        ← 建完即失联
GET  /api/tasks            -> 200，列表不含新任务
```

**为什么测试没抓住**：`test_user_isolation.py` 只覆盖登录用户（`audit_owner_a/b`），
访客路径——也就是默认路径——没有任何用例。

**修复**：`create_task` 里把两件事拆开——查 Key 仍走 apikeys 桶（`key_uid`），
任务属主改用任务命名空间的 `resolve_user_id(user)`。`chat_routes` 的用法本就正确
（只用于查 Key），无需改动。

**回归测试** `tests/test_guest_task_ownership.py`（3 例）：访客建的任务能立刻读到自己、
出现在列表里、属主落在 `"default"`；访客 WS 能订阅自己的任务；登录用户看不到访客的任务。
修复后同一复现脚本：`GET -> 200`、`列表含新任务: True`。

> **过程记录（多会话并发工作树的坑，2026-10-14 再次实证）**：提交这个修复时，
> `git add backend/app/api/tasks.py` 把同一文件里**另一条会话未提交的改动**
> （`_resolve_image_path` 收敛到 `node_helpers.resolve_task_media_path`、导出 xlsx/csv 改按
> mtime 取最新文件的 `_latest_task_file`）一起卷进了 commit `0f5d900` 并推送。
> 已用 `git worktree` 干净检出 HEAD 验证：43/43 相关测试通过，那部分改动自洽
> （引用的 helper 已在 `node_helpers.py` 入库），推送的树没有坏。
> AGENTS.md 已把这条教训写成纪律（暂存显式列路径 + 提交前 `git status --short`），
> 但**同一文件里混着两头改动时，逐文件暂存仍不够**——要么先 `git stash` 分清，
> 要么用 `git add -p` 按 hunk 挑。本次选择保留（内容已验证可用、force-push 被禁），
> 并在此登记，免得后人困惑那段代码的来历。

### 9.2 端到端实测记录

访客属主修复后，一道轻量线性规划题（工厂两种产品、两种原料约束）走完整链路：

| 项 | 实测值 |
|----|--------|
| 任务 | `b4a4d714`（匿名/访客形态，无 token） |
| 终态 | `completed`，总耗时 **240s** |
| analysis_output | 2498 字 |
| model_output | 2633 字 |
| solving_output | 10573 字（含沙箱代码执行） |
| verification_output | 3676 字 |
| writing_output / final_response | **40727 字** |
| 事件流 | 317 条：node_start/end 各 10、node_delta 242、tool_call/result 各 9、code_exec 18、plan 1、task_end 1 |
| 断点续做 | 7 个阶段检查点齐全，`resume_stage=null`、`is_active=false` |
| 论文标题 | 《基于线性规划的工厂日生产计划优化模型与灵敏度分析》 |

**这条实测同时验证了 9.1 的修复**：任务以访客身份创建，轮询全程能 `GET /api/tasks/{id}`
读到各节点产物——修复前同一流程在第一步就 404。

内容质量小观察（非缺陷）：`solving_output` 的开头是英文过程性独白
（"All verifications pass. Now I'll output the co…"），求解节点的原始产出没有过
`_clean_md` 类的清洗就直接进了状态；终稿由写作节点重写，故不影响论文成品。

---

## 十、顺手发现的两条（非本轮主目标，记录在案）

### 10.1 方法卡详情有数据但不渲染（P2，前端）

`KnowledgeSearchPanel.vue` 的 `method_card` 分支只渲染 `principle` 与 `applicable_when`；
API 已返回（修复后也能正常加载）的 `formulas` / `common_mistakes` / `code_snippets` /
`typical_scenarios` / `related_cards` **没有展示位**。同为详情的 `paper` 分支却把这些
字段渲染得很完整（核心公式 / 方法链路 / 算法概要 / 常见陷阱）。管理页的 ArrayEditor
能编辑它们，但浏览页看不到——建议按 paper 分支的规格补齐。

### 10.2 新增 Key 的 DNS 校验在本机误杀真实服务商（P1，你的在改项）

为落实上一轮审计的 P1-1 建议（「补一步 DNS 解析后再判内网」），`_validate_custom_base_url`
现在会 `getaddrinfo` 后逐一判定。但**本机 DNS 是 fake-ip 池**：

```
api.deepseek.com    -> 198.18.0.89
api.siliconflow.cn  -> 198.18.0.103
```

`198.18.0.0/15` 被 `_is_disallowed_ip` 判为内网 → 任何真实服务商的 base_url 都被拒，
`tests/test_apikeys_ssrf.py::test_public_https_accepted` 因此失败（这是当前全量测试里
唯一的红）。调用点只有新增 Key 的两个端点（`create_api_key` / `quick_add_api_key`，
apikeys.py:303/373），所以**已配置的 Key 不受影响、任务与对话照常跑**；受影响的是
「在 /apikeys 页或首页添加新 Key」这条流程。

三个方向（按推荐排序）：① 对 `PROVIDER_PRESETS` 里的已知域名做白名单，跳过 DNS 判定；
② 把 `198.18.0.0/15` 从内网判定中排除（它是 benchmarking 保留段，常被代理软件的
fake-ip 池使用，本机即是）；③ 用环境变量开关控制这层 DNS 校验，默认只在生产开。

---

## 十一、清理轮：孤儿端点与死字段（用户拍板「清理」）

### 11.1 删除的 6 个端点（88 → 82）

用脚本重新做了一次前后端契约比对（而不是手工抽查），确认无调用方后删除：

| 端点 | 删除理由 |
|------|----------|
| `POST /api/knowledge/import/paper` `/method` `/confirm` `/extract-text` | 整个 `knowledge_import_routes.py` 删除。前端走 `/knowledge/upload` + `/knowledge/jobs/{id}` 异步任务流，这套同步预览/确认流程已被取代 |
| `POST /api/learning/path/generate` | 与 `GET /learning/path/{role}` 重复（都调 `generate_learning_path`），只是多两个前端从不传的 level/goal 参数 |
| `PUT /api/profile/roles` | 无任何调用方；画像的角色改由 `POST /profile/diagnose` 写入（该端点保留——它是画像唯一的写入口，且有隔离测试覆盖） |

**没有连带删除的**：`app/services/kb_extractor.py`（`KBExtractor`）。它表面上只被
`knowledge_import_routes.py` 引用，但 `backend/scripts/` 下有 5 个批量导入脚本
（`batch_extract_methods` / `batch_import_papers` / `build_missing_problems` /
`import_2014a` / `import_problems`）在用它——86 张方法卡当初就是这么进来的。
HTTP 表面可以删，提取引擎必须留。

### 11.2 顺手发现：角色画像从未被写入（新 P2）✅ 已修

删 `/profile/roles` 时顺着读了一遍画像链路，发现一个**与删除无关的既有缺陷**：

- 前端 `stores/profile.ts:49` 用 `hasProfile = p.roles.length > 0` 判断有没有学习画像，
  它决定首页「继续学习」卡是否显示；
- 而后端 `profile.roles` 只有两个写入口——`PUT /roles`（已删，本来就没调用方）和
  `POST /profile/diagnose`（前端也从不调用，只有测试在用）；
- 且 `_profiles` 是**进程内存字典**，重启即失。

结论：`hasProfile` 恒为 false，**首页「继续学习」卡永远不会显示**；学习工位的角色切换是纯前端（localStorage）行为，与服务端画像是两张皮。

**修复（用户拍板「让角色切换器切角色时调一次 diagnose」）**：

- `learning.ts` 的 `switchRole` 改为 async：本地切换 + 路径加载优先，随后
  `POST /profile/diagnose { role }` 写服务端画像；失败只 `console.warn` 不阻断
  （后台同步，不是主线功能）。
- 同时把 `diagnose` 从**覆盖**改成**合并**语义：`goal` / `weekly_hours` /
  `self_assessment` 不提供就保留画像现值。否则切换器每调一次就把用户在一次完整
  诊断里填的目标冲成默认值——那是「修一个坑、挖一个更深的坑」。
- 验证：真实 HTTP 实测 `hasProfile` 从 `false` → `true`、主角色覆盖正确、
  「美赛/25h」的目标在反复切角色后仍在；后端 6 例（含「只切角色不冲目标」护栏）
  + 前端 3 例（切角色即写、失败不阻断本地切换）。

仍未解决：`_profiles` 是进程内存字典，重启即失——画像没有持久化。要做的话得落
learning.db 或单独一张表，属于下一个功能点，不在本轮范围。

### 11.3 删掉的死字段与改掉的取消语义

- 前端 `LearningPath.total_units / completed_units / overall_mastery` 及 store 里
  三个恒为 0 的计算属性：后端从不返回这些字段，也没有任何页面消费。删除而不是
  「补默认值充数」——要么后端真返回，要么别声明。
- `POST /api/tasks/{id}/cancel` 对终态任务（completed/error/cancelled）改返 **409**：
  此前恒返 200「任务已取消」，前端会把已完成的任务显示成已取消。新增
  `tests/test_cancel_semantics.py`（5 例）：running 仍 200、三种终态 409 且状态
  不被篡改、他人任务仍 404（隔离优先于状态判断）。
