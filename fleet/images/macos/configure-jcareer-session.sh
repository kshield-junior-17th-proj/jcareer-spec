#!/bin/zsh
set -euo pipefail

if [[ $# -ne 5 ]]; then
  print -u2 'usage: configure-jcareer-session.sh <credential-free-https-url> <url-sha256> <SESSION-ref> <MAC-01..03> <expires-at-UTC>'
  exit 2
fi

preview_url=$1
approved_url_sha256=$2
session_ref=$3
endpoint_ref=$4
expires_at=$5
if ! printf '%s\n' "$preview_url" | /usr/bin/grep -Eq '^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/%+-]*)?$'; then
  print -u2 'preview URL must be credential-free HTTPS without user info, query, or fragment'
  exit 2
fi
if ! printf '%s\n' "$approved_url_sha256" | /usr/bin/grep -Eq '^[a-f0-9]{64}$'; then
  print -u2 'approved preview URL SHA-256 is invalid'
  exit 2
fi
observed_url_sha256=$(printf '%s' "$preview_url" | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}')
if [[ "$observed_url_sha256" != "$approved_url_sha256" ]]; then
  print -u2 'preview URL does not match the approved SHA-256'
  exit 2
fi
if ! printf '%s\n' "$session_ref" | /usr/bin/grep -Eq '^SESSION-[A-Z0-9_-]{8,64}$'; then
  print -u2 'session reference is invalid'
  exit 2
fi
if ! printf '%s\n' "$endpoint_ref" | /usr/bin/grep -Eq '^MAC-0[1-3]$'; then
  print -u2 'endpoint reference is invalid'
  exit 2
fi
if ! printf '%s\n' "$expires_at" | /usr/bin/grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'; then
  print -u2 'expiry must be an exact UTC timestamp'
  exit 2
fi
expires_epoch=$(/bin/date -j -u -f '%Y-%m-%dT%H:%M:%SZ' "$expires_at" '+%s' 2>/dev/null || true)
now_epoch=$(/bin/date -u '+%s')
if [[ -z "$expires_epoch" ]] || (( expires_epoch < now_epoch + 900 || expires_epoch > now_epoch + 28800 )); then
  print -u2 'expiry must be between 15 minutes and 8 hours from now'
  exit 2
fi

root='/Library/Application Support/JCareerLab'
test -r "$root/image-manifest.json"
test -x "$root/remove-jcareer-session.sh"
test -d /Applications/Safari.app
if [[ -e "$root/session.json" ]]; then
  print -u2 'an existing consultant session must be removed first'
  exit 2
fi
shortcut='/Users/Shared/J-Career approved preview.webloc'
cat >"$shortcut" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>URL</key><string>$preview_url</string></dict></plist>
PLIST
chmod 0644 "$shortcut"

configured_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
cat >"$root/session.json" <<JSON
{
  "schema_version": "jcareer-consultant-session-v2",
  "session_ref": "$session_ref",
  "endpoint_ref": "$endpoint_ref",
  "configured_at": "$configured_at",
  "expires_at": "$expires_at",
  "preview_url_sha256": "$observed_url_sha256",
  "credentials_recorded": false
}
JSON
chmod 0600 "$root/session.json"

launchd_plist='/Library/LaunchDaemons/com.jcareer.consultant-session.plist'
cat >"$launchd_plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.jcareer.consultant-session</string>
<key>ProgramArguments</key><array>
<string>$root/remove-jcareer-session.sh</string><string>$session_ref</string>
</array>
<key>RunAtLoad</key><true/>
<key>StartInterval</key><integer>300</integer>
</dict></plist>
PLIST
chmod 0644 "$launchd_plist"
/bin/launchctl bootout system/com.jcareer.consultant-session >/dev/null 2>&1 || true
/bin/launchctl bootstrap system "$launchd_plist"
print 'J-Career macOS session configured with URL-hash binding and expiry cleanup; no credential was stored.'
