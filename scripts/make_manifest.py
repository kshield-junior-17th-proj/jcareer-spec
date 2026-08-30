#!/usr/bin/env python3
"""MANIFEST 의 sha256 을 채운다. 선언 파일이 하나라도 없으면 exit 1 (V1 P0-03).

--allow-missing 을 주면 경고만 내고 채운 것만 기록한다 (반입 중간 단계용).
locked 상태의 MANIFEST 는 수정하지 않는다.
"""
import argparse, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lib_manifest as L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-missing", action="store_true")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()

    root = pathlib.Path(a.root).resolve() if a.root else L.repo_root()
    man = L.load(root)
    if (man.get("meta") or {}).get("manifest_state") == "locked":
        print("::error::manifest_state=locked 입니다. 잠긴 MANIFEST 는 수정하지 않습니다.")
        return 1

    mpath = root / "context/MANIFEST.yaml"
    lines = mpath.read_text(encoding="utf-8").splitlines()
    cur, out, filled, missing = None, [], 0, []

    for line in lines:
        pm = re.match(r'^\s*- path:\s*(\S+)\s*$', line)
        if pm:
            cur = pm.group(1)
        sm = re.match(r'^(\s*)sha256:\s*""\s*$', line)
        if sm and cur:
            p = root / "context" / cur
            if p.is_file():
                line = f'{sm.group(1)}sha256: "{L.sha256(p)}"'
                filled += 1
            else:
                missing.append(cur)
        out.append(line)

    for m in missing:
        print(f"::warning::반입되지 않음 {m}")
    if missing and not a.allow_missing:
        print(f"::error::선언 파일 {len(missing)}건이 없습니다. "
              f"반입을 마치거나 --allow-missing 을 명시하세요.")
        return 1

    mpath.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"sha256 {filled}건 기록 · 미반입 {len(missing)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
