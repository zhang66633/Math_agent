"""AgentState — 所有智能体共享的状态定义。"""

from typing import Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """LangGraph 共享状态，所有节点读写此 State。"""

    # --- 消息 ---
    messages: Annotated[list[BaseMessage], add_messages]

    # --- 模式 ---
    mode: Literal["teach", "execute"]
    session_id: str

    # --- 问题理解 ---
    problem_raw: str
    problem_type: str
    problem_complexity: Literal["simple", "composite", "innovative"]
    data_dependency: Literal["theoretical", "given_data", "self_collect"]

    # --- 知识库上下文 ---
    kb_methods: list[dict]
    kb_papers: list[dict]
    kb_templates: list[dict]
    kb_problems: list[dict]

    # --- 技能装配（app/skills）：规划阶段定下的技能目录，各节点按角色取用 ---
    active_skills: list[str]

    # --- 动态执行计划 ---
    execution_plan: list[
        str
    ]  # 例如: ["analysis", "modeling", "solving", "verification", "writing"]
    current_step_index: int
    retry_count: int
    max_retries: int

    # --- 各 Agent 输出 ---
    analysis_output: str | None
    model_output: str | None
    preprocessed_data: str | None  # 数据预处理节点输出
    solving_output: str | None
    verification_output: str | None
    writing_output: str | None

    # --- 回退控制 ---
    verification_passed: bool | None
    verification_feedback: str | None
    rollback_target: str | None

    # --- 用户 API Key 配置 ---
    api_key_config: dict | None

    # --- 题目数据附件 ---
    data_files: list[dict]  # 本题关联的数据文件信息 [{filename, columns, rows, ...}]
    data_files_dir: str  # 数据文件在磁盘上的目录路径

    # --- 导出文件 ---
    export_files: list[dict] | None  # 结果导出文件列表 [{type, name, url, size}]

    # --- 最终输出 ---
    final_response: str | None


def create_initial_state(
    problem_raw: str,
    mode: Literal["teach", "execute"] = "execute",
    session_id: str = "default",
    api_key_config: dict | None = None,
    data_files: list | None = None,
    data_files_dir: str = "",
) -> AgentState:
    """创建初始状态，填好默认值。"""
    return AgentState(
        messages=[],
        mode=mode,
        session_id=session_id,
        problem_raw=problem_raw,
        problem_type="",
        problem_complexity="simple",
        data_dependency="theoretical",
        kb_methods=[],
        kb_papers=[],
        kb_templates=[],
        kb_problems=[],
        execution_plan=[],
        current_step_index=-1,
        retry_count=0,
        max_retries=3,
        analysis_output=None,
        model_output=None,
        preprocessed_data=None,
        solving_output=None,
        verification_output=None,
        writing_output=None,
        verification_passed=None,
        verification_feedback=None,
        rollback_target=None,
        api_key_config=api_key_config,
        data_files=data_files or [],
        data_files_dir=data_files_dir,
        export_files=None,
        final_response=None,
    )
