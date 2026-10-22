#!/usr/bin/env bash
# Prompt for passwords and write secrets.yml (hashes only, except the hotspot
# PSK and borg passphrase, which must be stored in the clear to be usable).
set -euo pipefail

out="${1:-$(dirname "$0")/../secrets.yml}"
if [[ -e "$out" ]]; then
  echo "$out already exists; delete it first to regenerate." >&2
  exit 1
fi

ask() {
  local prompt="$1" a b
  while true; do
    read -rsp "$prompt: " a; echo >&2
    read -rsp "$prompt (again): " b; echo >&2
    [[ "$a" == "$b" && -n "$a" ]] && { printf '%s' "$a"; return; }
    echo "Didn't match or empty, try again." >&2
  done
}

root_pw=$(ask "root password (break-glass)")
admin_pw=$(ask "dennis login/sudo password")
kiosk_pw=$(ask "guest password (simple, will be posted)")
web_pw=$(ask "admin web password (Command Center, Paperless, Pat)")
read -rp "dennis SSH public key (paste one line, or blank to skip): " ssh_key
psk=$(ask "hotspot WiFi password (8+ chars)")
(( ${#psk} >= 8 )) || { echo "PSK must be 8+ chars" >&2; exit 1; }
borg_pw=$(openssl rand -base64 30 | tr -d '\n')

umask 077
cat > "$out" <<EOF
root_password_hash: "$(openssl passwd -6 "$root_pw")"
admin_password_hash: "$(openssl passwd -6 "$admin_pw")"
kiosk_password_hash: "$(openssl passwd -6 "$kiosk_pw")"
admin_basic_auth_hash: "$(htpasswd -nbBC 12 x "$web_pw" | cut -d: -f2)"
admin_ssh_pubkey: "$ssh_key"
hotspot_psk: "$psk"
borg_passphrase: "$borg_pw"
EOF

echo
echo "Wrote $out"
echo "WRITE THIS DOWN and keep it with the backup drives (needed to restore backups):"
echo "  borg passphrase: $borg_pw"
