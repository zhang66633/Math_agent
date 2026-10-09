# Phase 2 改进方案 — OOM·方案模式·知识库

> 版本: v0.1 | 日期: 2026-07-29
> 背景: Phase 1（PLAN.md）的 5 阶段流水线、知识库基础、前端页面全部交付。本文档覆盖下一阶段：解决 OOM 被杀、方案模式工作记忆、知识库批量导入。

---

## 一、OOM 内存优化

### 1.1 ChromaDB 独立容器

**现状**: ChromaDB 以库的形式 embedded 在后端进程内，吃 300-500MB。

**方案**: docker-compose 加一个 chromadb 服务，后端通过 HTTP 客户端连接。

```
# docker-compose.yml 新增
chromadb:
  image: chromadb/chroma:latest
  ports:
    - "8001:8000"
  volumes:
    - ./backend/data/chroma_db:/chroma/chroma
  environment:
    - IS_PERSISTENT=TRUE
  restart: unless-stopped
```

后端改动：`config.py` 加 `chroma_http_url` 配置项，`embedder.py`/`indexer.py` 从本地 ChromaDB 客户端切换为 `HttpClient`。

### 1.2 沙箱改 Docker 容器

**现状**: `subprocess.run([sys.executable, "-c", code])`，子进程继承主进程 site-packages（numpy/scipy/pandas 全加载），每执行一次 200-500MB。

**方案**: 自建 sandbox 镜像，需要时 `docker run --rm --network=none --memory=512m`。

```
# Dockerfile.sandbox
FROM python:3.11-slim
RUN pip install numpy scipy pandas matplotlib sympy cvxpy
COPY sandbox_wrapper.py /wrapper.py
ENTRYPOINT ["python", "/wrapper.py"]
```

```python
# executor.py 新增 Docker 模式
def run_docker(code: str, ...):
    subprocess.run([
        "docker", "run", "--rm",
        "--network=none",
        "--memory=512m",
        "-v", f"{output_dir}:/output",
        "mathmodel-sandbox",
        code
    ], timeout=self.timeout)
```

**关键收益**: 执行完自动销毁，内存回收；网络隔离天然生效（不需要 socket monkey-patch 和 _clean_env）；Windows 下有真正的内存限制。

---

## 二、方案模式 — 工作记忆

### 2.1 问题状态文档

每个 solution 会话一份 `problem_doc.md`，5 个阶段分批写入，LLM 整体重写：

```
backend/data/sessions/{session_id}/
├── problem_doc.md          # 问题状态文档
├── problem_doc.1.bak       # 快照（每次重写前备份，保留 10 份）
├── checkpoints/
│   ├── 1_classify.json
│   ├── 2_retrieve.json
│   ├── 3_analysis.json
│   ├── 4_modeling.json
│   ├── 5_solving.json
│   ├── 6_verification.json
│   └── 7_writing.json
└── messages.json           # 前端展示消息持久化
```

### 2.2 整体重写流程

```
每阶段结束
  → 读当前 problem_doc.md
  → 读本阶段 agent 输出
  → LLM 重写: "把新内容整合进去，3000 字以内，保持结构清晰"
  → atomic_write(tmp → rename)
  → 保存 checkpoint JSON（含时间戳 + 阶段名 + 输出摘要）
```

### 2.3 断点续做

```
POST /api/solution/start
  → 检查是否有未完成的 session
  → 有 → 读取最新 checkpoint → 从下一阶段继续
  → 无 → 新建

前端 solution 页
  → mounted 时 GET /api/tasks/{id} 检查状态
  → 未完成 → 提示"上次做到第 3 阶段，是否继续？"
```

### 2.4 子 Agent 上下文隔离

不用全文传递——每个子 Agent 只拿到 problem_doc 中与自己相关的切片：

