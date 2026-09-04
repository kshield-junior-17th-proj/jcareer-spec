from __future__ import annotations

import base64
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
OUTPUT = ASSETS / "JCAREER_ARCHITECTURE_FLOW_GALLERY.html"

FLOWS = (
    {
        "stem": "JCAREER_CANDIDATE_RECOMMENDATION_FLOW",
        "eyebrow": "FLOW 01 · CANDIDATE",
        "title": "Recommendations with a bounded explanation lane",
        "summary": (
            "A candidate asks for ranked jobs. The Agent Lambda owns the deterministic "
            "ranking; Bedrock can add qualitative text but cannot set the score or order."
        ),
    },
    {
        "stem": "JCAREER_RECRUITER_TALENT_SEARCH_FLOW",
        "eyebrow": "FLOW 02 · RECRUITER",
        "title": "Company-scoped talent search with human review",
        "summary": (
            "A recruiter searches candidates for one job. The same verified serverless "
            "backbone returns review support without auto-selection, fit probability, or a hiring decision."
        ),
    },
)


def data_uri(path: Path, mime: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def flow_section(flow: dict[str, str]) -> str:
    stem = flow["stem"]
    svg = ASSETS / f"{stem}.svg"
    gif = ASSETS / f"{stem}.gif"
    mp4 = ASSETS / f"{stem}.mp4"
    return f"""
    <article class="flow">
      <div class="flow-copy">
        <p class="eyebrow">{flow['eyebrow']}</p>
        <h2>{flow['title']}</h2>
        <p>{flow['summary']}</p>
        <div class="facts" aria-label="Asset metadata">
          <span>1800 × 980</span><span>3 s loop</span><span>H.264</span><span>SVG SHA {digest(svg)}</span>
        </div>
      </div>
      <figure class="canvas">
        <img src="{data_uri(svg, 'image/svg+xml')}" alt="{flow['title']} animated AWS architecture diagram">
      </figure>
      <details>
        <summary>Format previews</summary>
        <div class="formats">
          <figure><figcaption>H.264 MP4</figcaption><video src="{data_uri(mp4, 'video/mp4')}" controls muted loop playsinline preload="metadata"></video></figure>
          <figure><figcaption>Animated GIF</figcaption><img src="{data_uri(gif, 'image/gif')}" alt="Animated GIF preview of {flow['title']}"></figure>
        </div>
      </details>
    </article>
    """


def build() -> str:
    sections = "\n".join(flow_section(flow) for flow in FLOWS)
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>JCareer · Candidate and Recruiter Architecture Flows</title>
  <style>
    :root {{ color-scheme: light; --ink:#16202e; --sub:#5a6b7b; --line:#dce4ec; --paper:#fbfcfe; --live:#087f5b; --proposed:#b45309; --unknown:#64748b; --not:#be123c; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#eef2f5; color:var(--ink); font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    main {{ width:min(1500px,calc(100% - 40px)); margin:0 auto; padding:72px 0 96px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1.2fr) minmax(320px,.8fr); gap:64px; align-items:end; margin-bottom:56px; }}
    .kicker,.eyebrow {{ margin:0 0 12px; color:#0b7e7f; font-size:12px; font-weight:800; letter-spacing:.14em; text-transform:uppercase; }}
    h1 {{ max-width:850px; margin:0; font-size:clamp(42px,6vw,82px); line-height:.98; letter-spacing:-.055em; }}
    .intro {{ margin:0; color:var(--sub); font-size:18px; line-height:1.65; }}
    .status {{ grid-column:1/-1; display:grid; grid-template-columns:repeat(4,1fr); border:1px solid var(--line); background:white; }}
    .status div {{ min-height:110px; padding:22px 24px; border-right:1px solid var(--line); }}
    .status div:last-child {{ border-right:0; }}
    .status strong {{ display:block; margin-bottom:8px; font-size:12px; letter-spacing:.08em; }}
    .status span {{ color:var(--sub); font-size:13px; line-height:1.45; }}
    .live strong {{ color:var(--live); }} .proposed strong {{ color:var(--proposed); }} .unknown strong {{ color:var(--unknown); }} .not strong {{ color:var(--not); }}
    .flow {{ margin-top:36px; padding:38px; border:1px solid var(--line); background:var(--paper); box-shadow:0 18px 60px rgba(22,32,46,.08); }}
    .flow-copy {{ display:grid; grid-template-columns:1fr 1fr; column-gap:56px; align-items:end; margin-bottom:28px; }}
    .flow-copy .eyebrow {{ grid-column:1/-1; }}
    h2 {{ margin:0; font-size:clamp(28px,3vw,48px); line-height:1.05; letter-spacing:-.035em; }}
    .flow-copy > p:not(.eyebrow) {{ margin:0; color:var(--sub); font-size:16px; line-height:1.65; }}
    .facts {{ grid-column:1/-1; display:flex; flex-wrap:wrap; gap:8px; margin-top:20px; }}
    .facts span {{ padding:7px 10px; border:1px solid var(--line); border-radius:999px; background:white; color:var(--sub); font:700 11px ui-monospace,SFMono-Regular,Consolas,monospace; }}
    figure {{ margin:0; }}
    .canvas {{ overflow:hidden; border:1px solid var(--line); background:white; }}
    .canvas img,.formats img,.formats video {{ display:block; width:100%; height:auto; }}
    details {{ margin-top:18px; border-top:1px solid var(--line); }}
    summary {{ padding:18px 0 0; cursor:pointer; color:var(--sub); font-size:13px; font-weight:750; }}
    .formats {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-top:18px; }}
    .formats figure {{ border:1px solid var(--line); background:white; }}
    figcaption {{ padding:12px 14px; color:var(--sub); font:700 11px ui-monospace,SFMono-Regular,Consolas,monospace; }}
    footer {{ margin-top:42px; color:var(--sub); font-size:12px; line-height:1.6; }}
    @media (max-width:820px) {{ main {{ width:min(100% - 20px,1500px); padding-top:36px; }} header,.flow-copy,.formats {{ grid-template-columns:1fr; }} header {{ gap:28px; }} .status {{ grid-template-columns:1fr 1fr; }} .status div:nth-child(2) {{ border-right:0; }} .status div:nth-child(-n+2) {{ border-bottom:1px solid var(--line); }} .flow {{ padding:18px; }} .flow-copy > p:not(.eyebrow) {{ margin-top:16px; }} }}
    @media (prefers-reduced-motion:reduce) {{ * {{ scroll-behavior:auto !important; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div><p class="kicker">JCareer · architecture gallery</p><h1>Two journeys. One verified serverless backbone.</h1></div>
      <p class="intro">Candidate recommendation and recruiter talent search are separated by product intent while sharing the repository-supported AWS request plane. Every status boundary remains explicit.</p>
      <section class="status" aria-label="Architecture status legend">
        <div class="live"><strong>IMPLEMENTED</strong><span>Live-verified in the narrow synthetic production-serverless slice on 2026-09-01.</span></div>
        <div class="proposed"><strong>PROPOSED</strong><span>The enterprise 2-AZ ECS and RDS estate is a separate model, not the live path.</span></div>
        <div class="unknown"><strong>UNCONFIRMED</strong><span>Real-customer tenancy, data, fairness, quality, and operating evidence were not observed.</span></div>
        <div class="not"><strong>NOT-ASSET</strong><span>TRACE and JC-RECEIPT are never AWS services, estate assets, or deployment items.</span></div>
      </section>
    </header>
    {sections}
    <footer>Repository evidence cutoff: 2026-09-01. The diagrams do not claim real-customer production, autonomous selection, hiring decisions, or deployment of the enterprise target.</footer>
  </main>
</body>
</html>
"""
    return "\n".join(line.rstrip() for line in html.splitlines()) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(build(), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size} bytes)")
