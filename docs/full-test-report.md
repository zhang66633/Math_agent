# 全量功能测试报告（2026-10-13）

> **范围**：MathModelAgent 全部用户可见功能 + 导出链路 + 渲染链路。
> **方法**：真机实测——跑真实服务、用真实任务产物（不是只跑单测）。真实任务：`9e3c2dd1`（轻量优化题）、`bad9118a`（2023 国赛 C 题）。
> **结论**：**发现并修复 3 个导出缺陷，其中 2 个是「功能完全失效」级别**；其余功能 48 项实测通过（1 项为脚本自身方法用错，非产品缺陷）。

---

## 一、测试结果总览

| 域 | 测试方式 | 结果 |
|----|----------|------|
| 基础与系统 | `GET /api/health`、`/openapi.json`、`/api/sandbox/status` | 3/3 ✅ |
| 知识库（读） | 方法卡 86 / 论文 32 / 真题 38 / 模板 3、详情、raw、检索 | 全部 200 ✅（含中文与英文术语检索） |
| 学习中心 | 三角色学习路径 + 下一单元、题库 183、错题本、单元详情、单元自测、成长档案、进度、诊断 | 全部 200 ✅ |
| 训练场（写） | 答题判定、练习轮次 | 2/2 ✅（判定返回 `correct`/`answer_index`/含 LaTeX 的解析） |
| 会话与任务 | 任务列表 65 / 详情 / 状态 / 事件流 / 消息 / 文件、会话列表 / 详情 / 消息 | 全部 200 ✅ |
| 文件 | 上传（multipart）→ 下载回读 | 2/2 ✅（27 B，内容匹配） |
| 对话 | `POST /api/chat` SSE 流 | ✅ 1.4 s，`data: {"delta": "2"}` + `[DONE]` |
| 导出 | md / latex / docx / xlsx / csv / zip / POST docx | 7/7 ✅（修复后） |
| 公式与 Markdown 渲染 | 前端 vitest + 真实论文片段 | 23 例通过 ✅ |
| 前端页面 | 12 个页面模块经 Vite 编译加载 + SPA fallback | 12/12 ✅ |
| 回归 | 后端 pytest **188 用例 / 27 文件**、前端 vue-tsc / biome / vitest | 全绿 ✅ |

接口 smoke 共 **48 项**：第一批 42 项（41 通过，1 项失败是脚本对 `/api/profile/roles` 用了 GET，而该接口只接受 PUT，前端也未调用它）+ 第二批 6 项全通过。

---

## 二、发现并修复的缺陷

### 缺陷 1（P0）：`POST /api/export/docx` 对任何中文标题都 500

- **现象**：该接口返回 500，任何中文标题必然失败（默认标题就是「对话记录」）。
- **根因**：`Content-Disposition: attachment; filename="{title}.docx"` 直接把中文写进 HTTP 头；Starlette 按 latin-1 编码头值 → `UnicodeEncodeError: 'latin-1' codec can't encode characters`。
- **修复**：新增 `md_docx.content_disposition()`，按 RFC 5987 同时给出 ASCII 回退名与 `filename*=UTF-8''` 编码名；三处下载响应统一使用。
- **结果**：500 → **200**（48 KB docx）。

### 缺陷 2（P0）：`?format=latex` 导出的其实是 Python 代码

