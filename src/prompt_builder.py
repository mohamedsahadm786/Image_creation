"""
prompt_builder.py — Opus 4.7 prompt generation for Step 1 and Step 2.

Two top-level functions:
  - build_step_1_prompt(scenario)                                  -> dict
  - build_step_2_prompt(scenario, step_1_output)                   -> dict

Each calls Claude Opus 4.7 with the corresponding system prompt
(prompts/master_prompt_step1.md or master_prompt_step2.md) and returns
the parsed JSON envelope.

Static context (persona.yaml, brand.yaml, do_dont.md, product.yaml) is loaded
once and cached — these don't change between scenarios.
"""

import os
import re
import json
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

CLAUDE_MODEL = "claude-opus-4-7"

# System prompt paths
STEP_1_SYSTEM_PATH = Path("prompts/master_prompt_step1.md")
STEP_2_SYSTEM_PATH = Path("prompts/master_prompt_step2.md")

# Static context paths
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
        msg = "Missing required context files:\n" + "\n".join(
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
# STEP 1 — PuLID prompt builder
# ──────────────────────────────────────────────────────────────────────────

def build_step_1_prompt(scenario: dict) -> dict:
    """
    Build the Step 1 prompt envelope (PuLID call) for one scenario.
    Returns the parsed JSON output from Opus.
    """
    if not STEP_1_SYSTEM_PATH.exists():
        raise FileNotFoundError(f"missing system prompt: {STEP_1_SYSTEM_PATH}")

    system_prompt = STEP_1_SYSTEM_PATH.read_text(encoding="utf-8")
    ctx = _load_static_context()

    user_message = "\n".join(
        [
            "=== persona.yaml (USE prompt_descriptors VERBATIM) ===",
            ctx["persona_yaml"],
            "",
            "=== brand.yaml (vibe + palette context) ===",
            ctx["brand_yaml"],
            "",
            "=== do_dont.md (compliance rules) ===",
            ctx["do_dont_md"],
            "",
            "=== SCENARIO ===",
            json.dumps(scenario, indent=2),
            "",
            "=== TASK ===",
            "Build the Step 1 prompt envelope for this scenario.",
            "Output JSON matching the v2 Step 1 schema.",
            "Use scenario.outfit verbatim — never the persona reference photo's outfit.",
            "Use persona.yaml prompt_descriptors verbatim — never paraphrase.",
            "NO product mentioned. NO placeholder. The product hand is empty.",
            "Word count for step_1_image_prompt: 130-160 (200-250 acceptable for close-ups).",
        ]
    )

    print(f"[prompt_builder] Step 1 -> Opus 4.7 for scenario {scenario['id']}")
    response = _get_client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    output = _parse_json(response.content[0].text)

    wc = output.get("word_count", 0)
    slot_type = output.get("product_slot", {}).get("type", "?")
    print(f"[prompt_builder]   Step 1 done: word_count={wc}, slot_type={slot_type}")
    return output


# ──────────────────────────────────────────────────────────────────────────
# STEP 2 — Nano Banana 2 prompt builder
# ──────────────────────────────────────────────────────────────────────────

def build_step_2_prompt(scenario: dict, step_1_output: dict) -> dict:
    """
    Build the Step 2 prompt envelope (Nano Banana 2 Edit call).
    Receives both the original scenario AND the Step 1 output (which has
    the product_slot bridge data and the lighting language to echo).
    """
    if not STEP_2_SYSTEM_PATH.exists():
        raise FileNotFoundError(f"missing system prompt: {STEP_2_SYSTEM_PATH}")

    system_prompt = STEP_2_SYSTEM_PATH.read_text(encoding="utf-8")
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
            "Build the Step 2 prompt envelope.",
            "Use 'Image 1' (Step 1 scene) and 'Image 2' (product.jpg) reference syntax.",
            "Echo Step 1's lighting language verbatim in the lighting hook.",
            "Include the anti-hallucination phrase verbatim.",
            "Include the preserve clause verbatim.",
            "Word count for step_2_image_prompt: 100-140 (175-200 acceptable for complex).",
        ]
    )

    print(f"[prompt_builder] Step 2 -> Opus 4.7 for scenario {scenario['id']}")
    response = _get_client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=3072,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    output = _parse_json(response.content[0].text)

    wc = output.get("word_count", 0)
    print(f"[prompt_builder]   Step 2 done: word_count={wc}")
    return output