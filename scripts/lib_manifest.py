"""MANIFEST 파서 — V2.1.

V2 결함(검수 V2-P0-02): 반입 금지 파일(_restricted · _excluded)이 files 에 섞여 있어
                        locked 로 잠글 수 없었다. expected_count 27 vs 슬롯 32 불일치.

V2.1 구조:
  tracked_files   저장소에 실제 존재하며 SHA 를 잠근다
  external_assets 저장소 밖 위치·SHA·접근등급만 기록. 존재를 요구하지 않는다
  excluded_files  반입 금지 사유만 기록. 존재를 요구하지 않는다
"""
import hashlib, pathlib, sys

try:
    import yaml
except ImportError:
    print("::error::pyyaml 필요: pip install pyyaml"); sys.exit(2)

VALID_STATES = ("draft", "locked")


def repo_root(start=None):
    p = pathlib.Path(start or __file__).resolve()
    for c in [p] + list(p.parents):
        if (c / "context" / "MANIFEST.yaml").is_file():
            return c
    return pathlib.Path(__file__).resolve().parent.parent


def load(root):
    f = root / "context/MANIFEST.yaml"
    if not f.is_file():
        return {}
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {}


def sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def tracked(man):
    return [f for f in (man.get("tracked_files") or []) if f.get("path")]


def external(man):
    return [f for f in (man.get("external_assets") or []) if f.get("path")]


def excluded(man):
    return [f for f in (man.get("excluded_files") or []) if f.get("path")]


def declared_paths(man):
    """인용 앵커 대조용 — tracked 만. 반입 금지 자료는 인용 대상이 아니다."""
    return [f["path"] for f in tracked(man)]


def actual(root):
    base = root / "context/raw"
    out = []
    if not base.exists():
        return out
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.name in ("README.md", ".gitkeep"):
            continue
        rel = p.relative_to(root / "context").as_posix()
        if rel.startswith(("raw/_restricted/", "raw/_excluded/")):
            continue          # 반입 금지 영역은 tracked 대조 대상이 아니다
        out.append(rel)
    return out
