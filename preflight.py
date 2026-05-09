"""
preflight.py — Pre-run validation for Alluvi v2 pipeline.

Validates that every required file exists, every API key is set, every Python
dependency is installed, and every Python module is importable. Catches all
common setup errors before you spend any API credits on a real run.

Run:  python preflight.py

Exits with code 0 on success, 1 on any error.
"""

import os
import sys
from pathlib import Path

print("\n" + "=" * 72)
print(" ALLUVI v2 — PREFLIGHT CHECK")
print("=" * 72 + "\n")

errors: list[str] = []
warnings: list[str] = []


# ──────────────────────────────────────────────────────────────────────────
# 1. .env API keys
# ──────────────────────────────────────────────────────────────────────────
print("[1/7] Checking .env keys...")
try:
    from dotenv import load_dotenv

    load_dotenv()
    for key_name in ("ANTHROPIC_API_KEY", "FAL_KEY"):
        if os.getenv(key_name):
            value = os.getenv(key_name)
            masked = value[:8] + "..." + value[-4:] if len(value) > 16 else "***"
            print(f"  OK     {key_name} = {masked}")
        else:
            errors.append(f".env missing {key_name}")
            print(f"  MISSING {key_name}")
except ImportError:
    errors.append("python-dotenv not installed: run `pip install python-dotenv`")
    print("  ERROR  python-dotenv not installed")


# ──────────────────────────────────────────────────────────────────────────
# 2. Asset files
# ──────────────────────────────────────────────────────────────────────────
print("\n[2/7] Checking asset files...")
asset_files = [
    ("assets/persona.jpg", "Plan A Step 1 reference"),
    ("assets/persona_face_only.jpg", "Plan B Step 1 reference (cropped face)"),
    ("assets/persona.yaml", "Persona identity descriptor"),
    ("assets/product.jpg", "Step 2 product reference"),
    ("assets/product.yaml", "Product packaging descriptor"),
]
for fpath, role in asset_files:
    p = Path(fpath)
    if p.exists():
        size_kb = p.stat().st_size / 1024
        print(f"  OK     {fpath:<40} ({size_kb:>6.1f} KB)  -- {role}")
    else:
        errors.append(f"missing asset file: {fpath} ({role})")
        print(f"  MISSING {fpath}  -- {role}")


# ──────────────────────────────────────────────────────────────────────────
# 3. Brand & compliance files
# ──────────────────────────────────────────────────────────────────────────
print("\n[3/7] Checking brand & compliance files...")
brand_files = [
    "brand/brand.yaml",
    "brand/do_dont.md",
]
for fpath in brand_files:
    p = Path(fpath)
    if p.exists() and p.stat().st_size > 100:
        print(f"  OK     {fpath} ({p.stat().st_size:,} bytes)")
    elif p.exists():
        warnings.append(f"{fpath} exists but is suspiciously small")
        print(f"  WARN   {fpath} (only {p.stat().st_size} bytes)")
    else:
        errors.append(f"missing brand file: {fpath}")
        print(f"  MISSING {fpath}")


# ──────────────────────────────────────────────────────────────────────────
# 4. Scenarios + prompt templates
# ──────────────────────────────────────────────────────────────────────────
print("\n[4/7] Checking scenarios & prompt templates...")
required_files = [
    ("scenarios/scenarios.yaml", "30 hand-curated scenarios"),
    ("prompts/master_prompt_step1.md", "Step 1 PuLID system prompt"),
    ("prompts/master_prompt_step2.md", "Step 2 Nano Banana 2 system prompt"),
]
for fpath, role in required_files:
    p = Path(fpath)
    if p.exists() and p.stat().st_size > 1000:
        print(f"  OK     {fpath:<45} ({p.stat().st_size:>6,} bytes)  -- {role}")
    elif p.exists():
        warnings.append(f"{fpath} exists but is small ({p.stat().st_size} bytes)")
        print(f"  WARN   {fpath} (only {p.stat().st_size} bytes)")
    else:
        errors.append(f"missing required file: {fpath}")
        print(f"  MISSING {fpath}")



