"""
step_2.py — Step 2 dispatcher. Currently always Nano Banana 2 Edit.
Plan C variants will add their own step_2 implementations later.
"""

from pathlib import Path
from . import step_2_nano_banana


def generate(
    plan: str,
    step_1_local_path: str,
    step_2_prompt: str,
    step_2_params: dict,
    out_path: Path,
    scenario_id: str = "unknown",
) -> dict:
    if plan in ("plan_a", "plan_b"):
        return step_2_nano_banana.generate(
            step_1_local_path, step_2_prompt, step_2_params, out_path, scenario_id
        )
    raise ValueError(f"unknown plan: {plan!r} (expected 'plan_a' or 'plan_b')")