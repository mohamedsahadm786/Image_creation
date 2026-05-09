"""
trace_html_batch.py — visual reports for the qwen_tuned_prompt batch runner.

Self-contained — does NOT import or modify the parent trace_html.py.

Outputs:
  - write_chain_html(out_dir, record): per-scenario 5-panel A/B/C viewer
  - write_overview_html(batch_dir, records, summary): grid of all scenarios
    showing 3-up cards (NB / Qwen-v1 / Qwen-v2)

Path math: chain.html sits at
  experiments/step2_qwen_edit_2511/qwen_tuned_prompt/batch_runner/outputs/<ts>_batch/<sid>/chain.html
which is 7 directory levels deep from project root, so persona.jpg references
use 7 "../" segments.
"""

import html
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────
# Per-scenario 5-panel chain.html (the A/B/C drill-down)
# ──────────────────────────────────────────────────────────────────────────

def write_chain_html(out_dir: Path, record: dict) -> None:
    scenario = record.get("scenario", {})
    sc_id = scenario.get("id", "?")
    archetype = scenario.get("archetype", "")
    no_persona = archetype in ("flat_lay", "object_in_lineup")

    model_label = record.get("model_label", "Qwen (qwen-tuned prompt)")
    final_status = record.get("final_status", "?")
    error_message = record.get("error_message")

    # 7 levels up from {sid}/chain.html → project root → assets/persona.jpg
    persona_rel = "../../../../../../../assets/persona.jpg"

    if no_persona:
        step_0 = ("Step 0", "(no persona — flat-lay scenario)", None)
    else:
        step_0 = ("Step 0", "Source persona.jpg", persona_rel)

    panels = [
        step_0,
        ("Step 1 — PuLID", "Persona scene (no product)", "03_step1_persona.jpg"),
        ("Step 2a — Nano Banana", "NB-shaped prompt", "05_step2_nb.jpg"),
        ("Step 2b — Qwen v1", "OLD NB-shaped prompt", "05_step2_qwen_v1.jpg"),
        ("Step 2c — Qwen v2 (NEW)", "Qwen-tuned prompt", "05_step2_qwen_v2.jpg"),
    ]

    cards = []
    for label, caption, src in panels:
        accent = "stage-new" if "v2" in label else ""
        if src is None:
            cards.append(
                f"""<div class="stage {accent}">
  <div class="stage-label">{html.escape(label)}<br><span class="stage-cap">{html.escape(caption)}</span></div>
  <div class="stage-empty">no persona in this scenario</div>
</div>"""
            )
        else:
            cards.append(
                f"""<div class="stage {accent}">
  <div class="stage-label">{html.escape(label)}<br><span class="stage-cap">{html.escape(caption)}</span></div>
  <img src="{html.escape(src)}" alt="{html.escape(caption)}"
       onerror="this.outerHTML='<div class=stage-empty>not provided</div>'">
</div>"""
            )

    step_1_prompt = (
        record.get("step_1_output", {}).get("step_1_image_prompt", "(not available)")
    )
    nb_prompt = (
        record.get("step_2_nb_prompt", {}).get("step_2_image_prompt", "(not available)")
    )
    qwen_prompt = (
        record.get("step_2_qwen_prompt", {}).get("step_2_image_prompt", "(not available)")
    )

    nb_wc = record.get("step_2_nb_prompt", {}).get("word_count", "—")
    qwen_wc = record.get("step_2_qwen_prompt", {}).get("word_count", "—")

    nb_meta = record.get("step_2_nb_meta") or {}
    v1_meta = record.get("step_2_qwen_v1_meta") or {}
    v2_meta = record.get("step_2_qwen_v2_meta") or {}

    def _fmt_seconds(meta):
        s = meta.get("elapsed_seconds")
        return f"{s:.1f}s" if isinstance(s, (int, float)) else "—"

    def _fmt_cost(meta, key="cost_usd"):
        c = meta.get(key)
        return f"${c:.3f}" if isinstance(c, (int, float)) else "—"

    badge = (
        '<span class="badge badge-ok">SUCCESS</span>'
        if final_status == "success"
        else '<span class="badge badge-fail">FAILED</span>'
    )

    error_block = ""
    if final_status != "success" and error_message:
        error_block = f"""<div class="error-block">
  <strong>Run failed:</strong> {html.escape(str(error_message))}
</div>"""

    reused_run = record.get("reused_run_path", "?")
    qwen_v1_reused = record.get("qwen_v1_reused_path") or "(none)"

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html.escape(sc_id)} — Qwen-tuned prompt batch</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
       margin:0;padding:24px;background:#F4F6F8;color:#1F2937;max-width:1700px;margin:0 auto}}
  h1{{margin:0 0 6px 0;font-size:18px;padding:24px 24px 0}}
  .meta{{color:#6B7280;font-size:13px;margin-bottom:12px;padding:0 24px}}
  .meta-pill{{display:inline-block;background:#fff;padding:3px 10px;
             border-radius:4px;border:1px solid #E5E7EB;margin-right:6px;font-size:12px}}
  .reused{{color:#6B7280;font-size:11px;margin-bottom:18px;padding:0 24px;
          font-family:ui-monospace,'SF Mono',Menlo,monospace;line-height:1.7}}
  .stage-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;
             margin:0 24px 24px}}
  .stage{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;overflow:hidden}}
  .stage.stage-new{{border:2px solid #7C3AED;box-shadow:0 0 0 2px #EDE9FE}}
  .stage-label{{padding:8px 10px;border-bottom:1px solid #E5E7EB;font-size:11px;
               font-weight:600;background:#F9FAFB;line-height:1.4;min-height:46px}}
  .stage-new .stage-label{{background:#F5F3FF;color:#5B21B6}}
  .stage-cap{{font-weight:400;color:#6B7280;font-size:10px}}
  .stage img{{width:100%;display:block;aspect-ratio:9/16;object-fit:cover;background:#F3F4F6}}
  .stage-empty{{aspect-ratio:9/16;background:#F3F4F6;display:flex;
               align-items:center;justify-content:center;color:#9CA3AF;font-size:11px;
               text-align:center;padding:0 8px}}
  .compare-strip{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;
                 padding:14px 18px;margin:0 24px 18px;font-size:13px;
                 display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}}
  .compare-strip .col-title{{font-weight:600;margin-bottom:6px;font-size:12px;
                            text-transform:uppercase;letter-spacing:.5px;color:#374151}}
  .compare-strip .col.col-new .col-title{{color:#5B21B6}}
  .compare-strip .col-row{{color:#6B7280;font-size:12px;line-height:1.7}}
  .compare-strip .col-row strong{{color:#1F2937;font-weight:600}}
  .prompts{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;padding:18px;margin:0 24px}}
  .prompts h3{{margin:0 0 8px;font-size:13px;color:#374151;text-transform:uppercase;
              letter-spacing:.5px}}
  .prompts h3.h3-new{{color:#5B21B6}}
  .prompt-block{{background:#F9FAFB;border:1px solid #E5E7EB;border-radius:6px;
                padding:12px;font-size:12.5px;line-height:1.55;
                font-family:ui-monospace,'SF Mono',Menlo,monospace;
                margin-bottom:18px;white-space:pre-wrap;word-wrap:break-word}}
  .prompt-block.prompt-new{{background:#F5F3FF;border-color:#DDD6FE}}
  .prompt-pair{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:8px}}
  .prompt-meta{{font-size:11px;color:#6B7280;margin-bottom:4px;
               font-family:ui-monospace,'SF Mono',Menlo,monospace}}
  .badge{{display:inline-block;padding:3px 9px;border-radius:12px;
         font-size:10.5px;font-weight:600;margin-left:6px}}
  .badge-ok{{background:#D1FAE5;color:#065F46}}
  .badge-fail{{background:#FEE2E2;color:#991B1B}}
  .badge-experiment{{background:#EDE9FE;color:#5B21B6;margin-left:0;margin-right:6px}}
  .error-block{{background:#FFF7ED;border-left:3px solid #F97316;padding:10px 14px;
                margin:0 24px 18px;border-radius:4px;font-size:13px;color:#7C2D12}}
  .back{{display:inline-block;margin:24px 24px 0;color:#6B7280;font-size:12px;text-decoration:none}}
  .back:hover{{color:#1F2937;text-decoration:underline}}
</style>
</head>
<body>
<a class="back" href="../overview.html">← Back to overview</a>
<h1>
  <span class="badge badge-experiment">QWEN-TUNED PROMPT</span>
  {html.escape(sc_id)} — A/B/C comparison {badge}
</h1>
<div class="meta">
  <span class="meta-pill"><strong>{html.escape(scenario.get('category', '?'))}</strong></span>
  <span class="meta-pill">{html.escape(scenario.get('archetype', '?'))}</span>
  <span class="meta-pill">{html.escape(scenario.get('difficulty', '?'))}</span>
  <span class="meta-pill">model: {html.escape(model_label)}</span>
</div>
<div class="reused">
  reused step 1 + NB baseline: {html.escape(reused_run)}<br>
  reused qwen v1 (old prompt): {html.escape(qwen_v1_reused)}
</div>

{error_block}

<div class="stage-row">
{''.join(cards)}
</div>

<div class="compare-strip">
  <div class="col">
    <div class="col-title">Step 2a — Nano Banana baseline</div>
    <div class="col-row">endpoint: <strong>fal-ai/nano-banana-2/edit</strong></div>
    <div class="col-row">prompt: <strong>NB-shaped, {html.escape(str(nb_wc))} words</strong></div>
    <div class="col-row">elapsed: <strong>{_fmt_seconds(nb_meta)}</strong></div>
    <div class="col-row">cost: <strong>{_fmt_cost(nb_meta)}</strong></div>
  </div>
  <div class="col">
    <div class="col-title">Step 2b — Qwen v1 (OLD prompt)</div>
    <div class="col-row">endpoint: <strong>fal-ai/qwen-image-edit-2511</strong></div>
    <div class="col-row">prompt: <strong>NB-shaped, {html.escape(str(nb_wc))} words</strong></div>
    <div class="col-row">elapsed: <strong>{_fmt_seconds(v1_meta)}</strong></div>
    <div class="col-row">cost: <strong>{_fmt_cost(v1_meta)}</strong></div>
  </div>
  <div class="col col-new">
    <div class="col-title">Step 2c — Qwen v2 (NEW prompt)</div>
    <div class="col-row">endpoint: <strong>fal-ai/qwen-image-edit-2511</strong></div>
    <div class="col-row">prompt: <strong>Qwen-tuned, {html.escape(str(qwen_wc))} words</strong></div>
    <div class="col-row">elapsed: <strong>{_fmt_seconds(v2_meta)}</strong></div>
    <div class="col-row">cost qwen: <strong>{_fmt_cost(v2_meta, 'cost_qwen_api_usd')}</strong></div>
    <div class="col-row">cost opus: <strong>{_fmt_cost(v2_meta, 'cost_opus_prompt_usd')}</strong></div>
  </div>
</div>

<div class="prompts">
  <h3>Step 1 prompt → fal-ai/flux-pulid (reused from baseline run)</h3>
  <div class="prompt-block">{html.escape(step_1_prompt)}</div>

  <div class="prompt-pair">
    <div>
      <h3>Step 2 prompt — OLD (NB-shaped, fed to NB AND Qwen v1)</h3>
      <div class="prompt-meta">{html.escape(str(nb_wc))} words · model-agnostic / Nano-Banana-tuned</div>
      <div class="prompt-block">{html.escape(nb_prompt)}</div>
    </div>
    <div>
      <h3 class="h3-new">Step 2 prompt — NEW (Qwen-tuned, fed to Qwen v2)</h3>
      <div class="prompt-meta">{html.escape(str(qwen_wc))} words · uses positional refs, orientation lock, anatomy clause</div>
      <div class="prompt-block prompt-new">{html.escape(qwen_prompt)}</div>
    </div>
  </div>
</div>
</body>
</html>
"""
    (out_dir / "chain.html").write_text(html_doc, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# Batch overview.html — 3-up A/B/C grid of all scenarios
# ──────────────────────────────────────────────────────────────────────────

def write_overview_html(batch_dir: Path, records: list, summary: dict) -> None:
    """
    Render an overview.html at the batch root. Each card shows three images
    side-by-side: Nano Banana (left) / Qwen-v1 OLD prompt (middle) /
    Qwen-v2 NEW Qwen-tuned prompt (right, accented). Click → chain.html.
    """
    n = len(records)
    succeeded = summary.get("succeeded", 0)
    failed = summary.get("failed", 0)
    actual_cost = summary.get("actual_cost_usd", 0)
    elapsed = summary.get("elapsed_seconds", 0)
    timestamp = summary.get("timestamp", "?")
    model_label = summary.get("model_label", "Qwen (qwen-tuned prompt)")
    reuse_root = summary.get("reuse_run_root", "?")
    qwen_v1_root = summary.get("qwen_v1_root", "(none)")
    interrupted = summary.get("interrupted", False)

    cards = []
    for r in records:
        sc = r.get("scenario", {}) or {}
        sc_id = sc.get("id", "?")
        ok = r.get("final_status") == "success"
        badge_class = "badge-ok" if ok else "badge-fail"
        badge_text = "SUCCESS" if ok else "FAILED"

        nb_img = f"{sc_id}/05_step2_nb.jpg"
        v1_img = f"{sc_id}/05_step2_qwen_v1.jpg"
        v2_img = f"{sc_id}/05_step2_qwen_v2.jpg"
        chain_path = f"{sc_id}/chain.html"

        v2_meta = r.get("step_2_qwen_v2_meta") or {}
        elapsed_s = v2_meta.get("elapsed_seconds")
        elapsed_str = f"{elapsed_s:.1f}s" if isinstance(elapsed_s, (int, float)) else "—"

        qwen_wc = r.get("step_2_qwen_prompt", {}).get("word_count", "—")

        cards.append(
            f"""
<div class="card">
  <div class="card-header">
    <span class="card-id">{html.escape(sc_id)}</span>
    <span class="badge {badge_class}">{badge_text}</span>
  </div>
  <a href="{html.escape(chain_path)}" class="card-img-link">
    <div class="card-imgs">
      <div class="card-img-third">
        <div class="card-img-tag">NB</div>
        <img src="{html.escape(nb_img)}" alt="nano banana"
             onerror="this.outerHTML='<div class=card-empty>—</div>'">
      </div>
      <div class="card-img-third">
        <div class="card-img-tag tag-v1">Qwen v1</div>
        <img src="{html.escape(v1_img)}" alt="qwen old prompt"
             onerror="this.outerHTML='<div class=card-empty>—</div>'">
      </div>
      <div class="card-img-third card-img-new">
        <div class="card-img-tag tag-v2">Qwen v2</div>
        <img src="{html.escape(v2_img)}" alt="qwen new prompt"
             onerror="this.outerHTML='<div class=card-empty>—</div>'">
      </div>
    </div>
  </a>
  <div class="card-meta">
    <span class="meta-pill">{html.escape(sc.get('category','?'))}</span>
    <span class="meta-pill">{html.escape(sc.get('archetype','?'))}</span>
    <span class="meta-pill">{html.escape(sc.get('difficulty','?'))}</span>
    <span class="meta-pill">qwen v2: {html.escape(elapsed_str)}</span>
    <span class="meta-pill">{html.escape(str(qwen_wc))}w prompt</span>
  </div>
</div>"""
        )

    title_suffix = " (interrupted)" if interrupted else ""

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Qwen-tuned prompt batch — {html.escape(timestamp)}</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
       margin:0;padding:0;background:#F4F6F8;color:#1F2937}}
  header{{background:#5B21B6;color:#fff;padding:24px 32px}}
  header h1{{margin:0 0 6px;font-size:22px;font-weight:600}}
  header .meta{{font-size:13px;opacity:.85;font-family:ui-monospace,'SF Mono',Menlo,monospace;line-height:1.7}}
  .summary-bar{{display:flex;gap:22px;padding:16px 32px;background:#fff;
               border-bottom:1px solid #E5E7EB;font-size:14px;flex-wrap:wrap}}
  .summary-bar .stat{{display:flex;gap:6px}}
  .summary-bar .stat-label{{color:#6B7280}}
  .summary-bar .stat-value{{font-weight:600}}
  .legend{{padding:10px 32px;background:#F9FAFB;border-bottom:1px solid #E5E7EB;
          font-size:12px;color:#6B7280}}
  .legend strong{{color:#1F2937}}
  .legend .v2-callout{{color:#5B21B6;font-weight:600}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(540px,1fr));
        gap:20px;padding:24px 32px}}
  .card{{background:#fff;border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;
        transition:box-shadow .15s ease}}
  .card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.08)}}
  .card-header{{padding:10px 14px;border-bottom:1px solid #E5E7EB;
               display:flex;justify-content:space-between;align-items:center}}
  .card-id{{font-family:ui-monospace,monospace;font-size:11px;color:#6B7280}}
  .card-img-link{{display:block;text-decoration:none;color:inherit}}
  .card-imgs{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:0}}
  .card-img-third{{position:relative;background:#F3F4F6}}
  .card-img-third.card-img-new{{box-shadow:inset 0 0 0 2px #7C3AED}}
  .card-img-third img{{width:100%;display:block;aspect-ratio:9/16;object-fit:cover}}
  .card-img-tag{{position:absolute;top:6px;left:6px;background:rgba(0,0,0,.6);
                color:#fff;font-size:9px;font-weight:600;padding:2px 6px;border-radius:3px;
                z-index:2;letter-spacing:.5px}}
  .card-img-tag.tag-v1{{background:rgba(30,58,138,.85)}}
  .card-img-tag.tag-v2{{background:rgba(91,33,182,.95)}}
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
  <h1>Qwen-tuned prompt — Step 2 A/B/C experiment{html.escape(title_suffix)}</h1>
  <div class="meta">
    {html.escape(timestamp)} · model: {html.escape(model_label)}<br>
    plan-a-root: {html.escape(reuse_root)}<br>
    qwen-v1-root: {html.escape(qwen_v1_root)}
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
  Each card: <strong>NB (left)</strong> · <strong>Qwen v1 — OLD NB-shaped prompt (middle)</strong> · <span class="v2-callout">Qwen v2 — NEW Qwen-tuned prompt (right, purple-bordered)</span>. Click a card for the full 5-panel chain.html with prompt diff.
</div>
<div class="grid">
{''.join(cards)}
</div>
</body>
</html>
"""
    (batch_dir / "overview.html").write_text(html_doc, encoding="utf-8")