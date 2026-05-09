"""
prompt_builder_flux.py — FLUX-tuned Step 2 prompt generation for the
flux_tuned_prompt experiment.

Drives Opus 4.7 with master_prompt_step2_flux.md to produce the Step 2
image prompt envelope, including:
  - step_2_image_prompt (180-260 words target, hard ceiling 280)
  - negative_prompt (focused on documented Alluvi failure modes)
  - fal_flux_params (image_size, guidance_scale, num_inference_steps, etc.)

Self-contained module. Does not modify parent or sibling experiment files.
"""

import os
import re
import json
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

CLAUDE_MODEL = "claude-opus-4-7"

# This experiment's master prompt
EXPERIMENT_DIR = Path(__file__).resolve().parent
FLUX_SYSTEM_PROMPT_PATH = EXPERIMENT_DIR / "master_prompt_step2_flux.md"

# Static context paths — relative to project root
PERSONA_YAML_PATH = Path("assets/persona.yaml")
PRODUCT_YAML_PATH = Path("assets/product.yaml")
BRAND_YAML_PATH = Path("brand/brand.yaml")
DO_DONT_MD_PATH = Path("brand/do_dont.md")

_client: Anthropic | None = None
_static_context_cache: dict[str, str] | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in environment")
        _client = Anthropic(api_key=api_key)
    return _client


def _load_static_context() -> dict[str, str]:
    """Load and cache the four static context files."""
    global _static_context_cache
    if _static_context_cache is not None:
        return _static_context_cache

    paths = {
        "persona_yaml": PERSONA_YAML_PATH,
        "product_yaml": PRODUCT_YAML_PATH,
        "brand_yaml": BRAND_YAML_PATH,
        "do_dont_md": DO_DONT_MD_PATH,
    }
    missing = [(k, p) for k, p in paths.items() if not p.exists()]
    if missing:
        msg = "Missing required context files (run from project root):\n" + "\n".join(
            f"  - {k}: {p}" for k, p in missing
        )
        raise FileNotFoundError(msg)

    _static_context_cache = {k: p.read_text(encoding="utf-8") for k, p in paths.items()}
    return _static_context_cache


def _parse_json(text: str) -> dict:
    """Strip code fences and parse JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return json.loads(text)


def build_step_2_prompt_flux(scenario: dict, step_1_output: dict) -> dict:
    """
    Build the FLUX-tuned Step 2 prompt envelope.

    The master prompt produces a 180-260 word step_2_image_prompt plus a
    focused negative_prompt and fal_flux_params (guidance_scale 6.0,
    num_inference_steps 28).

    Args:
        scenario: parsed scenarios.yaml entry for this scenario
        step_1_output: parsed 02_step1_prompt.json from the baseline Plan A run

    Returns:
        dict with keys: step_2_image_prompt (str), negative_prompt (str),
        word_count (int), structure_breakdown, fal_flux_params,
        image_inputs_required, compliance_check.
    """
    if not FLUX_SYSTEM_PROMPT_PATH.exists():
        raise FileNotFoundError(f"missing system prompt: {FLUX_SYSTEM_PROMPT_PATH}")

    system_prompt = FLUX_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    ctx = _load_static_context()

    user_message = "\n".join(
        [
            "=== product.yaml (INTERNAL VALIDATION ONLY — never describe in prompt) ===",
            ctx["product_yaml"],
            "",
            "=== do_dont.md (compliance) ===",
            ctx["do_dont_md"],
            "",
            "=== ORIGINAL SCENARIO ===",
            json.dumps(scenario, indent=2),
            "",
            "=== STEP 1 OUTPUT (use product_slot for placement, lighting from sentence 4) ===",
            json.dumps(step_1_output, indent=2),
            "",
            "=== TASK ===",
            "Build the FLUX-tuned Step 2 prompt envelope per the system prompt above.",
            "",
            "BREVITY IS REQUIRED on FLUX. Per fal's official guidance, prompts above",
            "  ~100 words begin to lose coherence; we push to 260 max for our",
            "  compositing complexity. HARD CEILING: 280 words. Match the calibration",
            "  examples (~233 and ~246 words). Do NOT pad.",
            "",
            "Use 'the person from the first image' / 'the product from the second image' /",
            "  'the first image' / 'the second image' positional reference syntax.",
            "",
            "Use ONE concise identity preservation clause in Sentence 1 — do NOT stack",
            "  multiple parenthetical 'keep X unchanged' anchors (Qwen-style; hurts FLUX).",
            "",
            "Sentence 2 MUST include the orientation lock clause:",
            "  - 'product orientation matches the second image exactly'",
            "  - 'the same face of the box visible in the second image faces the [camera/mirror]'",
            "  - 'packaging not mirrored, flipped, or text-reversed'",
            "  DO NOT specify physical orientation (no 'landscape', 'portrait',",
            "  'wider than tall', 'long horizontal side', or similar). Just match the",
            "  second image.",
            "",
            "Sentence 3 MUST include terse anatomy clause:",
            "  - 'Two arms, two hands, two legs, five fingers per hand'",
            "  - Plus 'no pockets or hidden hands' for hand visibility",
            "",
            "Sentence 4 MUST include:",
            "  - product fidelity ('Alluvi packaging matches the second image exactly')",
            "  - white base preservation",
            "  - lighting direction (from Step 1)",
            "  - CAMERA/LENS specification (FLUX-specific — 35mm/50mm/85mm at f/2.8 etc.)",
            "",
            "negative_prompt MUST be the focused list per Principle 9.c — target documented",
            "  Alluvi failure modes (anatomy, mirroring, duplicates, style drift). Do NOT",
            "  add generic quality terms like 'low quality, blurry, jpeg artifacts, ugly'.",
            "",
            "fal_flux_params MUST include guidance_scale 6.0 (slightly stricter than",
            "  FLUX default 5.0 for product-photography fidelity).",
        ]
    )

    print(f"[prompt_builder_flux] Step 2 (FLUX-tuned) -> Opus 4.7 for scenario {scenario.get('id', '?')}")
    response = _get_client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    output = _parse_json(response.content[0].text)

    wc = output.get("word_count", 0)
    has_neg = bool(output.get("negative_prompt", "").strip())
    print(
        f"[prompt_builder_flux]   Step 2 done: word_count={wc}, "
        f"negative_prompt={'present' if has_neg else 'MISSING'}"
    )
    return output