"""
trace_html.py — single-run 5-panel A/B/C chain viewer for the qwen_tuned_prompt experiment.

Renders chain.html with:
  Panel 1: Step 0 — source persona.jpg (or empty for flat-lay scenarios)
  Panel 2: Step 1 — PuLID output (03_step1_persona.jpg)
  Panel 3: Step 2a — Nano Banana baseline (05_step2_nb.jpg)
  Panel 4: Step 2b — Qwen with OLD NB-shaped prompt (05_step2_qwen_v1.jpg)
  Panel 5: Step 2c — Qwen with NEW Qwen-tuned prompt (05_step2_qwen_v2.jpg)

Path math: chain.html sits at
  experiments/step2_qwen_edit_2511/qwen_tuned_prompt/outputs/<ts>_<sid>/chain.html
which is 5 levels deep, so persona.jpg references use 5 "../" segments.
"""

import html
from pathlib import Path


def write_chain_html(out_dir: Path, record: dict) -> None:
    scenario = record.get("scenario", {})
    sc_id = scenario.get("id", "?")
    archetype = scenario.get("archetype", "")
    no_persona = archetype in ("flat_lay", "object_in_lineup")

    model_label = record.get("model_label", "Qwen (qwen-tuned prompt)")
    final_status = record.get("final_status", "?")
    error_message = record.get("error_message")

    # 5 levels up from {sid}/chain.html → project root → assets/persona.jpg
    persona_rel = "../../../../../assets/persona.jpg"

    if no_persona:
        step_0 = ("Step 0", "(no persona — flat-lay scenario)", None)
    else:
        step_0 = ("Step 0", "Source persona.jpg", persona_rel)

    panels = [
        step_0,
        ("Step 1 — PuLID", "Persona scene (no product)", "03_step1_persona.jpg"),
        ("Step 2a — Nano Banana (baseline)",
         "NB with NB-shaped prompt", "05_step2_nb.jpg"),
        ("Step 2b — Qwen v1 (NB-shaped prompt)",
         "Qwen with OLD prompt", "05_step2_qwen_v1.jpg"),
        ("Step 2c — Qwen v2 (NEW Qwen-tuned prompt)",
         "Qwen with NEW prompt", "05_step2_qwen_v2.jpg"),
    ]

    cards = []
    for label, caption, src in panels:
        accent = ""
        if "v2" in label:
            accent = "stage-new"
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
    qwen_v1_reused = record.get("qwen_v1_reused_path") or "(none — v1 panel will show 'not provided')"

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html.escape(sc_id)} — Qwen-tuned prompt A/B/C</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
       margin:0;padding:24px;background:#F4F6F8;color:#1F2937;max-width:1600px;margin:0 auto}}
  h1{{margin:0 0 6px 0;font-size:18px;padding:24px 24px 0}}
  .meta{{color:#6B7280;font-size:13px;margin-bottom:12px;padding:0 24px}}
  .meta-pill{{display:inline-block;background:#fff;padding:3px 10px;
             border-radius:4px;border:1px solid #E5E7EB;margin-right:6px;font-size:12px}}
  .reused{{color:#6B7280;font-size:11px;margin-bottom:18px;padding:0 24px;
          font-family:ui-monospace,'SF Mono',Menlo,monospace;line-height:1.7}}
  .stage-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;
             margin:0 24px 24px;padding:0}}
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
  .prompts{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;padding:18px;
           margin:0 24px}}
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
</style>
</head>
<body>
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
    <div class="col-row">seed: <strong>{html.escape(str(nb_meta.get('seed', '—')))}</strong></div>
  </div>
  <div class="col">
    <div class="col-title">Step 2b — Qwen v1 (OLD prompt)</div>
    <div class="col-row">endpoint: <strong>fal-ai/qwen-image-edit-2511</strong></div>
    <div class="col-row">prompt: <strong>NB-shaped, {html.escape(str(nb_wc))} words</strong></div>
    <div class="col-row">elapsed: <strong>{_fmt_seconds(v1_meta)}</strong></div>
    <div class="col-row">cost: <strong>{_fmt_cost(v1_meta)}</strong></div>
    <div class="col-row">seed: <strong>{html.escape(str(v1_meta.get('seed', '—')))}</strong></div>
  </div>
  <div class="col col-new">
    <div class="col-title">Step 2c — Qwen v2 (NEW Qwen-tuned prompt)</div>
    <div class="col-row">endpoint: <strong>fal-ai/qwen-image-edit-2511</strong></div>
    <div class="col-row">prompt: <strong>Qwen-tuned, {html.escape(str(qwen_wc))} words</strong></div>
    <div class="col-row">elapsed: <strong>{_fmt_seconds(v2_meta)}</strong></div>
    <div class="col-row">cost qwen: <strong>{_fmt_cost(v2_meta, 'cost_qwen_api_usd')}</strong></div>
    <div class="col-row">cost opus: <strong>{_fmt_cost(v2_meta, 'cost_opus_prompt_usd')}</strong></div>
    <div class="col-row">seed: <strong>{html.escape(str(v2_meta.get('seed', '—')))}</strong></div>
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