#!/usr/bin/env bash
# One-time move from the NOMAD-based setup to the Hub-based one. Run it once on
# the server, before the first `sudo ./bootstrap.sh` of the new version:
#
#   sudo scripts/migrate-from-nomad.sh
#
# What it does (nothing is deleted except NOMAD's containers and old timers):
#   - stops and removes NOMAD's containers (its code and database stay in
#     /opt/project-nomad until you delete them)
#   - moves NOMAD's ZIMs, Kolibri content, videos and books into the new
#     library layout on the USB drive: renames on the same disk, so it's quick
#   - copies the app data you may have used (notes, inventory, passwords,
#     Jellyfin settings, PDF tools) into /opt/homestead/data
#   - removes the NOMAD storage bind mount and the old portal and link timers
set -euo pipefail
[[ $EUID -eq 0 ]] || exec sudo "$0" "$@"

LIB=/srv/library
SRC=$LIB/nomad                      # what NOMAD saw as /opt/project-nomad/storage
DATA=/opt/homestead/data
CORE=/srv/core

mountpoint -q "$LIB" || { echo "The LIBRARY drive isn't mounted at $LIB." >&2; exit 1; }
[[ -d "$SRC" ]] || { echo "No NOMAD storage at $SRC; nothing to migrate." >&2; exit 0; }

echo "== Stopping NOMAD"
if [[ -f /opt/project-nomad/compose.yml ]]; then
  docker compose -p project-nomad -f /opt/project-nomad/compose.yml down 2>/dev/null || true
fi
ids=$(docker ps -aq --filter name=nomad_)
[[ -n "$ids" ]] && docker rm -f $ids >/dev/null
for u in homestead-nomad-links.timer homestead-nomad-links.service homestead-status.timer homestead-status.service; do
  systemctl disable --now "$u" 2>/dev/null || true
  rm -f "/etc/systemd/system/$u"
done
rm -f /usr/local/sbin/homestead-nomad-links /usr/local/bin/homestead-status /etc/homestead/nomad-links.json
systemctl daemon-reload

move() {  # move a folder's contents into a new folder on the same disk
  local from=$1 to=$2
  [[ -d "$from" ]] || return 0
  mkdir -p "$to"
  find "$from" -mindepth 1 -maxdepth 1 -print0 | while IFS= read -r -d '' f; do
    if [[ -e "$to/$(basename "$f")" ]]; then
      echo "  keeping existing $to/$(basename "$f") (NOMAD's copy left in $from)"
    else
      mv "$f" "$to/"
    fi
  done
}

echo "== Library files (renames on the USB drive)"
move "$SRC/zim" "$LIB/zim"
move "$SRC/.homestead-partial/zim" "$LIB/.homestead-partial/zim"
move "$SRC/kolibri-gen2" "$LIB/kolibri"
move "$SRC/media" "$LIB/video"
move "$SRC/books" "$LIB/books/incoming"

echo "== Essentials duplicates (the copy on the internal disk is kept)"
for f in "$LIB"/zim/*.zim; do
  [[ -e "$f" ]] || continue
  if [[ -e "$CORE/zim/$(basename "$f")" ]]; then
    echo "  removing USB copy of $(basename "$f")"
    rm -f "$f"
  fi
done

echo "== App data (copied to the internal disk)"
copy() {
  local from=$1 to=$2
  [[ -d "$from" ]] || return 0
  if [[ -d "$to" && -n "$(ls -A "$to" 2>/dev/null)" ]]; then
    echo "  $to already has data; leaving it (NOMAD's copy is in $from)"
    return 0
  fi
  mkdir -p "$to"
  rsync -a "$from/" "$to/"
  chown -R 1000:1000 "$to"
  echo "  $from -> $to"
}
copy "$SRC/flatnotes" "$DATA/flatnotes"
copy "$SRC/homebox" "$DATA/homebox"
copy "$SRC/vaultwarden" "$DATA/vaultwarden"
rm -f "$DATA/vaultwarden/cert.pem" "$DATA/vaultwarden/key.pem"   # TLS is Caddy's job now
copy "$SRC/jellyfin/config" "$DATA/jellyfin/config"
copy "$SRC/stirling-pdf" "$DATA/stirling-pdf"

echo "== NOMAD storage bind mount"
if mountpoint -q /opt/project-nomad/storage; then umount /opt/project-nomad/storage; fi
sed -i '\#[[:space:]]/opt/project-nomad/storage[[:space:]]#d' /etc/fstab
systemctl daemon-reload

echo "== Old portal files"
rm -rf /srv/portal

cat <<EOF

Done. Next:
  cd ~/bin/homestead-server && git pull && sudo ./bootstrap.sh

What's left from NOMAD, to delete once everything looks right:
  $SRC          (what wasn't moved: its Qdrant index, Ollama copy, logs, maps)
  /opt/project-nomad   (its code and MySQL database)
  docker image prune -a   (NOMAD's container images)
EOF
