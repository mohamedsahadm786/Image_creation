"""
trace_html.py — single-run 4-panel A/B chain viewer for the
flux_tuned_prompt experiment.

Renders chain.html with:
  Panel 1: Step 0 — source persona.jpg
  Panel 2: Step 1 — PuLID output
  Panel 3: Step 2a — Nano Banana baseline
  Panel 4: Step 2b — FLUX-2 Klein 9B Base Edit with FLUX-tuned prompt
                     (orange-bordered)

Plus:
  - Compare strip showing endpoint / elapsed / cost / params per stage
  - OLD prompt vs NEW prompt diff (side-by-side)
  - negative_prompt displayed for FLUX side
"""

import html
from pathlib import Path


def write_chain_html(out_dir: Path, record: dict) -> None:
    scenario = record.get("scenario", {})
    sc_id = scenario.get("id", "?")
    archetype = scenario.get("archetype", "")
    no_persona = archetype in ("flat_lay", "object_in_lineup")

    model_label = record.get("model_label", "FLUX (tuned)")
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
        ("Step 2b — FLUX (NEW)",
         "FLUX with FLUX-tuned prompt", "05_step2_flux.jpg"),
    ]

    cards = []
    for label, caption, src in panels:
        accent = "stage-new" if "FLUX" in label else ""
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
    flux_prompt = (
        record.get("step_2_flux_prompt", {}).get("step_2_image_prompt", "(not available)")
    )
    flux_negative = (
        record.get("step_2_flux_prompt", {}).get("negative_prompt", "(not provided)")
    )

    nb_wc = record.get("step_2_nb_prompt", {}).get("word_count", "—")
    flux_wc = record.get("step_2_flux_prompt", {}).get("word_count", "—")

    flux_params = record.get("step_2_flux_prompt", {}).get("fal_flux_params", {})
    guidance = flux_params.get("guidance_scale", "—")
    steps = flux_params.get("num_inference_steps", "—")

    nb_meta = record.get("step_2_nb_meta") or {}
    flux_meta = record.get("step_2_flux_meta") or {}

    def _fmt_seconds(meta):
        s = meta.get("elapsed_seconds")
        return f"{s:.1f}s" if isinstance(s, (int, float)) else "—"

    def _fmt_cost(meta, key="cost_usd"):
        c = meta.get(key)
        return f"${c:.3f}" if isinstance(c, (int, float)) else "—"

    def _fmt_seed(meta):
        s = meta.get("seed")
        return str(s) if s is not None else "—"

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

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html.escape(sc_id)} — FLUX-tuned A/B</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
       margin:0;padding:24px;background:#F4F6F8;color:#1F2937;max-width:1500px;margin:0 auto}}
  h1{{margin:0 0 6px 0;font-size:18px;padding:24px 24px 0}}
  .meta{{color:#6B7280;font-size:13px;margin-bottom:12px;padding:0 24px}}
  .meta-pill{{display:inline-block;background:#fff;padding:3px 10px;
             border-radius:4px;border:1px solid #E5E7EB;margin-right:6px;font-size:12px}}
  .reused{{color:#6B7280;font-size:11px;margin-bottom:12px;padding:0 24px;
          font-family:ui-monospace,'SF Mono',Menlo,monospace;line-height:1.7}}
  .stage-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;
             margin:0 24px 24px;padding:0}}
  .stage{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;overflow:hidden}}
  .stage.stage-new{{border:2px solid #EA580C;box-shadow:0 0 0 2px #FED7AA}}
  .stage-label{{padding:8px 10px;border-bottom:1px solid #E5E7EB;font-size:11px;
               font-weight:600;background:#F9FAFB;line-height:1.4;min-height:46px}}
  .stage-new .stage-label{{background:#FFF7ED;color:#9A3412}}
  .stage-cap{{font-weight:400;color:#6B7280;font-size:10px}}
  .stage img{{width:100%;display:block;aspect-ratio:9/16;object-fit:cover;background:#F3F4F6;
             cursor:zoom-in}}
  .stage-empty{{aspect-ratio:9/16;background:#F3F4F6;display:flex;
               align-items:center;justify-content:center;color:#9CA3AF;font-size:11px;
               text-align:center;padding:0 8px}}
  .compare-strip{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;
                 padding:14px 18px;margin:0 24px 18px;font-size:13px;
                 display:grid;grid-template-columns:1fr 1fr;gap:14px}}
  .compare-strip .col-title{{font-weight:600;margin-bottom:6px;font-size:12px;
                            text-transform:uppercase;letter-spacing:.5px;color:#374151}}
  .compare-strip .col.col-new .col-title{{color:#9A3412}}
  .compare-strip .col-row{{color:#6B7280;font-size:12px;line-height:1.7}}
  .compare-strip .col-row strong{{color:#1F2937;font-weight:600}}
  .prompts{{background:#fff;border:1px solid #E5E7EB;border-radius:8px;padding:18px;margin:0 24px}}
  .prompts h3{{margin:0 0 8px;font-size:13px;color:#374151;text-transform:uppercase;
              letter-spacing:.5px}}
  .prompts h3.h3-new{{color:#9A3412}}
  .prompt-block{{background:#F9FAFB;border:1px solid #E5E7EB;border-radius:6px;
                padding:12px;font-size:12.5px;line-height:1.55;
                font-family:ui-monospace,'SF Mono',Menlo,monospace;
                margin-bottom:18px;white-space:pre-wrap;word-wrap:break-word}}
  .prompt-block.prompt-new{{background:#FFF7ED;border-color:#FED7AA}}
  .prompt-block.prompt-negative{{background:#FEF2F2;border-color:#FECACA;color:#7F1D1D}}
  .prompt-pair{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:8px}}
  .prompt-meta{{font-size:11px;color:#6B7280;margin-bottom:4px;
               font-family:ui-monospace,'SF Mono',Menlo,monospace}}
  .badge{{display:inline-block;padding:3px 9px;border-radius:12px;
         font-size:10.5px;font-weight:600;margin-left:6px}}
  .badge-ok{{background:#D1FAE5;color:#065F46}}
  .badge-fail{{background:#FEE2E2;color:#991B1B}}
  .badge-experiment{{background:#FED7AA;color:#9A3412;margin-left:0;margin-right:6px}}
  .error-block{{background:#FFF7ED;border-left:3px solid #F97316;padding:10px 14px;
                margin:0 24px 18px;border-radius:4px;font-size:13px;color:#7C2D12}}

  /* Lightbox / zoom */
  .lightbox{{display:none;position:fixed;top:0;left:0;width:100vw;height:100vh;
            background:rgba(0,0,0,.85);z-index:1000;cursor:zoom-out;
            align-items:center;justify-content:center}}
  .lightbox.active{{display:flex}}
  .lightbox img{{max-width:95vw;max-height:95vh;object-fit:contain}}
</style>
</head>
<body>
<h1>
  <span class="badge badge-experiment">FLUX TUNED</span>
  {html.escape(sc_id)} — A/B comparison {badge}
</h1>
<div class="meta">
  <span class="meta-pill"><strong>{html.escape(scenario.get('category', '?'))}</strong></span>
  <span class="meta-pill">{html.escape(scenario.get('archetype', '?'))}</span>
  <span class="meta-pill">{html.escape(scenario.get('difficulty', '?'))}</span>
  <span class="meta-pill">model: {html.escape(model_label)}</span>
</div>
<div class="reused">
  reused step 1 + NB baseline: {html.escape(reused_run)}
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
  <div class="col col-new">
    <div class="col-title">Step 2b — FLUX (NEW)</div>
    <div class="col-row">endpoint: <strong>fal-ai/flux-2/klein/9b/base/edit</strong></div>
    <div class="col-row">prompt: <strong>FLUX-tuned, {html.escape(str(flux_wc))} words</strong></div>
    <div class="col-row">guidance_scale: <strong>{html.escape(str(guidance))}</strong> · num_inference_steps: <strong>{html.escape(str(steps))}</strong></div>
    <div class="col-row">negative_prompt: <strong>{'present' if flux_negative and flux_negative != '(not provided)' else 'absent'}</strong></div>
    <div class="col-row">elapsed: <strong>{_fmt_seconds(flux_meta)}</strong></div>
    <div class="col-row">seed: <strong>{_fmt_seed(flux_meta)}</strong></div>
    <div class="col-row">cost flux: <strong>{_fmt_cost(flux_meta, 'cost_flux_api_usd')}</strong> · cost opus: <strong>{_fmt_cost(flux_meta, 'cost_opus_prompt_usd')}</strong></div>
  </div>
</div>

<div class="prompts">
  <h3>Step 1 prompt → fal-ai/flux-pulid (reused from baseline run)</h3>
  <div class="prompt-block">{html.escape(step_1_prompt)}</div>

  <div class="prompt-pair">
    <div>
      <h3>Step 2 prompt — OLD (NB-shaped, fed to NB)</h3>
      <div class="prompt-meta">{html.escape(str(nb_wc))} words · model-agnostic / Nano-Banana-tuned</div>
      <div class="prompt-block">{html.escape(nb_prompt)}</div>
    </div>
    <div>
      <h3 class="h3-new">Step 2 prompt — NEW (FLUX-tuned, fed to FLUX)</h3>
      <div class="prompt-meta">{html.escape(str(flux_wc))} words · guidance_scale={html.escape(str(guidance))}</div>
      <div class="prompt-block prompt-new">{html.escape(flux_prompt)}</div>
      <div class="prompt-meta" style="color:#9A3412">negative_prompt</div>
      <div class="prompt-block prompt-negative">{html.escape(flux_negative)}</div>
    </div>
  </div>
</div>

<div class="lightbox" id="lightbox" onclick="this.classList.remove('active')">
  <img id="lightbox-img" src="" alt="">
</div>

<script>
  document.querySelectorAll('.stage img').forEach(img => {{
    img.addEventListener('click', () => {{
      const lb = document.getElementById('lightbox');
      const lbImg = document.getElementById('lightbox-img');
      lbImg.src = img.src;
      lb.classList.add('active');
    }});
  }});
</script>
</body>
</html>
"""
    (out_dir / "chain.html").write_text(html_doc, encoding="utf-8")