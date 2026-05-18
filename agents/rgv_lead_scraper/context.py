from pathlib import Path

from omniagents.core.context.decorator import context_factory
from omniagents.core.skills import build_available_skills_block


@context_factory
def build_skills_context(variables):
    """Discover skills under <project>/.omni_code/skills/ and inject the
    block into the agent's instructions."""
    agent_dir = Path(__file__).resolve().parent
    project_root = agent_dir.parents[1]
    skill_roots = [project_root / ".omni_code" / "skills"]
    return {
        "available_skills_block": build_available_skills_block(skill_roots),
    }