- **现象**：导出的 `.tex` 不含 `\documentclass`，内容是一段 Python 源码。
- **根因**：`re.search(r"```(?:latex|tex)?\s*\n(.*?)```")` —— 语言标记写成**可选**，于是匹配到论文里**第一个**代码块（哪怕是 ```python）。
- **修复**：`extract_explicit_latex()` 只认显式 `latex`/`tex` 标记；无显式块且正文不是完整文档时，改由新增的 `markdown_to_latex()` 生成可编译的 ctexart 文档（标题映射章节、表格转 tabular、公式原样保留、特殊字符转义但保护 `$...$`）。
- **结果**：5905 B 的 Python 代码 → **16536 B 的含 `\documentclass` 的 LaTeX**。

### 缺陷 3（P1）：任务导出的 Word 表格全丢、行内格式未解析

- **现象**：`/api/tasks/{id}/export?format=docx` 产物中 **tables = 0**（论文里有 37 行表格），`**加粗**` 原样显示为星号。
- **根因**：项目里有**两份** markdown→docx 实现：`api/export_routes.py` 的版本解析完整；`api/tasks.py` 的版本自己写了套「简单转换」，`elif stripped.startswith("|"): continue` 直接丢弃表格行，段落也不做行内解析。同一篇论文走两个入口结果不同。
- **修复**：抽出单一真源 `app/services/md_docx.py`（行内解析 / 表格 / 列表 / 引用 / 代码块 / 图片注入），两个入口共用；`export_routes.py` 保留历史私有名 re-export，避免破坏既有 import 与测试。
- **结果**：tables **0 → 4**、单元格 **0 → 144**、`**` 残留 **true → false**；两个入口产物一致。

---

## 三、公式渲染链路（专项验证）

| 路径 | 机制 | 实测 |
|------|------|------|
| 前端阅读/对话 | marked + marked-katex-extension + DOMPurify | ✅ 真实论文片段（`aligned` 环境、表格内公式、正文行内公式）渲染为 `.katex`，无 `katex-error`，`$$` 不残留；**KaTeX 的 `style` 与 MathML `<math>` 未被 DOMPurify 洗掉**（配置漂移护栏） |
| 打印/导出 PDF | `exportPaper.ts` 预渲染 HTML + 内联 katex.css（离线自足） | ✅ 代码路径已不依赖任何 CDN |
| 后端 DOCX | 公式降级为可读文本 `[公式: ...]` | ⚠️ 见「已知限制」 |

---

## 四、已知限制与未覆盖项（如实记录）

| 项 | 说明 |
|----|------|
| DOCX 里的公式是文本 | Word 无法承载 LaTeX，目前降级为 `[公式: \max Z = ...]`。语义不丢、可读，但不是「排版好的公式」。若要提升可走 Word 原生公式（OMML）；前端 PDF 路径已是真渲染。 |
| 未测：`POST /api/knowledge/reindex` | 会重建向量索引（调用嵌入接口、需数分钟）。知识库检索是答辩演示环节，重建期间/失败时有影响演示的风险；YAML 是唯一真源、索引可重建，故本次不冒险。 |
| 未测：GitHub OAuth 登录 | 需真实 OAuth 凭据与回调域名，本机无法端到端验证；访客模式已实测可用。 |
| 未测：`/api/knowledge/import/confirm` | 会把抽取结果写入知识库真源 YAML（用户真实数据），故只验证到接口存在与契约。 |
| 未测：`POST /api/learning/units/{id}/complete` | 会改写用户学习档案的掌握度数据。 |
| 小语义问题 | 对**已完成**任务调用 `cancel` 返回 200「任务已取消」。幂等、无害，但语义不精确，可后续改为 409。 |
| 检索耗时 | 单次检索 2.7–6.9 s（BM25 + 向量 + 融合）。演示前建议先搜一次预热，避免首次点击时冷启动叠加。 |

---

## 五、复现方式

```bash
# 后端
cd backend && python -m pytest -q                 # 188 用例 / 27 文件
python -m ruff check app tests                    # 0 error

# 前端（本机 pnpm 链接曾损坏，可直接用 node 调用）
node node_modules/vue-tsc/bin/vue-tsc.js --noEmit # 0 error
node node_modules/@biomejs/biome/bin/biome check src
node node_modules/vitest/vitest.mjs run           # 23 例（markdown 17 + request 6）

# 导出实测（需后端在 8002 运行、且存在已完成任务）
#   GET /api/tasks/{id}/export?format=md|latex|docx|xlsx|csv
#   GET /api/tasks/{id}/package
#   POST /api/export/docx  {"markdown": "...", "title": "中文标题"}
```

---

## 六、本次新增/改动的测试资产

| 文件 | 内容 |
|------|------|
| `backend/tests/test_export_docx_latex.py` | 13 例：中文文件名响应头（latin-1 可编码）、DOCX 表格与行内格式、LaTeX 显式块提取、ctexart 骨架与公式保留、Python 代码块进 verbatim |
| `backend/tests/test_export_md.py`（既有） | 行内解析 5 例，继续通过（re-export 兼容） |
| `frontend/src/utils/markdown.test.ts` | 新增 2 例：真实论文片段渲染、DOMPurify 未洗掉 KaTeX 的 style/MathML |
| `backend/app/services/md_docx.py` | 本次新增的单一真源（DOCX 转换 + 下载头 + LaTeX 生成） |
