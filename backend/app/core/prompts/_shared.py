"""跨 Agent 共享的提示词片段。

从 agent_prompts.py（已废弃）中提取，被 chat_routes.py 等引用。
"""

MARKDOWN_RULES = """## 输出格式规范

- 数学公式使用 LaTeX 语法: 行内 `$...$`，块级 `$$...$$`
- 表格使用 Markdown 标准格式
- 代码使用 ``` 围栏标记，指定语言类型
- 层次结构清晰，使用 ## ### #### 标题"""

TEACH_SHARED_RULES = """## 教学模式通用规则

1. **绝不直接给出完整答案** — 用引导式提问激发思考
2. **分步引导** — 每次聚焦一个要点
3. **正向鼓励** — 先肯定进步，再指出改进方向
4. **实例类比** — 用学生熟悉的场景解释抽象概念
5. **自检清单** — 引导学生建立自我检验的习惯"""


def render_prompt(template: str, **kwargs: object) -> str:
    """安全渲染提示词模板：只替换显式给出的键，其余花括号原样保留。

    为什么不用 ``str.format``：提示词里常含 JSON 输出示例（如
    ``{"step": "analysis", "reason": "..."}``），``str.format`` 会把 ``{"step"``
    当成占位符解析并抛 ``KeyError: '"step"'``。2026-10-13 端到端压测时，
    方案模式就是因为 planner 用了 ``.format`` 而在 plan_execution 节点整体失败。

    只支持无条件占位符 ``{name}``（不支持格式说明符）——这已覆盖本项目全部提示词。
    """
    out = template
    for key, value in kwargs.items():
        out = out.replace("{" + key + "}", str(value))
    return out
