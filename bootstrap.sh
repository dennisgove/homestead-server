#!/usr/bin/env bash
# Run on the server after the Ubuntu install:  sudo ./bootstrap.sh [ansible args]
# Safe to re-run; the playbook is idempotent.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }
here="$(cd "$(dirname "$0")" && pwd)"
dest=/opt/homestead/repo

apt-get update || echo "apt update failed (offline?); continuing with what's installed"
apt-get install -y ansible apache2-utils rsync openssl

# Keep a copy of the repo on the box (it gets backed up and is used for rebuilds).
# secrets.yml is excluded so a fresh copy from elsewhere never deletes it; losing
# it would mean a new borg passphrase that no longer matches the backups.
mkdir -p "$dest"
if [[ "$here" != "$dest" ]]; then
  rsync -a --delete --exclude .git --exclude /secrets.yml "$here/" "$dest/"
fi

if [[ ! -f "$dest/secrets.yml" ]]; then
  bash "$dest/scripts/make-secrets.sh" "$dest/secrets.yml"
fi
chmod 600 "$dest/secrets.yml"

cd "$dest"
ansible-playbook site.yml "$@"

# The quick tunnel's address (scripts/tunnel-secrets.sh, token "quick"): last, so it doesn't scroll away.
if docker inspect -f '{{.State.Running}} {{.Config.Cmd}}' homestead-cloudflared 2>/dev/null | grep -q '^true .*--url'; then
  url=""
  for _ in $(seq 15); do
    url=$(docker logs homestead-cloudflared 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 || true)
    [[ -n "$url" ]] && break
    sleep 2
  done
  echo
  echo "The website from the internet: ${url:-no address yet (docker logs homestead-cloudflared)}"
  echo "(user name homestead and the tunnel password; the address changes when the tunnel restarts)"
fi
