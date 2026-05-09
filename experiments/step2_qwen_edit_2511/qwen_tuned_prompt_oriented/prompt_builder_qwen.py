"""
prompt_builder_qwen.py — Qwen-tuned Step 2 prompt generation + orientation picker
                         for the qwen_tuned_prompt_oriented experiment.

Two functions:

1. build_step_2_prompt_qwen(scenario, step_1_output) -> dict
   Same as the existing qwen_tuned_prompt experiment — drives Opus 4.7 with
   master_prompt_step2_qwen.md to produce the Step 2 image prompt envelope.
   Master prompt knows nothing about orientations; produces an
   orientation-agnostic prompt.

2. pick_product_orientation(step_2_image_prompt) -> dict
   NEW: drives a SEPARATE Opus 4.7 call with orientation_picker_prompt.md.
   Reads the just-produced Step 2 image prompt and picks one of four
   pre-rotated product reference images:
     horizontal | vertical | 45_right | 45_left
   Returns {"orientation": str, "reasoning": str}.

   This is a hidden layer — neither the master prompt nor the produced
   Step 2 prompt mentions orientation. From the prompt's perspective,
   image_urls[1] is just "the product reference photo".

Self-contained module. Loads its own static context. Does not modify
parent experiment files.
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
QWEN_SYSTEM_PROMPT_PATH = EXPERIMENT_DIR / "master_prompt_step2_qwen.md"
PICKER_SYSTEM_PROMPT_PATH = EXPERIMENT_DIR / "orientation_picker_prompt.md"

# Static context paths — relative to project root
PERSONA_YAML_PATH = Path("assets/persona.yaml")
PRODUCT_YAML_PATH = Path("assets/product.yaml")
BRAND_YAML_PATH = Path("brand/brand.yaml")
DO_DONT_MD_PATH = Path("brand/do_dont.md")

VALID_ORIENTATIONS = {"horizontal", "vertical", "45_right", "45_left"}

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


# ──────────────────────────────────────────────────────────────────────────
# 1. Step 2 prompt builder (orientation-agnostic — same as parent experiment)
# ──────────────────────────────────────────────────────────────────────────

def build_step_2_prompt_qwen(scenario: dict, step_1_output: dict) -> dict:
    """
    Build the Qwen-tuned Step 2 prompt envelope.

    The master prompt is orientation-agnostic — it does not mention or know
    about the four pre-rotated product images. From the prompt's perspective,
    there is one product reference image.

    Args:
        scenario: parsed scenarios.yaml entry for this scenario
        step_1_output: parsed 02_step1_prompt.json from the baseline Plan A run

    Returns:
        dict with keys: step_2_image_prompt (str), word_count (int),
        structure_breakdown, fal_qwen_params, image_inputs_required,
        compliance_check.
    """
    if not QWEN_SYSTEM_PROMPT_PATH.exists():
        raise FileNotFoundError(f"missing system prompt: {QWEN_SYSTEM_PROMPT_PATH}")

    system_prompt = QWEN_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
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
            "Build the Qwen-tuned Step 2 prompt envelope.",
            "Use 'the person from the first image' / 'the product from the second image' /",
            "  'the first image' / 'the second image' positional reference syntax",
            "  (REQUIRED in this Qwen variant — do NOT use generic 'reference photo' language).",
            "Thread 'keep X unchanged' anchors through Sentence 1 (keep her face unchanged,",
            "  keep her hair unchanged, keep her outfit unchanged, keep the scene unchanged).",
            "Echo Step 1's lighting language from sentence 4 verbatim in Sentence 4.",
            "Sentence 2 MUST include the orientation lock clause:",
            "  - the same face of the box that is visible in the second image faces the camera",
            "  - the packaging must NOT be mirrored, flipped, rotated upside-down, text-reversed",
            "  - 'preserve the box's proportions exactly as shown in the second image —",
            "    do not stretch, narrow, or distort the box'",
            "  DO NOT specify any physical orientation in the prompt (no 'landscape',",
            "  'portrait', 'wider than tall', 'long horizontal side', or similar). The",
            "  second image carries orientation; the prompt only says 'match the second image'.",
            "Sentence 2 MUST include positive + negative position re-anchoring",
            "  (e.g. 'at chest level, not above her head, not at her hip').",
            "Sentence 3 MUST include the anatomy sanity clause with occlusion handling",
            "  (exactly two arms, two hands, TWO LEGS, five fingers per hand;",
            "   fingers and hands occluded by the product or her body still fully exist —",
            "   do not omit them because they are hidden; no extra limbs, no extra digits,",
            "   no fused or warped fingers).",
            "Sentence 4 MUST include the single product clause at its start",
            "  ('exactly ONE physical Alluvi product is visible — never two copies, never",
            "   duplicates'; for mirror-reflection scenarios add 'the mirror reflection",
            "   counts as the same product').",
            "Include the white base preservation clause in Sentence 4.",
            "Word count for step_2_image_prompt: 360-450 (450-480 acceptable for complex scenarios).",
        ]
    )

    print(f"[prompt_builder_qwen] Step 2 (oriented variant) -> Opus 4.7 for scenario {scenario['id']}")
    response = _get_client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    output = _parse_json(response.content[0].text)

    wc = output.get("word_count", 0)
    print(f"[prompt_builder_qwen]   Step 2 done: word_count={wc}")
    return output


# ──────────────────────────────────────────────────────────────────────────
# 2. Orientation picker (NEW — separate, smaller Opus call)
# ──────────────────────────────────────────────────────────────────────────

def pick_product_orientation(step_2_image_prompt: str, scenario_id: str = "?") -> dict:
    """
    Pick which pre-rotated product reference image to pair with this prompt.

    Drives a SEPARATE Opus 4.7 call with orientation_picker_prompt.md as the
    system prompt. The picker reads the holding-pose description in
    Sentence 2 of the produced prompt and returns one of four labels:
      horizontal | vertical | 45_right | 45_left

    The picker is the only place in the pipeline that knows orientation
    files exist. It is fully decoupled from the Step 2 prompt builder
    above.

    Args:
        step_2_image_prompt: the produced step_2_image_prompt string
                             (the value of the "step_2_image_prompt" key
                             in the build_step_2_prompt_qwen output)
        scenario_id: optional, for logging only

    Returns:
        dict {"orientation": str, "reasoning": str}
        — orientation is guaranteed to be one of the 4 valid labels.
    """
    if not PICKER_SYSTEM_PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"missing picker system prompt: {PICKER_SYSTEM_PROMPT_PATH}"
        )

    system_prompt = PICKER_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    user_message = "\n".join(
        [
            "=== STEP 2 IMAGE PROMPT (already produced) ===",
            step_2_image_prompt,
            "",
            "=== TASK ===",
            "Read Sentence 2 of the prompt above (the holding-pose description).",
            "Pick one of: horizontal, vertical, 45_right, 45_left.",
            "Default to horizontal when in doubt.",
            "Output JSON only, exactly the schema in your system prompt.",
        ]
    )

    print(f"[prompt_builder_qwen] orientation picker -> Opus 4.7 for scenario {scenario_id}")
    response = _get_client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,  # picker output is tiny
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text
    try:
        out = _parse_json(raw)
    except Exception as e:
        # Defensive fallback — never let the picker crash the run
        print(f"[prompt_builder_qwen]   picker JSON parse failed ({e}); raw output:\n{raw}")
        return {
            "orientation": "horizontal",
            "reasoning": "picker JSON parse failed, defaulted to horizontal",
            "raw_output": raw,
        }

    orientation = str(out.get("orientation", "")).strip()
    reasoning = str(out.get("reasoning", "")).strip()

    if orientation not in VALID_ORIENTATIONS:
        print(
            f"[prompt_builder_qwen]   picker returned invalid orientation "
            f"'{orientation}', defaulting to horizontal"
        )
        return {
            "orientation": "horizontal",
            "reasoning": (
                f"picker returned invalid value '{orientation}', "
                f"defaulted to horizontal. original_reasoning: {reasoning}"
            ),
        }

    print(f"[prompt_builder_qwen]   picker chose: {orientation}  ({reasoning})")
    return {"orientation": orientation, "reasoning": reasoning}