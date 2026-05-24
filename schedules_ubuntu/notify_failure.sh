#!/usr/bin/env bash
# Send a ntfy.sh push notification when a systemd user unit fails.
# Invoked by `OnFailure=stock-notify@%n.service` on each scheduled unit.
# Usage: notify_failure.sh <failed-unit-name>
#
# Requires NTFY_TOPIC env var (set via stock-notify@.service's EnvironmentFile,
# pointing at ~/.config/systemd/user/stock-notify.env which is gitignored).
set -euo pipefail

unit="${1:-unknown-unit}"
topic="${NTFY_TOPIC:-}"

if [ -z "$topic" ]; then
    echo "notify_failure: NTFY_TOPIC not set; aborting" >&2
    exit 1
fi

host="$(hostname)"

# Last few lines of the failed unit's journal for context. journalctl --user
# is the same source we'd hit by hand when debugging.
log_tail="$(journalctl --user -u "$unit" -n 12 --no-pager 2>/dev/null | tail -10 || echo '(no journal)')"

curl -fsS \
    -H "Title: ${unit} failed on ${host}" \
    -H "Priority: high" \
    -H "Tags: warning,rotating_light" \
    -d "${log_tail}" \
    "https://ntfy.sh/${topic}" > /dev/null
