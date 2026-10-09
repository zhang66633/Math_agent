"""7 sub-agent node implementations (split from nodes.py).

One module per agent; nodes.py and workflow.py take node functions from here.
"""

from .analysis import analysis_agent_node
from .data_preprocessing import data_preprocessing_agent_node
from .export_results import export_results_agent_node
from .modeling import modeling_agent_node
from .solving import solving_agent_node
from .verification import verification_agent_node
from .writing import build_paper_sections, writing_agent_node

__all__ = [
    "analysis_agent_node",
    "build_paper_sections",
    "data_preprocessing_agent_node",
    "export_results_agent_node",
    "modeling_agent_node",
    "solving_agent_node",
    "verification_agent_node",
    "writing_agent_node",
]
