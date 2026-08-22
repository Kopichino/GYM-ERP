#!/usr/bin/env bash
# Render build command: installs deps, collects static files, and applies
# migrations on every deploy so the live DB schema never drifts from code.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
