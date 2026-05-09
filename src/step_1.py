"""
step_1.py — Step 1 dispatcher. Chooses Plan A (PuLID) or Plan B (Kontext)
based on the active config.
"""

from pathlib import Path
from . import step_1_pulid, step_1_kontext


def generate(
    plan: str,
    step_1_prompt: str,
    step_1_params: dict,
    out_path: Path,
    scenario_id: str = "unknown",
) -> dict:
    """
    Args:
        plan          : 'plan_a' or 'plan_b'
        step_1_prompt : the prompt string from Opus output
        step_1_params : the fal endpoint params (PuLID or Kontext-shaped)
        out_path      : where to save image
        scenario_id   : for log lines
    """
    if plan == "plan_a":
        return step_1_pulid.generate(step_1_prompt, step_1_params, out_path, scenario_id)
    if plan == "plan_b":
        return step_1_kontext.generate(step_1_prompt, step_1_params, out_path, scenario_id)
    raise ValueError(f"unknown plan: {plan!r} (expected 'plan_a' or 'plan_b')")