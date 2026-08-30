#!/usr/bin/env bash
# 워크플로의 태그 참조를 실제 commit SHA 로 교체한다.
# 사람이 실행하고 diff 를 검토한 뒤 커밋한다. gh CLI 인증이 필요하다.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v gh >/dev/null || { echo "gh CLI 필요"; exit 1; }
CHANGED=0
for f in .github/workflows/*.yml; do
  while IFS= read -r ref; do
    repo="${ref%@*}"; tag="${ref#*@}"
    case "$repo" in ./*|.github/*) continue;; esac
    [[ "$tag" =~ ^[0-9a-f]{40}$ ]] && continue
    sha=$(gh api "repos/$repo/commits/$tag" --jq .sha 2>/dev/null || true)
    if [ -n "$sha" ]; then
      echo "  $repo  $tag -> $sha"
      sed -i "s|uses: $repo@$tag|uses: $repo@$sha  # $tag|g" "$f"
      CHANGED=1
    else
      echo "  !! $repo@$tag 해석 실패 — 수동 확인 필요"
    fi
  done < <(grep -oE 'uses:\s*[^ #]+' "$f" | sed 's/uses:\s*//')
done
[ "$CHANGED" = 1 ] && echo "교체 완료. git diff 로 검토한 뒤 커밋하세요." || echo "변경 없음."
python3 scripts/check_action_pinning.py
