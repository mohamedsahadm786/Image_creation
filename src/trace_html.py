"""
trace_html.py — visual reports.

  - write_chain_html(scenario_dir, record)  : per-scenario chain visual
  - write_overview_html(run_dir, records, metadata) : run-level grid
"""

import html
import json
from pathlib import Path


def write_chain_html(scenario_dir: Path, record: dict) -> None:
    scenario = record.get("scenario", {})
    sc_id = scenario.get("id", "?")


    # Persona-absent archetypes don't have a source persona to compare against
    archetype = scenario.get("archetype", "")
    no_persona = archetype in ("flat_lay", "object_in_lineup")

    if no_persona:
        cover_files = [
            ("Step 0", "(no persona — flat-lay scenario)", None),
            ("Step 1", "Scene with empty product slot", "03_step1_persona.jpg"),
            ("Step 2", "Final composite", "05_step2_final.jpg"),
        ]
    else:
        # Path traverses: scenario_dir → run_ts → runs → outputs → project_root → assets
        cover_files = [
            ("Step 0", "Source persona.jpg", "../../../../assets/persona.jpg"),
            ("Step 1", "Persona scene (no product)", "03_step1_persona.jpg"),
            ("Step 2", "Final composite", "05_step2_final.jpg"),
        ]

    step_1_prompt = (
        record.get("step_1_output", {}).get("step_1_image_prompt", "(not generated)")
    )
    step_2_prompt = (
        record.get("step_2_output", {}).get("step_2_image_prompt", "(not generated)")
    )

    cards = []
    for label, caption, src in cover_files:
        if src is None:
            # Intentional empty slot (e.g. flat-lay has no persona source)
            cards.append(
                f"""<div class="stage">
  <div class="stage-label">{label} — {html.escape(caption)}</div>
  <div class="stage-empty">no persona in this scenario</div>
</div>"""
            )
        else:
            cards.append(
                f"""<div class="stage">
  <div class="stage-label">{label} — {html.escape(caption)}</div>
  <img src="{html.escape(src)}" alt="{html.escape(caption)}"
       onerror="this.outerHTML='<div class=stage-empty>not generated</div>'">
</div>"""
            )


    final_status = record.get("final_status", "?")
    badge = (
        '<span class="badge badge-ok">SUCCESS</span>'
        if final_status == "success"
        else '<span class="badge badge-fail">FAILED</span>'
    )

    error_block = ""
    if final_status != "success" and record.get("error_message"):
        error_block = f"""<div class="error-block">
  <strong>Error:</strong> {html.escape(record["error_message"])}
</div>"""

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{sc_id} — chain</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
       margin:0;padding:24px;background:#F4F6F8;color:#1F2937}}
  h1{{margin:0 0 6px 0;font-size:18px}}
  .meta{{color:#6B7280;font-size:13px;margin-bottom:24px}}
  .meta-pill{{display:inline-block;background:#fff;padding:3px 10px;
             border-radius:4px;border:1px solid #E5E7EB;margin-right:6px;font-size:12px}}
  .stage-row{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:28px}}
  .stage{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;overflow:hidden}}
  .stage-label{{padding:10px 12px;border-bottom:1px solid #E5E7EB;font-size:12px;
               font-weight:600;background:#F9FAFB}}
  .stage img{{width:100%;display:block;aspect-ratio:9/16;object-fit:cover;background:#F3F4F6}}
  .stage-empty{{aspect-ratio:9/16;background:#F3F4F6;display:flex;
               align-items:center;justify-content:center;color:#9CA3AF;font-size:12px}}
  .prompts{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;padding:18px}}
  .prompts h3{{margin:0 0 8px;font-size:13px;color:#374151;text-transform:uppercase;
              letter-spacing:.5px}}
  .prompt-block{{background:#F9FAFB;border:1px solid #E5E7EB;border-radius:6px;
                padding:12px;font-size:12.5px;line-height:1.55;
                font-family:ui-monospace,'SF Mono',Menlo,monospace;
                margin-bottom:18px;white-space:pre-wrap}}
  .badge{{display:inline-block;padding:3px 9px;border-radius:12px;
         font-size:10.5px;font-weight:600;margin-left:6px}}
  .badge-ok{{background:#D1FAE5;color:#065F46}}
  .badge-fail{{background:#FEE2E2;color:#991B1B}}
  .error-block{{background:#FFF7ED;border-left:3px solid #F97316;padding:10px 14px;
                margin-bottom:18px;border-radius:4px;font-size:13px;color:#7C2D12}}
</style>
</head>
<body>
<h1>{html.escape(sc_id)} {badge}</h1>
<div class="meta">
  <span class="meta-pill"><strong>{html.escape(scenario.get('category', '?'))}</strong></span>
  <span class="meta-pill">{html.escape(scenario.get('archetype', '?'))}</span>
  <span class="meta-pill">{html.escape(scenario.get('difficulty', '?'))}</span>
  <span class="meta-pill">plan: {html.escape(record.get('plan', '?'))}</span>
</div>

{error_block}

<div class="stage-row">
{''.join(cards)}
</div>

<div class="prompts">
  <h3>Step 1 prompt → fal-ai/flux-pulid (or kontext for Plan B)</h3>
  <div class="prompt-block">{html.escape(step_1_prompt)}</div>

  <h3>Step 2 prompt → fal-ai/nano-banana-2/edit</h3>
  <div class="prompt-block">{html.escape(step_2_prompt)}</div>
</div>
</body>
</html>
"""
    (scenario_dir / "chain.html").write_text(html_doc, encoding="utf-8")


def write_overview_html(run_dir: Path, records: list[dict], metadata: dict) -> None:
    success = sum(1 for r in records if r.get("final_status") == "success")
    failed = len(records) - success

    def _safe_cost(record: dict) -> float:
        """Sum step 1 + step 2 cost for a record, gracefully handling None values."""
        s1 = record.get("step_1_output") or {}
        s2 = record.get("step_2_output") or {}
        c1 = s1.get("cost_usd", 0) if isinstance(s1, dict) else 0
        c2 = s2.get("cost_usd", 0) if isinstance(s2, dict) else 0
        # Note: cost_usd may live in step_X_meta dict instead — check both
        return (c1 or 0) + (c2 or 0)

    total_cost = sum(_safe_cost(r) for r in records)


    cards = []
    for r in records:
        sc = r.get("scenario", {})
        sc_id = sc.get("id", "?")
        ok = r.get("final_status") == "success"
        badge_class = "badge-ok" if ok else "badge-fail"
        badge_text = "SUCCESS" if ok else "FAILED"

        final_path = f"{sc_id}/05_step2_final.jpg"
        chain_path = f"{sc_id}/chain.html"

        cards.append(
            f"""
<div class="card">
  <div class="card-header">
    <span class="card-id">{html.escape(sc_id)}</span>
    <span class="badge {badge_class}">{badge_text}</span>
  </div>
  <a href="{html.escape(chain_path)}" class="card-img-link">
    <img src="{html.escape(final_path)}" alt="{html.escape(sc_id)}"
         onerror="this.outerHTML='<div class=card-empty>not generated</div>'">
  </a>
  <div class="card-meta">
    <span class="meta-pill">{html.escape(sc.get('category','?'))}</span>
    <span class="meta-pill">{html.escape(sc.get('difficulty','?'))}</span>
  </div>
</div>"""
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Alluvi v2 run — {metadata.get('timestamp','?')}</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
       margin:0;padding:0;background:#F4F6F8;color:#1F2937}}
  header{{background:#2C3E50;color:#fff;padding:24px 32px}}
  header h1{{margin:0 0 6px;font-size:22px;font-weight:600}}
  header .meta{{font-size:13px;opacity:.85}}
  .summary-bar{{display:flex;gap:22px;padding:16px 32px;background:#fff;
               border-bottom:1px solid #E5E7EB;font-size:14px}}
  .summary-bar .stat{{display:flex;gap:6px}}
  .summary-bar .stat-label{{color:#6B7280}}
  .summary-bar .stat-value{{font-weight:600}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));
        gap:20px;padding:24px 32px}}
  .card{{background:#fff;border:1px solid #E5E7EB;border-radius:10px;overflow:hidden}}
  .card-header{{padding:10px 14px;border-bottom:1px solid #E5E7EB;
               display:flex;justify-content:space-between;align-items:center}}
  .card-id{{font-family:ui-monospace,monospace;font-size:11px;color:#6B7280}}
  .card-img-link{{display:block;text-decoration:none}}
  .card img{{width:100%;display:block;aspect-ratio:9/16;object-fit:cover;background:#F3F4F6}}
  .card-empty{{aspect-ratio:9/16;background:#F3F4F6;display:flex;align-items:center;
              justify-content:center;color:#9CA3AF;font-size:12px}}
  .card-meta{{padding:8px 14px;border-top:1px solid #E5E7EB}}
  .meta-pill{{display:inline-block;background:#F3F4F6;padding:3px 9px;
             border-radius:4px;color:#4B5563;font-size:11px;margin-right:4px}}
  .badge{{display:inline-block;padding:3px 9px;border-radius:12px;
         font-size:10.5px;font-weight:600}}
  .badge-ok{{background:#D1FAE5;color:#065F46}}
  .badge-fail{{background:#FEE2E2;color:#991B1B}}
</style>
</head>
<body>
<header>
  <h1>Alluvi v2 — {html.escape(metadata.get('plan','?'))}{' (PILOT)' if metadata.get('pilot_mode') else ''}</h1>
  <div class="meta">
    Run: {html.escape(metadata.get('timestamp','?'))} ·
    Scenarios: {len(records)}
  </div>
</header>
<div class="summary-bar">
  <div class="stat"><span class="stat-label">Total:</span> <span class="stat-value">{len(records)}</span></div>
  <div class="stat"><span class="stat-label">Success:</span> <span class="stat-value" style="color:#065F46">{success}</span></div>
  <div class="stat"><span class="stat-label">Failed:</span> <span class="stat-value" style="color:#991B1B">{failed}</span></div>
  <div class="stat"><span class="stat-label">Cost:</span> <span class="stat-value">${total_cost:.2f}</span></div>
</div>
<div class="grid">
{''.join(cards)}
</div>
</body>
</html>
"""
    (run_dir / "overview.html").write_text(html_doc, encoding="utf-8")