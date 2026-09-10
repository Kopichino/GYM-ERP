"""Drive a running IRONCORE backend as each of the three roles.

Stdlib only, so it runs under the project venv with nothing installed.

What this is for: IRONCORE is multi-tenant, and almost every API route now
lives under `/api/t/<slug>/`. The two bugs this script was written after were
both invisible to the test suite and obvious the moment something actually
called the API -- a missing import that 500'd one endpoint, and a route sent
without its tenant prefix that 403'd. Both showed up here in one run.

Usage (from the repo root, backend already running on :8000):

    backend/venv/Scripts/python.exe .claude/skills/run-gym-erp/smoke.py
    backend/venv/Scripts/python.exe .claude/skills/run-gym-erp/smoke.py --tenant ironcore-main

Exit code is 0 only when every expected status matched.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

PASSWORD = "IronDemo123!"

# (path, expected status). Expectations, not just "not a 500" -- a 403 where a
# 200 belongs is exactly the bug class this exists to catch, and it does not
# look like a crash.
ADMIN = [
    ("expenses/", 200), ("billing/", 200), ("crm/enquiries/", 200),
    ("crm/at-risk/", 200), ("reports/kpis/", 200), ("invoices/", 200),
    ("gamification/badges/", 200), ("commissions/entries/", 200),
    ("devices/", 200), ("shifts/", 200), ("feedback/surveys/", 200),
    ("referrals/", 200), ("announcements/", 200), ("instructors/", 200),
    ("gallery/", 200), ("schedule/", 200), ("billing/plans/", 200),
    ("billing/day-passes/", 200), ("branding/", 200),
]
MEMBER = [
    ("attendance/", 200), ("workouts/sessions/", 200), ("workouts/logs/", 200),
    ("nutrition/plans/", 200), ("bodystats/summary/", 200),
    ("gamification/achievements/", 200), ("gamification/records/new/", 200),
    ("wearables/metrics/", 200), ("pt/sessions/", 200), ("schedule/", 200),
    ("feedback/surveys/pending/", 200),
    # Admin-only, from a member token. A 200 here is a privilege escalation.
    ("expenses/", 403), ("reports/kpis/", 403),
]
TRAINER = [
    ("attendance/", 200), ("workouts/sessions/", 200), ("pt/sessions/", 200),
    ("pt/availability/", 200), ("shifts/", 200), ("crm/at-risk/", 200),
    ("schedule/", 200),
    # Trainers read their own earnings through a different route; the entries
    # list is IsAdmin, so 403 is correct and not a regression.
    ("commissions/entries/", 403),
]


def call(url, token=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        print(f"  cannot reach {url}: {exc.reason}")
        print("  is the backend running? see SKILL.md -> Run (agent path)")
        sys.exit(2)


def login(base, username):
    status, body = call(f"{base}/api/auth/login/", payload={
        "username": username, "password": PASSWORD,
    })
    if status != 200:
        print(f"  login failed for {username}: HTTP {status} {body[:200]!r}")
        sys.exit(2)
    return json.loads(body)["access"]


def run(base, tenant):
    prefix = f"{base}/api/t/{tenant}"
    failures = []

    for label, username, checks in (
        ("ADMIN", "demo.admin", ADMIN),
        ("MEMBER", "arjun.s", MEMBER),
        ("TRAINER", "coach.ravi", TRAINER),
    ):
        token = login(base, username)
        print(f"\n{label}  ({username})")
        for path, expected in checks:
            status, _ = call(f"{prefix}/{path}", token=token)
            ok = status == expected
            print(f"  {'ok  ' if ok else 'FAIL'} {status:<4} {path}"
                  f"{'' if ok else f'  (expected {expected})'}")
            if not ok:
                failures.append((label, path, status, expected))

    # Isolation: the same admin token against a gym they hold no Membership at.
    # This is the check that proves tenant scoping is actually enforcing.
    token = login(base, "demo.admin")
    status, _ = call(f"{base}/api/t/definitely-not-a-real-gym/expenses/", token=token)
    print(f"\nISOLATION\n  {'ok  ' if status in (403, 404) else 'FAIL'} {status:<4} "
          f"unknown tenant -> expenses/  (expected 403 or 404)")
    if status not in (403, 404):
        failures.append(("ISOLATION", "unknown tenant", status, 403))

    print()
    if failures:
        print(f"{len(failures)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--tenant", default="ironcore-main")
    args = parser.parse_args()
    sys.exit(run(args.base, args.tenant))
