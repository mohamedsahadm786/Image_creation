"""
trace_html_batch.py — visual reports for the flux_tuned_prompt batch runners.

Outputs:
  - write_chain_html(out_dir, record): per-scenario 4-panel chain.html with
    click-to-zoom + back-link to overview
  - write_overview_html(batch_dir, records, summary): 2-up cards
    (NB baseline / FLUX-tuned with orange accent)

Used by both run_batch.py (--plan-a-root mode) and run_batch_full.py
(from-scratch mode). For from-scratch mode, the NB panel will be missing
(no Plan A reuse) — handled gracefully with onerror placeholders.
"""

import html
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────
# Per-scenario chain.html (used by both --plan-a-root and --full modes)
# ──────────────────────────────────────────────────────────────────────────

def write_chain_html(out_dir: Path, record: dict) -> None:
    scenario = record.get("scenario", {})
    sc_id = scenario.get("id", "?")
    archetype = scenario.get("archetype", "")
    no_persona = archetype in ("flat_lay", "object_in_lineup")

    model_label = record.get("model_label", "FLUX (tuned)")
    final_status = record.get("final_status", "?")
    error_message = record.get("error_message")
    error_stage = record.get("error_stage")
    is_full_run = record.get("is_full_run", False)

    # 7 levels up from {sid}/chain.html → project root → assets/persona.jpg
    persona_rel = "../../../../../../../assets/persona.jpg"

    if no_persona:
        step_0 = ("Step 0", "(no persona — flat-lay scenario)", None)
    else:
        step_0 = ("Step 0", "Source persona.jpg", persona_rel)

    step_1_caption = "Persona scene (no product)" + (" — fresh from PuLID" if is_full_run else " — reused from Plan A")

    panels = [step_0, ("Step 1 — PuLID", step_1_caption, "03_step1_persona.jpg")]

    if not is_full_run:
        # In --plan-a-root mode, also show NB baseline for comparison
        panels.append(
            ("Step 2a — Nano Banana", "NB-shaped prompt", "05_step2_nb.jpg")
        )

    panels.append(
        ("Step 2 — FLUX (NEW)", "FLUX-tuned prompt", "05_step2_flux.jpg")
    )

    # Adjust grid to fit panel count
    panel_count = len(panels)

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
        stage_str = f" at stage <code>{html.escape(str(error_stage))}</code>" if error_stage else ""
        error_block = f"""<div class="error-block">
  <strong>Run failed{stage_str}:</strong> {html.escape(str(error_message))}
</div>"""

    reused_run = record.get("reused_run_path", "(from scratch — no Plan A reuse)")

    # Conditional NB compare strip — only show in --plan-a-root mode
    nb_strip = ""
    if not is_full_run:
        nb_strip = f"""
  <div class="col">
    <div class="col-title">Step 2a — Nano Banana baseline</div>
    <div class="col-row">endpoint: <strong>fal-ai/nano-banana-2/edit</strong></div>
    <div class="col-row">prompt: <strong>NB-shaped, {html.escape(str(nb_wc))} words</strong></div>
    <div class="col-row">elapsed: <strong>{_fmt_seconds(nb_meta)}</strong></div>
  </div>"""

    nb_prompt_panel = ""
    if not is_full_run:
        nb_prompt_panel = f"""
    <div>
      <h3>Step 2 prompt — OLD (NB-shaped)</h3>
      <div class="prompt-meta">{html.escape(str(nb_wc))} words</div>
      <div class="prompt-block">{html.escape(nb_prompt)}</div>
    </div>"""

    prompt_pair_class = "prompt-pair" if not is_full_run else "prompt-single"

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html.escape(sc_id)} — FLUX-tuned batch</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
       margin:0;padding:24px;background:#F4F6F8;color:#1F2937;max-width:1700px;margin:0 auto}}
  h1{{margin:0 0 6px 0;font-size:18px;padding:24px 24px 0}}
  .meta{{color:#6B7280;font-size:13px;margin-bottom:12px;padding:0 24px}}
  .meta-pill{{display:inline-block;background:#fff;padding:3px 10px;
             border-radius:4px;border:1px solid #E5E7EB;margin-right:6px;font-size:12px}}
  .reused{{color:#6B7280;font-size:11px;margin-bottom:12px;padding:0 24px;
          font-family:ui-monospace,'SF Mono',Menlo,monospace;line-height:1.7}}
  .stage-row{{display:grid;grid-template-columns:repeat({panel_count},1fr);gap:10px;
             margin:0 24px 24px}}
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
                 display:grid;grid-template-columns:{'1fr 1fr' if not is_full_run else '1fr'};gap:14px}}
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
  .prompt-single{{display:block}}
  .prompt-meta{{font-size:11px;color:#6B7280;margin-bottom:4px;
               font-family:ui-monospace,'SF Mono',Menlo,monospace}}
  .badge{{display:inline-block;padding:3px 9px;border-radius:12px;
         font-size:10.5px;font-weight:600;margin-left:6px}}
  .badge-ok{{background:#D1FAE5;color:#065F46}}
  .badge-fail{{background:#FEE2E2;color:#991B1B}}
  .badge-experiment{{background:#FED7AA;color:#9A3412;margin-left:0;margin-right:6px}}
  .error-block{{background:#FFF7ED;border-left:3px solid #F97316;padding:10px 14px;
                margin:0 24px 18px;border-radius:4px;font-size:13px;color:#7C2D12}}
  .error-block code{{background:#FED7AA;padding:1px 6px;border-radius:3px}}
  .back{{display:inline-block;margin:24px 24px 0;color:#6B7280;font-size:12px;text-decoration:none}}
  .back:hover{{color:#1F2937;text-decoration:underline}}
  .lightbox{{display:none;position:fixed;top:0;left:0;width:100vw;height:100vh;
            background:rgba(0,0,0,.85);z-index:1000;cursor:zoom-out;
            align-items:center;justify-content:center}}
  .lightbox.active{{display:flex}}
  .lightbox img{{max-width:95vw;max-height:95vh;object-fit:contain}}
</style>
</head>
<body>
<a class="back" href="../overview.html">← Back to overview</a>
<h1>
  <span class="badge badge-experiment">FLUX TUNED</span>
  {html.escape(sc_id)} — {'A/B comparison' if not is_full_run else 'from-scratch pipeline'} {badge}
</h1>
<div class="meta">
  <span class="meta-pill"><strong>{html.escape(scenario.get('category', '?'))}</strong></span>
  <span class="meta-pill">{html.escape(scenario.get('archetype', '?'))}</span>
  <span class="meta-pill">{html.escape(scenario.get('difficulty', '?'))}</span>
  <span class="meta-pill">model: {html.escape(model_label)}</span>
</div>
<div class="reused">
  source: {html.escape(reused_run)}
</div>

{error_block}

<div class="stage-row">
{''.join(cards)}
</div>

<div class="compare-strip">
  {nb_strip}
  <div class="col col-new">
    <div class="col-title">Step 2 — FLUX (NEW)</div>
    <div class="col-row">endpoint: <strong>fal-ai/flux-2/klein/9b/base/edit</strong></div>
    <div class="col-row">prompt: <strong>FLUX-tuned, {html.escape(str(flux_wc))} words</strong></div>
    <div class="col-row">guidance_scale: <strong>{html.escape(str(guidance))}</strong> · num_inference_steps: <strong>{html.escape(str(steps))}</strong></div>
    <div class="col-row">negative_prompt: <strong>{'present' if flux_negative and flux_negative != '(not provided)' else 'absent'}</strong></div>
    <div class="col-row">elapsed: <strong>{_fmt_seconds(flux_meta)}</strong> · seed: <strong>{_fmt_seed(flux_meta)}</strong></div>
    <div class="col-row">total cost: <strong>{_fmt_cost(flux_meta, 'cost_total_usd')}</strong></div>
  </div>
</div>

<div class="prompts">
  <h3>Step 1 prompt → fal-ai/flux-pulid {('(reused from Plan A)' if not is_full_run else '(fresh)')}</h3>
  <div class="prompt-block">{html.escape(step_1_prompt)}</div>

  <div class="{prompt_pair_class}">
    {nb_prompt_panel}
    <div>
      <h3 class="h3-new">Step 2 prompt — NEW (FLUX-tuned)</h3>
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


# ──────────────────────────────────────────────────────────────────────────
# Batch overview.html
# ──────────────────────────────────────────────────────────────────────────

def write_overview_html(
    batch_dir: Path,
    records: list,
    summary: dict,
) -> None:
    """2-up overview cards (NB / FLUX) for --plan-a-root mode,
    or single-card layout for --full mode."""
    n = len(records)
    succeeded = summary.get("succeeded", 0)
    failed = summary.get("failed", 0)
    actual_cost = summary.get("actual_cost_usd", 0)
    elapsed = summary.get("elapsed_seconds", 0)
    timestamp = summary.get("timestamp", "?")
    model_label = summary.get("model_label", "FLUX (tuned)")
    reuse_root = summary.get("reuse_run_root", "(from scratch — no Plan A reuse)")
    interrupted = summary.get("interrupted", False)
    is_full_run = summary.get("is_full_run", False)

    failure_stages: dict[str, int] = {}
    for r in records:
        if r.get("final_status") != "success":
            stage = r.get("error_stage", "unknown")
            failure_stages[stage] = failure_stages.get(stage, 0) + 1

    cards = []
    for r in records:
        sc = r.get("scenario", {}) or {}
        sc_id = sc.get("id", "?")
        ok = r.get("final_status") == "success"
        badge_class = "badge-ok" if ok else "badge-fail"
        badge_text = "SUCCESS" if ok else "FAILED"

        nb_img = f"{sc_id}/05_step2_nb.jpg"
        flux_img = f"{sc_id}/05_step2_flux.jpg"
        chain_path = f"{sc_id}/chain.html"

        flux_meta = r.get("step_2_flux_meta") or {}
        elapsed_s = flux_meta.get("elapsed_seconds")
        elapsed_str = f"{elapsed_s:.1f}s" if isinstance(elapsed_s, (int, float)) else "—"

        flux_wc = r.get("step_2_flux_prompt", {}).get("word_count", "—")
        error_stage = r.get("error_stage", "")

        error_pill = ""
        if not ok and error_stage:
            error_pill = f'<span class="meta-pill" style="background:#FEE2E2;color:#991B1B">failed: {html.escape(error_stage)}</span>'

        # In --full mode, single-image card (no NB column)
        if is_full_run:
            cards.append(
                f"""
<div class="card">
  <div class="card-header">
    <span class="card-id">{html.escape(sc_id)}</span>
    <span class="badge {badge_class}">{badge_text}</span>
  </div>
  <a href="{html.escape(chain_path)}" class="card-img-link">
    <div class="card-imgs card-imgs-single">
      <div class="card-img-full card-img-new">
        <div class="card-img-tag tag-flux">FLUX (tuned)</div>
        <img src="{html.escape(flux_img)}" alt="flux output"
             onerror="this.outerHTML='<div class=card-empty>—</div>'">
      </div>
    </div>
  </a>
  <div class="card-meta">
    <span class="meta-pill">{html.escape(sc.get('category','?'))}</span>
    <span class="meta-pill">{html.escape(sc.get('archetype','?'))}</span>
    <span class="meta-pill">{html.escape(sc.get('difficulty','?'))}</span>
    <span class="meta-pill">flux: {html.escape(elapsed_str)}</span>
    <span class="meta-pill">{html.escape(str(flux_wc))}w prompt</span>
    {error_pill}
  </div>
</div>"""
            )
        else:
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
        <img src="{html.escape(nb_img)}" alt="nb baseline"
             onerror="this.outerHTML='<div class=card-empty>—</div>'">
      </div>
      <div class="card-img-half card-img-new">
        <div class="card-img-tag tag-flux">FLUX (tuned)</div>
        <img src="{html.escape(flux_img)}" alt="flux output"
             onerror="this.outerHTML='<div class=card-empty>—</div>'">
      </div>
    </div>
  </a>
  <div class="card-meta">
    <span class="meta-pill">{html.escape(sc.get('category','?'))}</span>
    <span class="meta-pill">{html.escape(sc.get('archetype','?'))}</span>
    <span class="meta-pill">{html.escape(sc.get('difficulty','?'))}</span>
    <span class="meta-pill">flux: {html.escape(elapsed_str)}</span>
    <span class="meta-pill">{html.escape(str(flux_wc))}w prompt</span>
    {error_pill}
  </div>
</div>"""
            )

    title_suffix = " (interrupted)" if interrupted else ""
    title_mode = " — full from-scratch" if is_full_run else " — A/B vs NB baseline"

    failure_summary = ""
    if failure_stages:
        failure_summary = (
            "Failures by stage: "
            + " · ".join(
                f"<strong>{html.escape(k)}</strong>: {v}"
                for k, v in sorted(failure_stages.items())
            )
        )

    grid_min = "320px" if is_full_run else "440px"

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FLUX-tuned batch{html.escape(title_mode)} — {html.escape(timestamp)}</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
       margin:0;padding:0;background:#F4F6F8;color:#1F2937}}
  header{{background:#9A3412;color:#fff;padding:24px 32px}}
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
  .legend .flux-callout{{color:#9A3412;font-weight:600}}
  .failure-summary{{padding:10px 32px;background:#FFF7ED;border-bottom:1px solid #FED7AA;
                  font-size:12px;color:#7C2D12}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax({grid_min},1fr));
        gap:20px;padding:24px 32px}}
  .card{{background:#fff;border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;
        transition:box-shadow .15s ease}}
  .card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.08)}}
  .card-header{{padding:10px 14px;border-bottom:1px solid #E5E7EB;
               display:flex;justify-content:space-between;align-items:center}}
  .card-id{{font-family:ui-monospace,monospace;font-size:11px;color:#6B7280}}
  .card-img-link{{display:block;text-decoration:none;color:inherit}}
  .card-imgs{{display:grid;grid-template-columns:1fr 1fr;gap:0}}
  .card-imgs.card-imgs-single{{grid-template-columns:1fr}}
  .card-img-half,.card-img-full{{position:relative;background:#F3F4F6}}
  .card-img-half.card-img-new,.card-img-full.card-img-new{{box-shadow:inset 0 0 0 2px #EA580C}}
  .card-img-half img,.card-img-full img{{width:100%;display:block;aspect-ratio:9/16;object-fit:cover}}
  .card-img-tag{{position:absolute;top:6px;left:6px;background:rgba(0,0,0,.6);
                color:#fff;font-size:9px;font-weight:600;padding:2px 6px;border-radius:3px;
                z-index:2;letter-spacing:.5px}}
  .card-img-tag.tag-flux{{background:rgba(154,52,18,.95)}}
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
  <h1>FLUX-tuned Step 2 experiment{html.escape(title_mode)}{html.escape(title_suffix)}</h1>
  <div class="meta">
    {html.escape(timestamp)} · model: {html.escape(model_label)}<br>
    source: {html.escape(reuse_root)}
  </div>
</header>
<div class="summary-bar">
  <div class="stat"><span class="stat-label">Total:</span> <span class="stat-value">{n}</span></div>
  <div class="stat"><span class="stat-label">Success:</span> <span class="stat-value" style="color:#065F46">{succeeded}</span></div>
  <div class="stat"><span class="stat-label">Failed:</span> <span class="stat-value" style="color:#991B1B">{failed}</span></div>
  <div class="stat"><span class="stat-label">Cost:</span> <span class="stat-value">${actual_cost:.2f}</span></div>
  <div class="stat"><span class="stat-label">Elapsed:</span> <span class="stat-value">{elapsed:.0f}s ({elapsed/60:.1f} min)</span></div>
</div>
{f'<div class="failure-summary">{failure_summary}</div>' if failure_summary else ''}
<div class="legend">
  Each card: {'<strong>NB baseline (left)</strong> · <span class="flux-callout">FLUX-tuned (right, orange)</span>' if not is_full_run else '<span class="flux-callout">FLUX-tuned (orange)</span>'}. Click a card for the full chain.html with prompt diff + click-to-zoom images.
</div>
<div class="grid">
{''.join(cards)}
</div>
</body>
</html>
"""
    (batch_dir / "overview.html").write_text(html_doc, encoding="utf-8")