from __future__ import annotations

from pathlib import Path

from omniagents.core.context.decorator import context_factory
from omniagents.core.skills import build_available_skills_block


@context_factory
def build_context(variables):
    agent_dir = Path(__file__).parent
    skill_roots = [agent_dir / "skills"]
    return {
        "available_skills_block": build_available_skills_block(skill_roots),
        **(variables or {}),
    }
