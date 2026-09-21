#!/usr/bin/env bash
# Render build command: installs deps, collects static files, and applies
# migrations on every deploy so the live DB schema never drifts from code.
# Then loads the shared exercise and food catalogues. Foods can only be added by
# platform staff, so without this a fresh deploy's diet planner has nothing to
# pick from. The food import adds missing foods by name and leaves existing
# ones exactly as they are, so it is safe on every deploy.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py import_exercises
python manage.py import_foods
