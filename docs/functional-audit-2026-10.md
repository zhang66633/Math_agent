# 功能层全面审计报告（2026-10-14）

> 审计方式：**静态通读 + 全量测试 + 真实进程实测**。安全层审计（`AUDIT-2026-10.md`）已完成修复闭环
> （`731a588` 已合入推送），本轮只查**功能层面**：功能是否真的可用、前后端是否对得上、文档是否说谎。
> 实测手段：自起隔离实例（127.0.0.1:8010，不碰用户 8002）+ 桩 LLM 全链路跑图 + 37 项 HTTP 冒烟。

## 一、结论先行

| 级别 | 数量 | 内容 |
|------|------|------|
| **P0 功能缺陷** | 1 | **86 张方法卡中 22 张（25.6%）详情接口必返 500**，并存在「编辑→保存」**抹掉公式/代码字段**的数据毁灭路径 |
| **P1 死功能** | 1 | Working Memory「问题状态文档」永不更新——生产数据实证所有真实任务的 `problem_doc.md` 都是初始模板 |
| **P2** | 3 | 6 个孤儿端点无任何调用方；测试残渣落进运行数据目录；`pytest.ini` 的 `-q` 吞掉汇总行 |
| **P3** | 2 | 前端声明了 API 从不返回的类型字段；对已完成任务 cancel 返回 200 |

**测试面全绿**：后端 209 passed、ruff 0 error、前端 typecheck / biome / vitest(23) / build 全过；
LangGraph 九节点全链路用桩 LLM 实测跑通；SSE 对话与 WebSocket 属主校验均端到端验证通过。

---

## 二、测试矩阵（本轮实测，非引用）

| 项目 | 命令 | 结果 |
|------|------|------|
| 后端测试 | `python -m pytest` | ✅ **209 passed**（198 + 用户新增 11 个隔离测试，28.6s） |
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

---

## 四、P1：Working Memory 的「问题状态文档」是死功能

`_save_working_memory`（`node_helpers.py:221-223`）想用 `asyncio.get_event_loop().run_in_executor(...)`
异步触发 `update_problem_doc`（LLM 整体重写问题状态文档），但：

- 生产里节点跑在 langgraph 的线程池 worker 里，**该线程没有运行中的事件循环** →
  `get_event_loop()` 抛 RuntimeError → 命中 `except RuntimeError` 分支，只打一条 warning 就跳过。
- 本轮桩 LLM 全链路实测，7 个节点**全部**打出「当前线程无运行事件循环，跳过问题文档异步重写」。
- **生产数据实证**：真实任务 `62b64b79` / `b5c91839` 的 7 个检查点齐全，但 `problem_doc.md`
  仍是 `init_session` 写的初始模板（7 个章节全「（待完成）」，mtime 早于所有检查点）。
- 且 `get_problem_doc()` **全仓库零调用方**——即使文档被更新了也没有任何读者。

检查点（`save_checkpoint`）本身是好的，`/api/tasks/{id}/status` 的断点续做依赖它，功能正常。
死掉的只是「LLM 持续维护的问题状态文档」这半边。

**修复建议**：改成 `threading.Thread(target=..., daemon=True).start()` 或
`concurrent.futures.ThreadPoolExecutor` 直接提交，不依赖调用线程的事件循环；同时给
`update_problem_doc` 找一个真实读者（或明确删掉这半边，别留悬空设计）。

---

## 五、P2/P3 明细

| # | 级别 | 问题 | 证据 / 建议 |
|---|------|------|------------|
| 1 | P2 | **6 个孤儿端点**：`POST /api/knowledge/import/{confirm,extract-text,method,paper}`、`POST /api/learning/path/generate`、`PUT /api/profile/roles` —— 前端与 `backend/scripts/` 均无调用方 | 前端走的是 `/knowledge/upload` + `/knowledge/jobs/{id}` 异步任务流；import/* 是被取代的旧同步路径。建议：确认无外部消费者后删除，或在 docs 标注「预留 API」 |
| 2 | P2 | **测试残渣落进运行数据目录**：`backend/data/` 下与 `learning.db`、`sessions.db` 混放着 `test_learning*.db`、`test_sessions_*`、`diag_*` 等测试产物 | 测试应把临时库指到 tmp_path（`test_learning_store.py` 等已有此模式），别让运行目录同时充当测试草稿本 |
| 3 | P2 | `pytest.ini` 的 `addopts = -q` 吞掉 `N passed` 汇总行，只能靠退出码判断成败 | 改 `-ra` 或去掉 `-q`（上一轮审计已提，未落地） |
| 4 | P3 | 前端 `LearningPath` 接口声明 `total_units/completed_units/overall_mastery`，后端从不返回 → store 里 `?? 0` 兜底 | 学习页未渲染这三个字段，暂无用户可见影响；删掉死类型字段或让后端补返回 |
| 5 | P3 | 对已完成任务 `POST /cancel` 返回 200「任务已取消」 | 幂等无害，建议改 409 |

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

## 八、未覆盖项（需拍板）

1. **真实 LLM 端到端任务**（`POST /api/tasks` 跑完整国赛题，约 3 分钟、消耗真实额度、会往
   `sessions.json` 写一条任务）。上一轮已实测过两次；本轮代码有改动（写作流水线 / 技能装配），
   是否值得再跑一次由你定。
2. `POST /api/knowledge/reindex`（重建向量索引数分钟，演示期有风险）与
   `/api/knowledge/import/confirm`（写 YAML 真源）依旧未测，理由同上一轮报告。
