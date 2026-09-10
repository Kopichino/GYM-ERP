---
name: run-gym-erp
description: Run, start, launch, screenshot or smoke-test IRONCORE — the multi-tenant gym ERP (Django REST backend on :8000, React/Vite frontend on :5173). Covers starting both servers, the demo logins, the /t/<slug>/ tenant URL prefix every API route now needs, and driving all three portals in a browser.
---

# Running IRONCORE

Django REST backend + React/Vite frontend, one repo, two servers that must
**both** be up. Drive the API with `smoke.py` in this directory; drive the UI
with the Browser pane tools.

Paths below are relative to the repo root. Environment is **Windows**; the
backend runs from a checked-in venv at `backend/venv/`, so there is no
`python` on PATH to use — always the venv interpreter by full path.

## The one thing that will waste your time

Every API route except sign-in now lives under a tenant prefix:

```
/api/t/ironcore-main/expenses/     <- correct
/api/expenses/                     <- 403, no tenant resolved
```

Platform-level routes that take **no** prefix: `/api/auth/signup/`,
`/api/auth/login/`, `/api/auth/refresh/`, `/api/auth/logout/`, `/api/auth/me/`.
Everything else under `/api/auth/` — `admin/members/`, `admin/users/`,
`trainer/members/` — **is** tenant-scoped and does take the prefix.

The current tenant slug is `ironcore-main`. Confirm it:

```bash
cd backend && ./venv/Scripts/python.exe -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','gymerp.settings')
django.setup()
from tenancy.models import Tenant
print(list(Tenant.objects.values_list('slug', flat=True)))
"
```

## Run (agent path)

Both servers are declared in `.claude/launch.json`. Start them with the
`preview_start` tool — **not** Bash — one call each:

- `preview_start` with `name: "gym-erp-backend"` → :8000
- `preview_start` with `name: "gym-erp-frontend"` → :5173

Then smoke the API as all three roles:

```bash
./backend/venv/Scripts/python.exe .claude/skills/run-gym-erp/smoke.py
```

41 checks across admin / member / trainer, plus a cross-tenant isolation
probe. Exit 0 only if every expected status matched. It asserts **expected**
codes, not merely "not a 500" — a 403 where a 200 belongs is the bug class
this exists to catch and it does not look like a crash.

To drive the UI, navigate to `http://localhost:5173/login` and submit the form
via `javascript_tool` (the React inputs ignore plain `.value` assignment, so go
through the native setter):

```js
const set=(el,v)=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));};
const i=document.querySelectorAll('input');
set(i[0],'demo.admin'); set(i[1],'IronDemo123!');
document.querySelector('form').requestSubmit();
```

Then `computer` → `screenshot`. **Look at it.** A rendered nav bar over an
empty body is the failure mode here, not a blank page — see Gotchas.

## Demo logins

Every seeded account uses `IronDemo123!`.

| Username | Role | Why this one |
|---|---|---|
| `demo.admin` | admin | Owner dashboard, KPIs, heatmap |
| `coach.ravi` | trainer | 2 assigned members, shifts, PT diary |
| `arjun.s` | member | Richest data — PRs, badges, leaderboard |
| `meena.d` | member | Opted out of the leaderboard |
| `rahul.v` | member | Expired membership, shows in at-risk |
| `vikram.r` | member | Brand new, exercises empty states |

Reseed (destructive — wipes demo rows only, keyed on the `@ironcore.demo`
email domain):

```bash
cd backend && ./venv/Scripts/python.exe manage.py seed_demo --wipe && ./venv/Scripts/python.exe manage.py seed_demo
```

## Test

Default run is SQLite and **skips 30 concurrency tests**:

```bash
cd backend && ./venv/Scripts/python.exe manage.py test
```

Those 30 hold the four database-level invariants (one open check-in per user,
one live PT booking per slot, one feedback response per occasion, gapless
invoice numbering). SQLite serialises writers and ignores `select_for_update`,
so they cannot be reproduced on it and skip themselves loudly. A green SQLite
run is not evidence any race is handled. For the real thing:

```bash
docker run -d --name ironcore-test-pg -e POSTGRES_PASSWORD=testpass -e POSTGRES_USER=ironcore -e POSTGRES_DB=ironcore -p 55432:5432 postgres:16
cd backend && DATABASE_URL="postgres://ironcore:testpass@127.0.0.1:55432/ironcore" ./venv/Scripts/python.exe manage.py test
```

Postgres needs `psycopg`, which is **not** in `requirements.txt`:

```bash
cd backend && ./venv/Scripts/python.exe -m pip install "psycopg[binary]"
```

Full Postgres run is ~12 minutes. Tear down with `docker rm -f ironcore-test-pg`.

## Gotchas

- **"Invalid username and password" usually means the backend is down.** The
  login form shows that message for any failed request, including a refused
  connection. Check `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/health/`
  before believing it is a credentials problem.
- **A rendered nav bar with an empty body under it is a 500, not a slow load.**
  React renders the shell before data arrives, so a crashed endpoint leaves the
  chrome intact. Go to `preview_logs` with `level: "error"` for the traceback —
  the browser console only shows the status code.
- **Frontend URL prefixing lives in exactly one place**, the axios interceptor
  in `frontend/src/lib/api.ts`. Do not add `/t/<slug>/` at call sites. When
  custom domains land, the server resolves the tenant from the Host header and
  that interceptor gets deleted.
- **The tests skip on SQLite without failing.** `OK (skipped=30)` is easy to
  read as a clean run. It is not.
- **`reset_sequences = True` on a `TransactionTestCase` collides with the
  tenancy backfill**, which inserts an Organisation at id 1 — the reset hands
  that id out again and the insert fails on the primary key. Do not add it to
  test classes that touch tenancy.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `NameError: name 'access' is not defined` | A view calls `access(request)` without importing it | `from core.permissions import access` |
| Endpoint 403s for a role that should have it | Called without the tenant prefix, so no tenant resolved and the caller holds no roles | Use `/api/t/ironcore-main/...` |
| Trainer sees "no members assigned" | `/api/auth/trainer/members/` sent unprefixed | It is tenant-scoped despite living under `/auth/`; see the prefix rules above |
| `duplicate key ... tenancy_organisation_pkey` in tests | `reset_sequences = True` plus the backfill's row at id 1 | Drop `reset_sequences` from that class |
| Concurrency tests all skip | Running on SQLite | Point `DATABASE_URL` at Postgres |
