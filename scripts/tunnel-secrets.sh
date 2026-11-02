#!/usr/bin/env bash
# Set up (or change) the Cloudflare Tunnel's secrets in secrets.yml: the tunnel's token, from
# Cloudflare's dashboard (or "quick": a temporary trycloudflare.com address, no account needed),
# and the password everyone types to use the website through it.
# Then run bootstrap.sh again. A blank token takes the tunnel out.
#   sudo bash scripts/tunnel-secrets.sh [/opt/homestead/repo/secrets.yml]
set -euo pipefail

out="${1:-/opt/homestead/repo/secrets.yml}"
[[ -f "$out" ]] || { echo "$out isn't there: run bootstrap.sh first." >&2; exit 1; }

read -rsp "Tunnel token (the long eyJ... after --token in Cloudflare's Docker command; quick = a temporary address; blank = no tunnel): " token; echo >&2
token="${token#*--token }"; token="${token// /}"
pw=""
if [[ -n "$token" ]]; then
  while true; do
    read -rsp "Password for the website through the tunnel: " a; echo >&2
    read -rsp "Again: " b; echo >&2
    [[ "$a" == "$b" && -n "$a" ]] && { pw="$a"; break; }
    echo "Didn't match or empty, try again." >&2
  done
fi

umask 077
tmp=$(mktemp "$out.XXXX")
grep -v '^tunnel_token:\|^tunnel_basic_auth_hash:' "$out" > "$tmp" || true
if [[ -n "$token" ]]; then
  echo "tunnel_token: \"$token\"" >> "$tmp"
  echo "tunnel_basic_auth_hash: \"$(htpasswd -nbBC 12 x "$pw" | cut -d: -f2)\"" >> "$tmp"
fi
chmod 600 "$tmp"
mv "$tmp" "$out"
echo "Wrote $out. Now: sudo ./bootstrap.sh"
