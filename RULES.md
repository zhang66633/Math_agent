# 项目规则（硬约束，不可协商）

## 一、技术栈锁定

- **前端**：Vue 3 + Vite + TypeScript + shadcn-vue + Tailwind CSS + Pinia
- **后端**：FastAPI + LangGraph + LangChain
- **LLM**：默认国产栈（DeepSeek / Qwen / GLM），Claude / GPT 经 OpenAI/Anthropic 兼容接口作为**可选**供应商（需在 `.env` 显式配置对应 Key，默认不启用）
- **权威文档**：`PLAN.md`；`docs/archive/ARCHITECTURE.md` 为早期废弃方案，禁止参考；其余文档在 `docs/`（现行）与 `docs/archive/`（历史）分级存放，以 `docs/README.md` 索引为准

## 二、架构红线

- 三模式职责不可混淆：
  - `/chat` `/teach`：纯对话 SSE（快），不走 LangGraph 流水线
  - `/solution`：LangGraph 多智能体流水线（重），不走纯对话
- 编排器**必须**脱离事件循环运行（`asyncio.to_thread`），禁止在 async 路由里直接跑同步 LLM 节点
- uvicorn 不带 `--reload`（不稳定）
- Redis 非必须（自动回退 fakeredis）

## 三、Git 规范

### 协作流程
- **直接推 main**，先 pull 再 push
- 发生冲突时本地解决后 push，不得 force-push

### 禁止清单（强制执行）
- **禁止**对 main 做 force-push / rebase / 重建历史
- **禁止**对 origin 做 force-push（任何分支）
- GitHub 仓库开启 main 分支保护（禁止 force push）

### 提交格式
```
type: 中文描述
```
类型：`feat`（功能）、`fix`（修复）、`chore`（杂项）、`docs`（文档）、`refactor`（重构）

### 禁止入库
- 密钥、Token、`.env`、`apikeys.json`
- `*.pyc`、`__pycache__/`
- `chroma_db/`、`*.sqlite3`
- 运行产物（`images/`、`output_paper.*`、日志文件）
- `node_modules/`、`dist/`

## 四、目录约定

| 路径 | 用途 |
|------|------|
| `backend/scripts/` | 一次性调试/验证脚本 |
| `backend/data/` | 本地运行时数据（不入库） |
| `frontend/src/composables/` | 页面间复用逻辑 |
| `frontend/src/stores/` | Pinia 状态管理 |

禁止在 `backend/` 或 `frontend/src/` 根部堆放一次性脚本。

## 五、代码约定

- 跨页面共用逻辑**必须**抽 composable，禁止复制粘贴
- API Key 通过页面配置（`/apikeys`）或 `backend/data/apikeys.json`，不硬编码
- 新功能先打通前后端再提交，不留下纯 mock 页面
