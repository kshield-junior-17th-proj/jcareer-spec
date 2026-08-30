#!/bin/zsh
set -euo pipefail

root='/Library/Application Support/JCareerLab'
install -d -m 0755 "$root"
source_dir=${0:A:h}
for script_name in configure-jcareer-session.sh remove-jcareer-session.sh validate-consultant.sh; do
  test -r "$source_dir/$script_name"
  /usr/bin/install -o root -g wheel -m 0755 "$source_dir/$script_name" "$root/$script_name"
done
test -d /Applications/Safari.app
/usr/bin/codesign --verify --deep --strict /Applications/Safari.app
cat >"$root/README.txt" <<'TEXT'
J-Career synthetic consulting workplace component
- No AWS, SaaS, OpenDART, Bedrock, preview, or user credentials are stored here.
- An approved MDM or physical-device workflow supplies identity, a hash-bound HTTPS preview URL, and an expiry.
- This component is not a signed package, macOS image, deployed device, or posture result.
TEXT
cat >"$root/image-manifest.json" <<'JSON'
{
  "schema_version": "jcareer-macos-image-v1",
  "data_classification": "SYNTHETIC_DEMONSTRATION_ONLY",
  "image_build_state": "COMPONENT_INSTALLED_NOT_DEPLOYED",
  "credentials_baked": false,
  "preview_url_baked": false,
  "browser_contract": "APPLE_SAFARI_REQUIRED_AT_PREPARATION",
  "session_cleanup_installed": true
}
JSON
chmod 0644 "$root/README.txt" "$root/image-manifest.json"

shared_desktop='/Users/Shared'
cat >"$shared_desktop/Slack - approved account required.webloc" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>URL</key><string>https://app.slack.com/client</string></dict></plist>
PLIST
cat >"$shared_desktop/OpenDART public site.webloc" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>URL</key><string>https://opendart.fss.or.kr/</string></dict></plist>
PLIST
chmod 0644 "$shared_desktop/Slack - approved account required.webloc" "$shared_desktop/OpenDART public site.webloc"
print 'J-Career macOS component prepared; no image or deployment is claimed.'
