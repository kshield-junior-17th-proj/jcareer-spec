#!/bin/zsh
set -euo pipefail

root='/Library/Application Support/JCareerLab'
test -r "$root/image-manifest.json"
firewall_state=$(/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>/dev/null || true)
filevault_state=$(fdesetup status 2>/dev/null || true)
xprotect_version=$(defaults read /Library/Apple/System/Library/CoreServices/XProtect.bundle/Contents/Info CFBundleShortVersionString 2>/dev/null || true)
safari_present=false
cleanup_present=false
[[ -d /Applications/Safari.app ]] && safari_present=true
[[ -x "$root/remove-jcareer-session.sh" ]] && cleanup_present=true
firewall_enabled=false
filevault_enabled=false
printf '%s' "$firewall_state" | /usr/bin/grep -Eqi 'enabled|state = 1' && firewall_enabled=true
printf '%s' "$filevault_state" | /usr/bin/grep -Eqi 'FileVault is On' && filevault_enabled=true

printf '{"schema_version":"jcareer-macos-preflight-v2","firewall_enabled_observed":%s,"filevault_enabled_observed":%s,"xprotect_version_observed":%s,"safari_present_observed":%s,"cleanup_script_present_observed":%s,"posture_decision":"HUMAN"}\n' \
  "$firewall_enabled" \
  "$filevault_enabled" \
  "$([[ -n "$xprotect_version" ]] && printf 'true' || printf 'false')" \
  "$safari_present" \
  "$cleanup_present"
