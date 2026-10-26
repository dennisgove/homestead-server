"""Library jobs. Each runs as a systemd oneshot (homestead-<job>.service) and
reports progress in paths.status/<job>.json, which the Hub's pages read."""
