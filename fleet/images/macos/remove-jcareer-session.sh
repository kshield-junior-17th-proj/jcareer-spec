#!/bin/zsh
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  print -u2 'usage: remove-jcareer-session.sh <SESSION-ref> [--force]'
  exit 2
fi
session_ref=$1
force=${2:-}
if ! printf '%s\n' "$session_ref" | /usr/bin/grep -Eq '^SESSION-[A-Z0-9_-]{8,64}$'; then
  print -u2 'session reference is invalid'
  exit 2
fi
if [[ -n "$force" && "$force" != '--force' ]]; then
  print -u2 'only --force is accepted as an optional argument'
  exit 2
fi

root='/Library/Application Support/JCareerLab'
session_file="$root/session.json"
shortcut='/Users/Shared/J-Career approved preview.webloc'
launchd_plist='/Library/LaunchDaemons/com.jcareer.consultant-session.plist'
if [[ ! -r "$session_file" ]]; then
  /usr/bin/osascript -e 'tell application "Safari" to quit' >/dev/null 2>&1 || true
  /usr/bin/osascript -e 'tell application "Slack" to quit' >/dev/null 2>&1 || true
  /usr/bin/pkill -x Safari >/dev/null 2>&1 || true
  /usr/bin/pkill -x Slack >/dev/null 2>&1 || true
  /bin/rm -f "$shortcut"
  /bin/launchctl bootout system/com.jcareer.consultant-session >/dev/null 2>&1 || true
  /bin/rm -f "$launchd_plist"
  print 'JCAREER_MACOS_SESSION_ARTIFACTS_REMOVED=PASS'
  print 'JCAREER_MACOS_COOKIE_CLEANUP=HUMAN_MDM_REQUIRED'
  exit 0
fi

observed_ref=$(/usr/bin/plutil -extract session_ref raw -o - "$session_file" 2>/dev/null || true)
expires_at=$(/usr/bin/plutil -extract expires_at raw -o - "$session_file" 2>/dev/null || true)
if [[ "$observed_ref" != "$session_ref" ]]; then
  print -u2 'requested cleanup does not match the configured session'
  exit 2
fi
expires_epoch=$(/bin/date -j -u -f '%Y-%m-%dT%H:%M:%SZ' "$expires_at" '+%s' 2>/dev/null || true)
now_epoch=$(/bin/date -u '+%s')
if [[ "$force" != '--force' && -n "$expires_epoch" ]]; then
  if (( now_epoch < expires_epoch )); then
    exit 0
  fi
fi

/usr/bin/osascript -e 'tell application "Safari" to quit' >/dev/null 2>&1 || true
/usr/bin/osascript -e 'tell application "Slack" to quit' >/dev/null 2>&1 || true
/usr/bin/pkill -x Safari >/dev/null 2>&1 || true
/usr/bin/pkill -x Slack >/dev/null 2>&1 || true
/bin/rm -f "$shortcut" "$session_file"
/bin/launchctl bootout system/com.jcareer.consultant-session >/dev/null 2>&1 || true
/bin/rm -f "$launchd_plist"
print 'JCAREER_MACOS_SESSION_ARTIFACTS_REMOVED=PASS'
print 'JCAREER_MACOS_COOKIE_CLEANUP=HUMAN_MDM_REQUIRED'
