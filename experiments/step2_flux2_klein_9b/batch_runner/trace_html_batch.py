"""
trace_html_batch.py — visual reports for the FLUX-2-Klein-9B batch runner.

Self-contained — does NOT import or modify the parent trace_html.py.

  - write_chain_html(out_dir, record)              : per-scenario 4-panel A/B viewer
  - write_overview_html(batch_dir, records, summary): grid of all scenarios with
                                                      Nano Banana / FLUX-2-Klein side-by-side

Path math note: chain.html sits at
  experiments/step2_flux2_klein_9b/batch_runner/outputs/<ts>_batch/<sid>/chain.html
which is 6 directory levels deep from project root, so persona.jpg references
use "../../../../../../assets/persona.jpg" (6 "../" segments).
"""

import html
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────
# Per-scenario 4-panel chain.html (the A/B drill-down)
# ──────────────────────────────────────────────────────────────────────────

def write_chain_html(out_dir: Path, record: dict) -> None:
    scenario = record.get("scenario", {})
    sc_id = scenario.get("id", "?")
    archetype = scenario.get("archetype", "")
    no_persona = archetype in ("flat_lay", "object_in_lineup")

    model_label = record.get("model_label", "FLUX-2-Klein-9B")
    final_status = record.get("final_status", "?")
    error_message = record.get("error_message")

    # 6 levels up from {sid}/chain.html → project root, then assets/persona.jpg
    persona_rel = "../../../../../../assets/persona.jpg"

    if no_persona:
        step_0 = ("Step 0", "(no persona — flat-lay scenario)", None)
    else:
        step_0 = ("Step 0", "Source persona.jpg", persona_rel)

    panels = [
        step_0,
        ("Step 1 — PuLID", "Persona scene (no product)", "03_step1_persona.jpg"),
        ("Step 2 — Nano Banana (baseline)",
         "Existing Plan A output", "05_step2_nano_banana.jpg"),
        (f"Step 2 — {model_label} (NEW)",
         "Experiment output", "05_step2_flux2_klein_final.jpg"),
    ]

    cards = []
    for label, caption, src in panels:
        if src is None:
            cards.append(
                f"""<div class="stage">
  <div class="stage-label">{html.escape(label)} — {html.escape(caption)}</div>
  <div class="stage-empty">no persona in this scenario</div>
</div>"""
            )
        else:
            cards.append(
                f"""<div class="stage">
  <div class="stage-label">{html.escape(label)} — {html.escape(caption)}</div>
  <img src="{html.escape(src)}" alt="{html.escape(caption)}"
       onerror="this.outerHTML='<div class=stage-empty>not generated</div>'">
</div>"""
            )

    step_1_prompt = (
        record.get("step_1_output", {}).get("step_1_image_prompt", "(not available)")
    )
    step_2_prompt = (
        record.get("step_2_output", {}).get("step_2_image_prompt", "(not available)")
    )

    nb_meta = record.get("step_2_nano_banana_meta") or {}
    flux2_meta = record.get("step_2_flux2_meta") or {}

    def _fmt_seconds(meta):
        s = meta.get("elapsed_seconds")
        return f"{s:.1f}s" if isinstance(s, (int, float)) else "—"

    def _fmt_cost(meta):
        c = meta.get("cost_usd")
        return f"${c:.3f}" if isinstance(c, (int, float)) else "—"

    nb_time = _fmt_seconds(nb_meta)
    flux2_time = _fmt_seconds(flux2_meta)
    nb_cost = _fmt_cost(nb_meta)
    flux2_cost = _fmt_cost(flux2_meta)
    nb_seed = nb_meta.get("seed", "—")
    flux2_seed = flux2_meta.get("seed", "—")

    badge = (
        '<span class="badge badge-ok">SUCCESS</span>'
        if final_status == "success"
        else '<span class="badge badge-fail">FAILED</span>'
    )

    error_block = ""
    if final_status != "success" and error_message:
        error_block = f"""<div class="error-block">
  <strong>FLUX call failed:</strong> {html.escape(str(error_message))}
</div>"""

    reused_run = record.get("reused_run_path", "?")

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html.escape(sc_id)} — FLUX-2-Klein-9B Step 2 batch</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
       margin:0;padding:24px;background:#F4F6F8;color:#1F2937}}
  h1{{margin:0 0 6px 0;font-size:18px}}
  .meta{{color:#6B7280;font-size:13px;margin-bottom:12px}}
  .meta-pill{{display:inline-block;background:#fff;padding:3px 10px;
             border-radius:4px;border:1px solid #E5E7EB;margin-right:6px;font-size:12px}}
  .reused{{color:#6B7280;font-size:11px;margin-bottom:18px;
          font-family:ui-monospace,'SF Mono',Menlo,monospace}}
  .stage-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
  .stage{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;overflow:hidden}}
  .stage-label{{padding:8px 10px;border-bottom:1px solid #E5E7EB;font-size:11px;
               font-weight:600;background:#F9FAFB;line-height:1.4}}
  .stage img{{width:100%;display:block;aspect-ratio:9/16;object-fit:cover;background:#F3F4F6}}
  .stage-empty{{aspect-ratio:9/16;background:#F3F4F6;display:flex;
               align-items:center;justify-content:center;color:#9CA3AF;font-size:11px;
               text-align:center;padding:0 8px}}
  .compare-strip{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;
                 padding:14px 18px;margin-bottom:18px;font-size:13px;
                 display:grid;grid-template-columns:1fr 1fr;gap:14px}}
  .compare-strip .col-title{{font-weight:600;margin-bottom:6px;font-size:12px;
                            text-transform:uppercase;letter-spacing:.5px;color:#374151}}
  .compare-strip .col-row{{color:#6B7280;font-size:12px;line-height:1.7}}
  .compare-strip .col-row strong{{color:#1F2937;font-weight:600}}
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
  .badge-experiment{{background:#FEF3C7;color:#78350F;margin-left:0;margin-right:6px}}
  .error-block{{background:#FFF7ED;border-left:3px solid #F97316;padding:10px 14px;
                margin-bottom:18px;border-radius:4px;font-size:13px;color:#7C2D12}}
  .back{{display:inline-block;margin-bottom:14px;color:#6B7280;font-size:12px;
        text-decoration:none}}
  .back:hover{{color:#1F2937;text-decoration:underline}}
</style>
</head>
<body>
<a class="back" href="../overview.html">← Back to overview</a>
<h1>
  <span class="badge badge-experiment">EXPERIMENT</span>
  {html.escape(sc_id)} — Step 2 model swap {badge}
</h1>
<div class="meta">
  <span class="meta-pill"><strong>{html.escape(scenario.get('category', '?'))}</strong></span>
  <span class="meta-pill">{html.escape(scenario.get('archetype', '?'))}</span>
  <span class="meta-pill">{html.escape(scenario.get('difficulty', '?'))}</span>
  <span class="meta-pill">model: {html.escape(model_label)}</span>
</div>
<div class="reused">reused step 1 from: {html.escape(reused_run)}</div>

{error_block}

<div class="stage-row">
{''.join(cards)}
</div>

<div class="compare-strip">
  <div class="col">
    <div class="col-title">Step 2 — Nano Banana (baseline)</div>
    <div class="col-row">endpoint: <strong>fal-ai/nano-banana-2/edit</strong></div>
    <div class="col-row">elapsed: <strong>{nb_time}</strong></div>
    <div class="col-row">cost: <strong>{nb_cost}</strong></div>
    <div class="col-row">seed: <strong>{html.escape(str(nb_seed))}</strong></div>
  </div>
  <div class="col">
    <div class="col-title">Step 2 — {html.escape(model_label)} (this experiment)</div>
    <div class="col-row">endpoint: <strong>{html.escape(flux2_meta.get('endpoint', 'fal-ai/flux-2/klein/9b/edit'))}</strong></div>
    <div class="col-row">elapsed: <strong>{flux2_time}</strong></div>
    <div class="col-row">cost: <strong>{flux2_cost}</strong></div>
    <div class="col-row">seed: <strong>{html.escape(str(flux2_seed))}</strong></div>
  </div>
</div>

<div class="prompts">
  <h3>Step 1 prompt → fal-ai/flux-pulid (reused from baseline run)</h3>
  <div class="prompt-block">{html.escape(step_1_prompt)}</div>

  <h3>Step 2 prompt (same prompt fed to BOTH models)</h3>
  <div class="prompt-block">{html.escape(step_2_prompt)}</div>
</div>
</body>
</html>
"""
    (out_dir / "chain.html").write_text(html_doc, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# Batch overview.html — A/B grid of all scenarios
# ──────────────────────────────────────────────────────────────────────────

def write_overview_html(batch_dir: Path, records: list, summary: dict) -> None:
    """
    Render an overview.html at the batch root showing a grid of cards.
    Each card displays Nano Banana (left) next to FLUX-2-Klein-9B (right) and
    links to that scenario's chain.html.
    """
    n = len(records)
    succeeded = summary.get("succeeded", 0)
    failed = summary.get("failed", 0)
    actual_cost = summary.get("actual_cost_usd", 0)
    elapsed = summary.get("elapsed_seconds", 0)
    timestamp = summary.get("timestamp", "?")
    model_label = summary.get("model_label", "FLUX-2-Klein-9B")
    reuse_root = summary.get("reuse_run_root", "?")
    interrupted = summary.get("interrupted", False)

    cards = []
    for r in records:
        sc = r.get("scenario", {}) or {}
        sc_id = sc.get("id", "?")
        ok = r.get("final_status") == "success"
        badge_class = "badge-ok" if ok else "badge-fail"
        badge_text = "SUCCESS" if ok else "FAILED"

        flux2_img = f"{sc_id}/05_step2_flux2_klein_final.jpg"
        nb_img = f"{sc_id}/05_step2_nano_banana.jpg"
        chain_path = f"{sc_id}/chain.html"

        fmeta = r.get("step_2_flux2_meta") or {}
        elapsed_s = fmeta.get("elapsed_seconds")
        elapsed_str = f"{elapsed_s:.1f}s" if isinstance(elapsed_s, (int, float)) else "—"

        cards.append(
            f"""
<div class="card">
  <div class="card-header">
    <span class="card-id">{html.escape(sc_id)}</span>
    <span class="badge {badge_class}">{badge_text}</span>
  </div>
  <a href="{html.escape(chain_path)}" class="card-img-link">
    <div class="card-imgs">
      <div class="card-img-half">
        <div class="card-img-tag">NB</div>
        <img src="{html.escape(nb_img)}" alt="nano banana"
             onerror="this.outerHTML='<div class=card-empty>—</div>'">
      </div>
      <div class="card-img-half">
        <div class="card-img-tag tag-flux">FLUX</div>
        <img src="{html.escape(flux2_img)}" alt="flux-2-klein"
             onerror="this.outerHTML='<div class=card-empty>—</div>'">
      </div>
    </div>
  </a>
  <div class="card-meta">
    <span class="meta-pill">{html.escape(sc.get('category','?'))}</span>
    <span class="meta-pill">{html.escape(sc.get('archetype','?'))}</span>
    <span class="meta-pill">{html.escape(sc.get('difficulty','?'))}</span>
    <span class="meta-pill">{html.escape(elapsed_str)}</span>
  </div>
</div>"""
        )

    title_suffix = " (interrupted)" if interrupted else ""

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FLUX-2-Klein-9B Step 2 batch — {html.escape(timestamp)}</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
       margin:0;padding:0;background:#F4F6F8;color:#1F2937}}
  header{{background:#78350F;color:#fff;padding:24px 32px}}
  header h1{{margin:0 0 6px;font-size:22px;font-weight:600}}
  header .meta{{font-size:13px;opacity:.85;font-family:ui-monospace,'SF Mono',Menlo,monospace}}
  .summary-bar{{display:flex;gap:22px;padding:16px 32px;background:#fff;
               border-bottom:1px solid #E5E7EB;font-size:14px;flex-wrap:wrap}}
  .summary-bar .stat{{display:flex;gap:6px}}
  .summary-bar .stat-label{{color:#6B7280}}
  .summary-bar .stat-value{{font-weight:600}}
  .legend{{padding:10px 32px;background:#F9FAFB;border-bottom:1px solid #E5E7EB;
          font-size:12px;color:#6B7280}}
  .legend strong{{color:#1F2937}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));
        gap:20px;padding:24px 32px}}
  .card{{background:#fff;border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;
        transition:box-shadow .15s ease}}
  .card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.08)}}
  .card-header{{padding:10px 14px;border-bottom:1px solid #E5E7EB;
               display:flex;justify-content:space-between;align-items:center}}
  .card-id{{font-family:ui-monospace,monospace;font-size:11px;color:#6B7280}}
  .card-img-link{{display:block;text-decoration:none;color:inherit}}
  .card-imgs{{display:grid;grid-template-columns:1fr 1fr;gap:0}}
  .card-img-half{{position:relative;background:#F3F4F6}}
  .card-img-half img{{width:100%;display:block;aspect-ratio:9/16;object-fit:cover}}
  .card-img-tag{{position:absolute;top:6px;left:6px;background:rgba(0,0,0,.6);
                color:#fff;font-size:9px;font-weight:600;padding:2px 6px;border-radius:3px;
                z-index:2;letter-spacing:.5px}}
  .card-img-tag.tag-flux{{background:rgba(120,53,15,.85)}}
  .card-empty{{aspect-ratio:9/16;background:#F3F4F6;display:flex;align-items:center;
              justify-content:center;color:#9CA3AF;font-size:12px}}
  .card-meta{{padding:8px 14px;border-top:1px solid #E5E7EB}}
  .meta-pill{{display:inline-block;background:#F3F4F6;padding:3px 9px;
             border-radius:4px;color:#4B5563;font-size:11px;margin-right:4px;margin-bottom:2px}}
  .badge{{display:inline-block;padding:3px 9px;border-radius:12px;
         font-size:10.5px;font-weight:600}}
  .badge-ok{{background:#D1FAE5;color:#065F46}}
  .badge-fail{{background:#FEE2E2;color:#991B1B}}
</style>
</head>
<body>
<header>
  <h1>FLUX-2-Klein-9B — Step 2 swap experiment{html.escape(title_suffix)}</h1>
  <div class="meta">
    {html.escape(timestamp)} ·
    reuse-root: {html.escape(reuse_root)} ·
    model: {html.escape(model_label)}
  </div>
</header>
<div class="summary-bar">
  <div class="stat"><span class="stat-label">Total:</span> <span class="stat-value">{n}</span></div>
  <div class="stat"><span class="stat-label">Success:</span> <span class="stat-value" style="color:#065F46">{succeeded}</span></div>
  <div class="stat"><span class="stat-label">Failed:</span> <span class="stat-value" style="color:#991B1B">{failed}</span></div>
  <div class="stat"><span class="stat-label">Cost:</span> <span class="stat-value">${actual_cost:.2f}</span></div>
  <div class="stat"><span class="stat-label">Elapsed:</span> <span class="stat-value">{elapsed:.0f}s ({elapsed/60:.1f} min)</span></div>
</div>
<div class="legend">
  Each card shows <strong>Nano Banana (left)</strong> next to <strong>FLUX-2-Klein-9B (right)</strong>. Click a card to open the full 4-panel chain.html.
</div>
<div class="grid">
{''.join(cards)}
</div>
</body>
</html>
"""
    (batch_dir / "overview.html").write_text(html_doc, encoding="utf-8")