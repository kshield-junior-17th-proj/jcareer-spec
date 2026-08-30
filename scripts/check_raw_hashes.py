#!/usr/bin/env python3
"""context/raw 무결성 — V2.1 (검수 V2-P0-02 수정).

V2 결함:
  - 반입 금지 파일이 files 에 섞여 locked 가 불가능
  - draft 이면 전부 없어도 exit 0 이고, CI 가 draft 병합을 허용
  - 알 수 없는 manifest_state 가 무시됨

V2.1:
  --require-locked   locked 가 아니면 실패 (main 대상 PR 에서 사용)
  알 수 없는 state    즉시 실패
  tracked 만 존재·해시를 요구. external/excluded 는 메타만 검증
"""
import argparse, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lib_manifest as L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=None)
    ap.add_argument("--require-locked", action="store_true")
    a = ap.parse_args()

    root = pathlib.Path(a.root).resolve() if a.root else L.repo_root()
    man = L.load(root)
    meta = man.get("meta") or {}
    state = meta.get("manifest_state")

    if state not in L.VALID_STATES:
        print(f"::error::manifest_state 값이 유효하지 않습니다: {state!r} "
              f"— {L.VALID_STATES} 중 하나여야 합니다")
        return 1
    if a.require_locked and state != "locked":
        print(f"::error::main 대상 PR 은 manifest_state=locked 를 요구합니다 (현재 {state})")
        return 1

    if "files" in man:
        print("::error::구 스키마 `files:` 가 남아 있습니다 — "
              "tracked_files / external_assets / excluded_files 로 분리하세요 (V2.1)")
        return 1
    if "tracked_files" not in man:
        print("::error::tracked_files 키가 없습니다. 빈 목록이라도 명시해야 합니다 "
              "(오타로 0건이 되어 조용히 통과하는 것을 막습니다)")
        return 1

    trk, ext, exc = L.tracked(man), L.external(man), L.excluded(man)
    act = set(L.actual(root))

    hard, soft, ok = [], [], 0
    seen, declared_paths = set(), set()
    for f in trk:
        rel = f["path"]
        if rel in seen:
            hard.append(f"중복 선언 경로 {rel}")
        seen.add(rel); declared_paths.add(rel)
        want = (f.get("sha256") or "").strip()
        p = root / "context" / rel
        if not p.is_file():
            (hard if state == "locked" else soft).append(f"선언됐으나 파일 없음 {rel}")
            continue
        if not want:
            (hard if state == "locked" else soft).append(f"sha256 미기입 {rel}")
            continue
        got = L.sha256(p)
        if got == want:
            ok += 1
        else:
            hard.append(f"해시 불일치 {rel}  기대 {want[:12]}…  실제 {got[:12]}…")

    for rel in sorted(act - declared_paths):
        hard.append(f"미선언 파일이 raw 에 있음 {rel}")

    # external / excluded 는 존재를 요구하지 않는다. 메타 필수 필드만 본다.
    for f in ext:
        for k in ("location", "access_grade"):
            if not f.get(k):
                hard.append(f"external_assets 필수 필드 누락 {f['path']}.{k}")
    for f in exc:
        if not f.get("reason"):
            hard.append(f"excluded_files 사유 누락 {f['path']}")
        p = root / "context" / f["path"]
        if p.is_file():
            hard.append(f"반입 금지 파일이 저장소에 있습니다 {f['path']}")

    # 개수 계약
    cnt = meta.get("counts") or {}
    if cnt:
        exp = cnt.get("tracked_expected_total")
        if exp is not None and exp != len(trk):
            hard.append(f"tracked_expected_total={exp} 이나 실제 선언 {len(trk)}건")
        for key, coll in (("external_assets", ext), ("excluded_files", exc)):
            e = cnt.get(key)
            if e is not None and e != len(coll):
                hard.append(f"counts.{key}={e} 이나 실제 {len(coll)}건")

    print(f"manifest_state={state}  tracked {len(trk)} · external {len(ext)} · "
          f"excluded {len(exc)} · 실제 raw {len(act)} · 검증통과 {ok}")
    for m in soft:
        print(f"::warning::{m}")
    for m in hard:
        print(f"::error::{m}")
    if hard:
        print("::error::raw 무결성 검사 실패")
        return 1
    print("locked 무결성 통과" if state == "locked"
          else "draft 상태 — 반입 완료 후 locked 로 전환하라. main PR 은 locked 를 요구한다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
