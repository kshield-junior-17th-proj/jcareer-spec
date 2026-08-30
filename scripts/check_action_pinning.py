#!/usr/bin/env python3
"""모든 외부 GitHub Action 이 40자리 commit SHA 로 고정됐는지 검사 — 실패시킨다.

V2 결함(V2-P0-08): list_unpinned_actions.sh 는 경고 후 항상 exit 0 이었고,
                   워크플로에서 다시 `|| true` 로 감쌌다. 정규식은 @main·@master 를 놓쳤다.
                   그리고 terraform-plan.yml 에 `curl .../master/... | bash` 가 남아 있었다.
"""
import pathlib, re, sys

USES = re.compile(r'^\s*(?:-\s*)?uses:\s*([^\s#]+)')
SHA40 = re.compile(r'^[0-9a-f]{40}$')
REMOTE_PIPE = re.compile(r'(curl|wget)[^\n|]*\|\s*(sudo\s+)?(bash|sh)')


def main():
    root = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 \
        else pathlib.Path(__file__).resolve().parent.parent
    wf = root / ".github/workflows"
    bad, pipes = [], []
    for f in sorted(wf.glob("*.yml")) + sorted(wf.glob("*.yaml")):
        text = f.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            m = USES.match(line)
            if m:
                ref = m.group(1).strip().strip('"').strip("'")
                if ref.startswith("./") or ref.startswith(".github/"):
                    continue                       # 로컬 action 은 제외
                if "@" not in ref:
                    bad.append((f.name, i, ref, "버전 참조 없음")); continue
                _, _, ver = ref.partition("@")
                if not SHA40.match(ver):
                    bad.append((f.name, i, ref, f"SHA 아님 ({ver})"))
        for i, line in enumerate(text.splitlines(), 1):
            if REMOTE_PIPE.search(line):
                pipes.append((f.name, i, line.strip()[:100]))

    for n, i, ref, why in bad:
        print(f"::error file=.github/workflows/{n},line={i}::Action 미고정 {ref} — {why}")
    for n, i, l in pipes:
        print(f"::error file=.github/workflows/{n},line={i}::원격 스크립트 파이프 실행 금지 — {l}")
    if bad or pipes:
        print(f"::error::미고정 Action {len(bad)}건 · 원격 파이프 {len(pipes)}건")
        return 1
    print("모든 Action 이 40자리 SHA 로 고정됨 · 원격 파이프 실행 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
