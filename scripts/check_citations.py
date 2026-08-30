#!/usr/bin/env python3
"""인용 앵커 검증 — V2.1 (검수 V2-P0-04 수정).

V2 결함: YAML 을 한 줄 정규식으로 읽어 다중행 배열(`anchors:` 아래 리스트),
         `evidence:` 배열, block scalar 를 전부 놓쳤다. 깨진 경로를 0건으로 셌다.

V2.1: yaml.safe_load 후 객체를 재귀 순회한다. YAML 파싱 오류도 실패로 처리한다.

앵커 표기 — 저장소 기준 전체 경로만 허용
    context/raw/<실제파일명>#<절>
    docs/current/<파일>#<절>
    context/proposals/<...>#<절>
'<' '>' 를 포함하면 placeholder 로 보고 무시한다.
"""
import argparse, json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lib_manifest as L

try:
    import yaml
except ImportError:
    print("::error::pyyaml 필요"); sys.exit(2)

PREFIX = ("context/raw/", "docs/current/", "context/proposals/")
ANCHOR_KEYS = {"source", "evidence", "anchors", "sources", "refs"}
MD_CODE = re.compile(r'`([^`\n]+)`')
MD_LINK = re.compile(r'\]\(([^)\s]+)\)')


def is_anchor(s):
    if not isinstance(s, str):
        return False
    s = s.strip()
    return bool(s) and "<" not in s and ">" not in s and "#" in s and s.startswith(PREFIX)


def walk_yaml(node, out, key=None):
    """재귀 순회. ANCHOR_KEYS 아래의 문자열/리스트/중첩을 전부 수집."""
    if isinstance(node, dict):
        for k, v in node.items():
            walk_yaml(v, out, str(k))
    elif isinstance(node, list):
        for v in node:
            walk_yaml(v, out, key)
    elif isinstance(node, str):
        if key in ANCHOR_KEYS:
            # 배열 원소 하나가 여러 앵커를 담을 수도 있다
            for tok in re.split(r'[\s,]+', node.strip()):
                tok = tok.strip().strip('"').strip("'")
                if is_anchor(tok):
                    out.append(tok)
                elif tok.startswith(("raw/", "context/", "docs/")) and "#" in tok \
                        and "<" not in tok:
                    out.append(tok)   # 잘못된 형식도 수집해서 아래에서 실패시킨다


def collect(root, scan_dirs):
    found, parse_errors = [], []
    for d in scan_dirs:
        base = root / d
        if not base.exists():
            continue
        for f in sorted(base.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(root).as_posix()
            suf = f.suffix.lower()
            text = f.read_text(encoding="utf-8", errors="replace")
            if suf in (".yaml", ".yml"):
                try:
                    docs = list(yaml.safe_load_all(text))
                except Exception as e:
                    parse_errors.append({"in": rel, "reason": f"YAML 파싱 실패: {e}"})
                    continue
                acc = []
                for doc in docs:
                    walk_yaml(doc, acc)
                found += [(rel, a) for a in acc]
            elif suf in (".md", ".markdown"):
                for m in list(MD_CODE.finditer(text)) + list(MD_LINK.finditer(text)):
                    tok = m.group(1).strip()
                    if is_anchor(tok):
                        found.append((rel, tok))
    return found, parse_errors


def headings(p):
    if p.suffix.lower() not in (".md", ".markdown"):
        return None
    hs = set()
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r'^#{1,6}\s+(.*?)\s*$', line)
        if not m:
            continue
        t = m.group(1).strip()
        hs.add(t); hs.add(t.lstrip("§").strip())
        n = re.match(r'^§?\s*([0-9]+(?:\.[0-9]+)*)', t)
        if n: hs.add(n.group(1))
        d = re.match(r'^([A-Z]-\d+|[A-Z]\.\d+(?:\.\d+)?|R-\d+|GAP-[A-Z0-9-]+)', t)
        if d: hs.add(d.group(1))
    return hs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--scan", nargs="*",
                    default=["docs/current", "context/findings", "context/proposals"])
    ap.add_argument("--mode", choices=["auto", "strict", "declared"], default="auto")
    a = ap.parse_args()
    root = (pathlib.Path(a.root).resolve() if a.root
            else pathlib.Path(__file__).resolve().parent.parent)

    man = L.load(root)
    state = (man.get("meta") or {}).get("manifest_state", "draft")
    mode = a.mode
    if mode == "auto":
        mode = "strict" if state == "locked" else "declared"
    declared_raw = {"context/" + p for p in L.declared_paths(man)}

    anchors, parse_errors = collect(root, a.scan)
    broken = list(parse_errors)
    for where, anc in anchors:
        if not is_anchor(anc):
            broken.append({"in": where, "anchor": anc,
                           "reason": "앵커 형식 위반 — 저장소 기준 전체 경로여야 한다"})
            continue
        path, _, sec = anc.partition("#")
        target = root / path
        if not target.is_file():
            if mode == "declared" and path in declared_raw:
                continue
            broken.append({"in": where, "anchor": anc,
                           "reason": "파일 없음" if mode == "strict"
                                     else "MANIFEST 에 선언되지 않은 경로"})
            continue
        hs = headings(target)
        if hs is None:
            continue
        key = sec.lstrip("§").strip()
        if key in hs or any(h.startswith(key) for h in hs):
            continue
        broken.append({"in": where, "anchor": anc, "reason": "절 없음"})

    rep = {"mode": mode, "manifest_state": state,
           "checked": len(anchors), "parse_errors": len(parse_errors), "broken": broken}
    if a.out:
        o = pathlib.Path(a.out); o.parent.mkdir(parents=True, exist_ok=True)
        o.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"인용 앵커 {len(anchors)}건 검사 (mode={mode}) · 깨짐 {len(broken)}건")
    for b in broken:
        print(f"::error file={b['in']}::{b.get('anchor','')} — {b['reason']}")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
