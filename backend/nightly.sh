#!/usr/bin/env bash
# The nightly housekeeping run (Render cron: see render.yaml).
#
# Both commands sweep every gym, one tenant scope at a time, and both are
# idempotent, so a retried run is harmless. They are run independently on
# purpose: chained with `&&`, a failure in the first meant the reminders never
# went out at all. The worst exit status is reported at the end, so a scheduler
# watching exit codes still sees that something went wrong.
set -o nounset

status=0

python manage.py expire_subscriptions || status=$?
python manage.py send_reminders || status=$?

exit "$status"