# ──────────────────────────────────────────────────────────────────────────
# 5. scenarios.yaml structure validation (FULL — every scenario, not spot-check)
# ──────────────────────────────────────────────────────────────────────────
print("\n[5/7] Validating scenarios.yaml structure...")
scenarios_path = Path("scenarios/scenarios.yaml")
if scenarios_path.exists():
    try:
        # Use the same archetype-aware validator the pipeline uses at runtime,
        # so preflight cannot pass while the pipeline crashes on startup.
        sys.path.insert(0, str(Path.cwd()))
        from src.scenario_loader import load_scenarios

        scenarios = load_scenarios()
        print(f"  OK     {len(scenarios)} scenarios loaded and validated")

        # Distribution breakdown so you can sanity-check at a glance:
        from collections import Counter
        by_archetype = Counter(s["archetype"] for s in scenarios)
        by_difficulty = Counter(s["difficulty"] for s in scenarios)
        by_category = Counter(s["category"] for s in scenarios)

        print(f"  INFO   by archetype : {dict(by_archetype)}")
        print(f"  INFO   by difficulty: {dict(by_difficulty)}")
        print(f"  INFO   by category  : {dict(by_category)}")

    except ImportError as e:
        errors.append(f"could not import scenario_loader: {e}")
        print(f"  ERROR  import failed: {e}")
    except FileNotFoundError as e:
        errors.append(str(e))
        print(f"  ERROR  {e}")
    except ValueError as e:
        # ValueError from load_scenarios() contains ALL validation errors,
        # one per line — surface them so the user can fix in one pass.
        errors.append("scenarios.yaml validation failed (see lines below)")
        print(f"  ERROR  scenarios.yaml validation FAILED:")
        for line in str(e).splitlines():
            print(f"         {line}")
    except Exception as e:
        errors.append(f"scenarios.yaml unexpected error: {type(e).__name__}: {e}")
        print(f"  ERROR  {type(e).__name__}: {e}")
else:
    print("  SKIP   scenarios.yaml missing (already reported in step 4)")


# ──────────────────────────────────────────────────────────────────────────
# 6. Python dependencies
# ──────────────────────────────────────────────────────────────────────────
print("\n[6/7] Checking Python dependencies...")
deps = [
    ("anthropic", "Claude Opus 4.7 / Sonnet 4.6 SDK"),
    ("fal_client", "fal.ai endpoint client"),
    ("requests", "HTTP downloads"),
    ("dotenv", "via python-dotenv"),
    ("yaml", "via PyYAML"),
    ("PIL", "via Pillow"),
    ("openpyxl", "Excel export"),
]
for module_name, role in deps:
    try:
        mod = __import__(module_name)
        version = getattr(mod, "__version__", "?")
        print(f"  OK     {module_name:<15} {version:<12}  -- {role}")
    except ImportError:
        errors.append(f"missing dependency: {module_name} -- run `pip install -r requirements.txt`")
        print(f"  MISSING {module_name}  -- {role}")

# sqlite3 is stdlib but verify
try:
    import sqlite3
    print(f"  OK     sqlite3         {sqlite3.sqlite_version:<12}  -- stdlib (database)")
except ImportError:
    errors.append("sqlite3 not available (Python stdlib problem)")


# ──────────────────────────────────────────────────────────────────────────
# 7. Project module imports
# ──────────────────────────────────────────────────────────────────────────
print("\n[7/7] Checking project module imports...")
sys.path.insert(0, str(Path.cwd()))

src_modules = [
    "src.db",
    "src.scenario_loader",
    "src.prompt_builder",
    "src.step_1_pulid",
    "src.step_2_nano_banana",
    "src.trace_html",
]
for mod_name in src_modules:
    try:
        __import__(mod_name)
        print(f"  OK     {mod_name}")
    except ModuleNotFoundError as e:
        if "src" in str(e):
            errors.append(f"missing project file: {mod_name.replace('.', '/')}.py")
            print(f"  MISSING {mod_name}")
        else:
            errors.append(f"{mod_name} failed to import: {e}")
            print(f"  ERROR  {mod_name}: {e}")
    except Exception as e:
        errors.append(f"{mod_name} import failed: {type(e).__name__}: {e}")
        print(f"  ERROR  {mod_name}: {type(e).__name__}: {e}")


# ──────────────────────────────────────────────────────────────────────────
# VERDICT
# ──────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 72)
if not errors:
    print(" PREFLIGHT PASSED")
    print("=" * 72)
    print("\nReady to run:")
    print("  python -m pipelines.run_plan_a --pilot   # 5 easy scenarios first")
    print("  python -m pipelines.run_plan_a            # all 30 scenarios")
    print("\nEstimated cost:  ~$0.08-$0.12 per image  (~$3.00 for full 30)")
    print("Estimated time:  ~2 min per image          (~60 min for full 30, sequential)")
    if warnings:
        print(f"\n{len(warnings)} non-blocking warning(s):")
        for w in warnings:
            print(f"  - {w}")
    print()
    sys.exit(0)
else:
    print(f" PREFLIGHT FAILED — {len(errors)} error(s)")
    print("=" * 72)
    print("\nErrors to fix before running:\n")
    for e in errors:
        print(f"  X {e}")
    if warnings:
        print(f"\n{len(warnings)} additional warning(s):")
        for w in warnings:
            print(f"  - {w}")
    print()
    sys.exit(1)