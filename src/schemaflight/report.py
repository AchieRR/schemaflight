from __future__ import annotations

from html import escape
from typing import Protocol


class ReportAsset(Protocol):
    name: str
    owners: tuple[str, ...]
    depth: int


def render_evidence_report(
    *,
    source_name: str,
    source_field: str,
    target_field: str,
    impacted: list[ReportAsset],
    owner_routes: dict[str, list[str]],
    lineage_hops: int,
    query_patch_count: int,
    direct_rename_allowed: bool,
) -> str:
    source = f"{source_name}.{source_field}"
    nodes = [(source_name, "SOURCE")] + [
        (asset.name, f"HOP {asset.depth:02d}") for asset in impacted
    ]
    lineage_markup = "".join(
        f'<li><span class="node-index">{escape(label)}</span><strong>{escape(name)}</strong></li>'
        for name, label in nodes
    )
    owner_markup = "".join(
        "<tr>"
        f'<th scope="row">@{escape(owner)}</th>'
        f"<td>{', '.join(f'<code>{escape(name)}</code>' for name in names)}</td>"
        "</tr>"
        for owner, names in owner_routes.items()
    ) or (
        '<tr><th scope="row">none</th><td>No downstream acknowledgement required.</td></tr>'
        if direct_rename_allowed
        else '<tr><th scope="row">unowned</th><td>Assign before contract.</td></tr>'
    )
    hop_label = f"{lineage_hops:02d}"
    verdict = "DIRECT RENAME ALLOWED" if direct_rename_allowed else "DIRECT RENAME REJECTED"
    plan_markup = (
        '<div class="phase"><div><b>Direct</b><p>Rename, validate, and retain a rollback path.</p></div></div>'
        if direct_rename_allowed
        else (
            '<div class="phase"><div><b>Expand</b><p>Expose both field names without breaking readers.</p></div></div>'
            '<div class="phase"><div><b>Migrate</b><p>Backfill and apply evidence-linked query patches.</p></div></div>'
            '<div class="phase"><div><b>Contract</b><p>Remove the legacy field only after checks and acknowledgement.</p></div></div>'
        )
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SchemaFlight — migration evidence</title>
  <style>
    :root {{
      --ink: #0b0f10; --panel: #121819; --line: #344143; --paper: #e8ece7;
      --muted: #9aa7a3; --hazard: #f4c95d; --signal: #2de1c2; --danger: #ff6b5f;
      --space: clamp(1rem, 2vw, 1.6rem); --ease: cubic-bezier(.2,.8,.2,1);
    }}
    * {{ box-sizing: border-box; }}
    html {{ color-scheme: dark; background: var(--ink); }}
    body {{ margin: 0; color: var(--paper); font: 16px/1.55 "Segoe UI", Arial, sans-serif;
      background: repeating-linear-gradient(135deg, rgba(255,255,255,.018) 0 1px, transparent 1px 12px), var(--ink); }}
    code, .eyebrow, .metric span, .node-index {{ font-family: Consolas, "Courier New", monospace; }}
    .skip-link {{ position: fixed; left: 1rem; top: -5rem; z-index: 10; padding: .7rem 1rem;
      color: var(--ink); background: var(--hazard); font-weight: 800; }}
    .skip-link:focus {{ top: 1rem; }}
    header, main, footer {{ width: min(1180px, calc(100% - 2rem)); margin-inline: auto; }}
    header {{ padding: clamp(3rem, 8vw, 7rem) 0 2rem; border-bottom: 1px solid var(--line); position: relative; }}
    header::after {{ content: ""; position: absolute; right: 0; top: 1.5rem; width: min(38vw, 360px); height: 10px;
      background: repeating-linear-gradient(135deg, var(--hazard) 0 12px, var(--ink) 12px 24px); }}
    .eyebrow {{ margin: 0 0 1rem; color: var(--signal); letter-spacing: .13em; font-size: .78rem; font-weight: 800; }}
    h1 {{ max-width: 900px; margin: 0; font-family: "Arial Narrow", "Segoe UI", sans-serif; font-size: clamp(2.6rem, 7vw, 6.8rem);
      line-height: .93; letter-spacing: -.055em; text-transform: uppercase; }}
    h1 em {{ color: var(--hazard); font-style: normal; }}
    .verdict {{ display: inline-flex; gap: .7rem; align-items: center; margin-top: 1.5rem; padding: .55rem .8rem;
      border: 1px solid var(--danger); color: var(--danger); font: 800 .78rem/1 Consolas, monospace; letter-spacing: .08em; }}
    .verdict::before {{ content: ""; width: 8px; height: 8px; background: currentColor; border-radius: 50%; box-shadow: 0 0 18px currentColor; }}
    main {{ padding: 2rem 0 4rem; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--line); background: var(--panel); }}
    .metric {{ min-height: 132px; padding: var(--space); border-right: 1px solid var(--line); display: grid; align-content: space-between; transition: background .22s var(--ease), transform .22s var(--ease); }}
    .metric:last-child {{ border-right: 0; }}
    .metric:hover {{ background: #182122; transform: translateY(-2px); }}
    .metric b {{ font: 800 clamp(2rem, 5vw, 4.2rem)/1 "Arial Narrow", sans-serif; color: var(--hazard); }}
    .metric span {{ color: var(--muted); font-size: .72rem; letter-spacing: .09em; text-transform: uppercase; }}
    .layout {{ display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr); gap: 1px; margin-top: 1px; background: var(--line); border: 1px solid var(--line); }}
    section {{ background: var(--panel); padding: clamp(1.3rem, 3vw, 2.4rem); }}
    section h2 {{ margin: 0 0 1.3rem; font: 800 .78rem/1 Consolas, monospace; letter-spacing: .11em; color: var(--signal); }}
    .lineage {{ list-style: none; margin: 0; padding: 0; }}
    .lineage li {{ position: relative; min-height: 86px; display: grid; grid-template-columns: 84px 1fr; align-items: center; border-top: 1px solid var(--line); }}
    .lineage li::before {{ content: ""; position: absolute; left: 56px; top: -1px; bottom: -1px; width: 2px; background: var(--hazard); }}
    .lineage li::after {{ content: ""; position: absolute; left: 50px; width: 14px; height: 14px; border: 2px solid var(--hazard); background: var(--panel); transform: rotate(45deg); }}
    .lineage li:first-child {{ border-top: 0; }} .node-index {{ color: var(--muted); font-size: .68rem; }}
    .lineage strong {{ padding-left: 1rem; font-size: clamp(1rem, 2.2vw, 1.45rem); overflow-wrap: anywhere; }}
    .phases {{ counter-reset: phase; display: grid; gap: .7rem; }}
    .phase {{ counter-increment: phase; display: grid; grid-template-columns: 42px 1fr; gap: .8rem; padding: 1rem; border: 1px solid var(--line); transition: border-color .22s var(--ease), transform .22s var(--ease); }}
    .phase:hover {{ border-color: var(--signal); transform: translateX(3px); }}
    .phase::before {{ content: "0" counter(phase); color: var(--hazard); font: 800 1rem Consolas, monospace; }}
    .phase b {{ display: block; text-transform: uppercase; }} .phase p {{ color: var(--muted); margin: .2rem 0 0; font-size: .9rem; }}
    .owners {{ grid-column: 1 / -1; }}
    table {{ width: 100%; border-collapse: collapse; }} th, td {{ padding: .9rem; border-top: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ width: 190px; color: var(--hazard); font-family: Consolas, monospace; }} td code {{ color: var(--paper); }}
    footer {{ padding: 1.2rem 0 2.5rem; color: var(--muted); font: .72rem Consolas, monospace; letter-spacing: .08em; text-transform: uppercase; }}
    @media (max-width: 820px) {{ .metrics {{ grid-template-columns: repeat(2, 1fr); }} .metric:nth-child(2) {{ border-right: 0; }} .metric {{ border-bottom: 1px solid var(--line); }} .layout {{ grid-template-columns: 1fr; }} }}
    @media (max-width: 520px) {{ .metrics {{ grid-template-columns: 1fr; }} .metric {{ border-right: 0; }} .lineage li {{ grid-template-columns: 72px 1fr; }} .lineage li::before {{ left: 48px; }} .lineage li::after {{ left: 42px; }} th {{ width: auto; }} th, td {{ display: block; }} }}
    @media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; scroll-behavior: auto !important; }} }}
  </style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to migration evidence</a>
  <header>
    <p class="eyebrow">SCHEMAFLIGHT / MIGRATION CONTROL</p>
    <h1>{escape(source)} <em>→</em> {escape(target_field)}</h1>
    <div class="verdict">{verdict}</div>
  </header>
  <main id="main">
    <div class="metrics" aria-label="Migration evidence summary">
      <div class="metric"><b>{hop_label}</b><span>lineage hops</span></div>
      <div class="metric"><b>{len(impacted):02d}</b><span>assets impacted</span></div>
      <div class="metric"><b>{len(owner_routes):02d}</b><span>owner routes</span></div>
      <div class="metric"><b>{query_patch_count:02d}</b><span>queries patched</span></div>
    </div>
    <div class="layout">
      <section aria-labelledby="lineage-heading">
        <h2 id="lineage-heading">DATAHUB EVIDENCE // {hop_label} HOPS</h2>
        <ol class="lineage">{lineage_markup}</ol>
      </section>
      <section aria-labelledby="plan-heading">
        <h2 id="plan-heading">CONTROLLED FLIGHT PLAN</h2>
        <div class="phases">{plan_markup}</div>
      </section>
      <section class="owners" aria-labelledby="owners-heading">
        <h2 id="owners-heading">OWNER ROUTING // ACKNOWLEDGEMENT REQUIRED</h2>
        <table><tbody>{owner_markup}</tbody></table>
      </section>
    </div>
  </main>
  <footer>Deterministic report · no remote assets · generated from DataHub lineage and usage context</footer>
</body>
</html>
"""
