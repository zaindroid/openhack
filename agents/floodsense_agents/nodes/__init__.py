"""Node placeholders. None of these call a model or a database."""

from floodsense_agents.nodes.investigator import run as investigate
from floodsense_agents.nodes.judge import run as judge
from floodsense_agents.nodes.skeptic import run as challenge

__all__ = ["challenge", "investigate", "judge"]