- Analysis: §1 问题概述
- Modeling: §2 推荐方法 + §3 分析报告
- Solving: §4 模型公式 + 代码要求
- Verification: §5 求解结果 + §4 模型假设
- Writing: 全部章节（生成论文需要完整上下文）

### 2.5 新增文件

| 文件 | 职责 |
|------|------|
| `app/services/working_memory.py` | 读写 problem_doc、checkpoint、快照、原子写入 |
| `app/services/episodic_memory.py` | solution 完成 → LLM 生成经验摘要 → embed → 存入 ChromaDB |

### 2.6 修改文件

| 文件 | 改动 |
|------|------|
| `core/nodes.py` | 每个节点末尾调 `working_memory.save_checkpoint()` |
| `api/tasks.py` | 增加恢复未完成 session、读取 checkpoint |
| `core/workflow.py` | 支持从指定阶段启动（skip 已完成节点） |

---

## 三、知识库 — 批量导入 + 扩充

### 3.1 PDF 论文批量导入

**入口**: 新建 `POST /api/knowledge/batch-import`

**流程**:
```
上传 PDF 文件（或指定目录路径）
  → PyMuPDF 逐页提取文本
  → LLM 结构化提取（title/year/problem_type/core_models/...）
  → 生成 YAML → 写入 knowledge_base/papers/
  → 标记 status: pending_review
  → 前端预览页，人工 approve/reject
  → 通过 → embed 入库 → status: published
```

**LLM 提取 prompt**:
```
你是一个数学建模论文解析器。根据以下论文文本，提取结构化信息：

论文文本: {pdf_text[:8000]}

返回 JSON:
{
  "title": "论文标题",
  "year": 2023,
  "competition": "国赛",
  "problem_id": "C",
  "tags": {
    "problem_type": ["优化"],
    "core_models": ["线性规划", "整数规划"],
    "techniques": ["灵敏度分析"]
  },
  "analysis": {
    "problem_summary": "一句话概括",
    "key_assumptions": ["假设1", "假设2"],
    "objective": "目标是什么",
    "constraints": "约束是什么"
  },
  "model": {
    "approach": "建模思路",
    "innovation": "创新点",
    "solution_method": "求解方法"
  },
  "evaluation": {
    "strengths": [],
    "weaknesses": [],
    "lessons": "可学之处"
  },
  "quality_rating": 4
}
```

### 3.2 方法卡片补充

从 `../roadmap.md` 中挑 6 个高频缺口：

| 方法 | 类别 |
|------|------|
| 多元线性回归 | 统计 |
| Logistic 回归 | 统计 |
| 假设检验 + 方差分析 | 统计 |
| NSGA-II 多目标优化 | 优化 |
| LSTM 时间序列 | 预测 |
| 网络流 / 最小生成树 | 图论 |

用现有 `scripts/import_knowledge.py` 的 LLM 提取功能 + 手写 YAML 混合方式录入。

### 3.3 新增/修改文件

| 文件 | 职责 |
|------|------|
| 新建 `app/api/knowledge_import_routes.py` | 批量导入 API |
| 新建 `app/services/kb_extractor.py` | PDF 文本提取 + LLM 结构化 |
| 修改 `app/api/router.py` | 注册新路由 |
| 新增 `knowledge_base/papers/` | 批量导入的论文 YAML |
| 新增 `knowledge_base/methods/statistics/` | 补充方法卡片 |

---

## 四、执行顺序

| # | 任务 | 工时 | 依赖 |
|---|------|------|------|
| 1 | ChromaDB 独立容器 | 0.5h | 无 |
| 2 | 沙箱 Docker 化 | 2h | 无 |
| 3 | 方案模式工作记忆 | 1d | 无 |
| 4 | 情景记忆 | 0.5d | #3 |
| 5 | 知识库批量导入 | 1d | 无 |
| 6 | 方法卡片补充 | 2h | 无 |

#1、#2 并行做（互不依赖）；#3→#4 串行；#5、#6 并行做。

---

*待用户确认后逐项实施。*
