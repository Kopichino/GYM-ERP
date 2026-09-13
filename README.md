# IRONCORE -- Gym ERP

A free-to-run gym platform with three separate portals -- member, trainer and
admin -- behind a single login. Members self-service check in/out, log workouts,
track progress, and browse announcements/schedule/gallery. Trainers
get their assigned roster, can log sessions for those members, and manage their
own classes and profile. Admins manage all content, import data from other gym
software, and export to Excel.

It also runs the business side: GST invoicing, expenses, trainer commission,
reports, offers and POS checkout, a lead pipeline, member referrals, weekly
workout and diet plans, QR and biometric check-in, expiry reminders by email,
online payment by UPI/card, WhatsApp messaging, and white-label branding.

Stack: Django REST Framework (backend) + React/Vite/TypeScript with React Three
Fiber (frontend). Designed to run entirely on free hosting tiers -- see
`Deployment` below. Every paid integration (Razorpay, WhatsApp, SMTP, Claude)
is optional and off unless its credentials are set; the feature hides itself
rather than failing at the point of use.

## Project layout

```
backend/    Django project (gymerp) -- one app per feature area
frontend/   React + Vite + TypeScript SPA
render.yaml Render blueprint for the backend
```

## Local development

### Backend

```
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env         # defaults work out of the box (SQLite, DEBUG=True)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

API runs at `http://127.0.0.1:8000/api/`. Django admin at `/admin/`.

Without Cloudinary credentials in `.env`, uploaded media (profile photos,
instructor photos, gallery posts) is stored on local disk under `backend/media/`
-- fine for development, but production always needs Cloudinary (see below)
since Render's free-tier disk is wiped on every deploy.

### Running the tests

```
cd backend
python manage.py test
```

That runs the whole suite on SQLite, which is the right default for day-to-day
work. It does not run everything, though: the `tests_concurrency.py` modules
skip themselves on SQLite and say so.

They have to. Four invariants in this project are held by the database rather
than by application code -- one open check-in per user, one live PT booking per
slot, one feedback response per occasion, and gapless invoice numbering -- and
the last two depend on `select_for_update()` taking a real row lock. SQLite has
no such lock (Django reports `has_select_for_update = False` for it) and
serialises writers anyway, so on SQLite those tests would pass without ever
exercising the thing they exist to check. A green SQLite run is not evidence
that a race is handled.

Production is Postgres, so point the suite at one to run them for real:

```
docker run --rm -d -p 5433:5432 -e POSTGRES_PASSWORD=test --name gymerp-test postgres:16
DATABASE_URL=postgres://postgres:test@localhost:5433/postgres python manage.py test
docker rm -f gymerp-test
```

Any Postgres will do -- a Neon branch works the same way. The concurrency tests
fire genuinely simultaneous requests through threads (see `core/testing.py`) and
assert that exactly one wins, so they are worth running before any change to
booking, check-in, or invoice numbering.

### Frontend

```
cd frontend
npm install
copy .env.example .env         # points at http://localhost:8000/api by default
npm run dev
```

App runs at `http://127.0.0.1:5173/`.

### First-time data

The workout catalog (`Exercise`) and schedule/announcement content
are admin-managed -- log into `/admin/` (Django admin) or the in-app Admin
Dashboard (`/admin` route, requires a staff user) to seed some exercises and
content before testing the member-facing pages.

## Environment variables

See `backend/.env.example` and `frontend/.env.example` for the full list.
Key ones:

| Variable | Where | Purpose |
|---|---|---|
| `SECRET_KEY` | backend | Django secret key -- must be a long random value in production |
| `DEBUG` | backend | `False` in production |
| `DATABASE_URL` | backend | Postgres connection string in production; unset = SQLite locally |
| `REDIS_URL` | backend | Shared cache. **Unset = rate limiting is per-process and is wiped on every restart**, so the login and per-username throttles stop holding. `manage.py check --deploy` warns when it is missing in production |
| `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` | backend | Must list the deployed frontend's exact origin |
| `CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET` | backend | Required in production for media uploads |
| `CLOUDINARY_AUTH_TOKEN_KEY` | backend | Optional. Makes signed receipt URLs time-limited. Without it they are signed but do not expire -- still private, but a leaked URL keeps working |
| `DJANGO_ADMIN_ENABLED` | backend | `False` removes the Django admin route entirely. It is a full read/write console over every gym, behind a password alone |
| `DJANGO_ADMIN_URL` | backend | Moves the admin off `/admin/`, which is the path undirected scanning looks for. Default `admin/` |
| `SECURE_HSTS_SECONDS` | backend | HSTS max-age, default one week. Preload is claimed automatically only at a year or more -- raise it once every subdomain is HTTPS-only, since browsers honour it for the full duration regardless of what the server later says |
| `VITE_API_URL` | frontend | Backend API base URL |
| `GYM_NAME` / `GYM_GSTIN` / `GYM_STATE` / `GST_RATE` | backend | Printed on invoices. The branding page overrides these once filled in; `GYM_STATE` decides CGST+SGST vs IGST |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `DEFAULT_FROM_EMAIL` | backend | Outgoing member email. Unset = mail is printed to the console instead of sent |
| `FRONTEND_URL` | backend | Where password-reset emails link to. Must be the deployed frontend's origin in production, or members get a link to localhost |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / `RAZORPAY_WEBHOOK_SECRET` | backend | Online payment. Unset = the member portal doesn't offer it |
| `WHATSAPP_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` / `WHATSAPP_VERIFY_TOKEN` / `WHATSAPP_APP_SECRET` | backend | WhatsApp Business. Unset = nothing is sent and the assistant never replies |
| `ANTHROPIC_API_KEY` / `ASSISTANT_MODEL` | backend | Optional. Lets the WhatsApp assistant answer questions its own matcher doesn't recognise |

## Deployment (all free tier)

1. **Database -- Neon**: create a free Postgres project at neon.tech, copy the
   connection string into `DATABASE_URL`.
2. **Media -- Cloudinary**: create a free account at cloudinary.com, copy the
   cloud name/API key/secret into the backend env vars.
3. **Backend -- Render**: create a free Web Service from this repo with root
   directory `backend`, build command `bash build.sh`, start command
   `gunicorn gymerp.wsgi:application` (or use the included `render.yaml`
   blueprint). Set all the env vars above, plus `ALLOWED_HOSTS` to your Render
   domain. Render's free web services sleep after 15 minutes idle; the
   frontend shows a "waking up the server..." message on cold start rather
   than a bare spinner.
4. **Frontend -- Vercel**: import this repo with root directory `frontend`,
   framework preset Vite. Set `VITE_API_URL` to your Render backend's
   `/api` URL. The included `vercel.json` handles client-side routing
   (React Router) so deep links don't 404.
5. Update the backend's `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` to the
   real Vercel domain once you have it, and redeploy.
6. (Optional) **Sentry**: free-tier project for both Django and React, set
   `SENTRY_DSN` on the backend.

## What's in it

Each feature area is its own Django app. Everything derivable is derived rather
than stored, so two numbers can never disagree:

| Area | App | Notes |
|---|---|---|
| Accounts, roles, profiles | `accounts` | `is_staff` derived from `role` |
| Check-in / out | `attendance` | one open visit per user, enforced by a partial unique index. Tap, QR or biometric all land on the same row |
| Biometric terminals | `devices` | API-key auth (not JWT), punch -> toggle visit |
| Workouts, exercises, weekly split | `workouts` | `days_per_week` is the day count, not a column |
| Diet plans and food catalogue | `nutrition` | calories and macros computed from grams x the catalogue, never written back |
| Body stats and goals | `bodystats` | BMI from height + weight; goal progress from live data |
| Plans, payments, offers, POS checkout | `billing` | `record_payment` is the only write path; membership status is read off the ledger |
| Online payment (Razorpay/UPI) | `billing` | server prices the order; the callback only confirms it was paid |
| GST invoicing | `invoicing` | gapless per-financial-year numbering under `select_for_update`; tax backed out of a tax-inclusive total |
| Expenses | `expenses` | categories, date-ranged summary |
| Trainer commission and payouts | `commissions` | most-specific rule wins; the rate is snapshotted on the entry |
| Reports and custom report builder | `reports` | whitelisted fields only -- no free-text reaches the ORM |
| Enquiries and lead pipeline | `crm` | source, stages, call trail, one-click conversion to a member |
| Member referrals | `referrals` | reward paid as a zero-amount renewal, so expiry moves through the normal ledger |
| Email reminders | `notifications` | nightly sweep, keyed so a re-run sends nothing |
| WhatsApp + assistant | `messaging` | signature-verified webhook; the assistant answers from gym data |
| Classes and bookings | `schedule_app` | capacity held under `select_for_update` |
| Announcements, gallery | `announcements`, `gallery` | |
| White-label branding | `branding` | name, logo and colours applied at runtime |
| Import from other gym software | `dataimport` | preview-then-commit, alias-matched headers |
| Retention / at-risk members | `crm` | thresholds are a row; who is at risk is read off check-in history every time, never flagged |
| Badges, milestones, personal records | `gamification` | criteria evaluated against live counts on read; lift badges name an exercise so "100kg" means something; PRs snapshot bodyweight so the ratio stays true |
| "New PR" moments | `gamification` | what a record beat is derived from the record before it; only *whether the member has seen it* is stored, and back-catalogue records arrive already seen |
| Leaderboard, public and private | `gamification` | the public board is opt-in; the private "just for me" standing gives an opted-out member their own rank, names nobody else, and refuses to place anyone in a pool under five |
| Staff rota | `shifts` | overlap checked under `select_for_update`; who is on the floor is derived |
| Day passes and walk-in guests | `billing`, `attendance` | guest visits share the check-in table so footfall figures cannot miss them; `user` is null, which leaves the one-open-check-in index untouched |
| Personal training | `pt` | slots derived from a weekly pattern minus days off minus bookings -- there is no slot table |
| Owner KPIs and occupancy heatmap | `reports` | MRR, ARPM, churn, PT utilisation and class fill computed on read, each carrying its own definition |
| Access control at the door | `devices` | turnstiles and doors check membership before opening; terminals behave as before |
| NPS / member feedback | `feedback` | the score is derived from responses; a pending prompt is an unanswered visit, not a queued row |
| Multi-tenancy | `tenancy` | Organisation -> Tenant (branch) -> Membership(user, tenant, role). Role lives on the membership, not the user, so one person can coach at two gyms and own a third |
| Custom domains | `tenancy` | a gym proves ownership with a DNS TXT record before the domain does anything; only verified domains resolve, get through `ALLOWED_HOSTS`, or are allowed as a CORS origin |
| Per-gym email identity | `tenancy` | reminders come from the gym's own domain once SPF and DKIM verify; until then they go from the platform, because unauthenticated mail lands in spam and the gym never finds out |
| Tenant isolation | `tenancy` | scoped managers are the *default* manager on every tenant-owned model, so a forgotten filter is a non-event; `.unscoped` is the deliberate way past. Reads with no tenant in scope raise rather than returning everything |
| Website enquiry form | `tenancy`, `crm` | a gym's own site posts leads straight into their pipeline. The key is assumed public, so it can only *create*, is rate limited per key rather than per IP, and spam is dropped silently with the same 201 an accepted lead gets |

### Multi-tenancy

Every operational row belongs to a branch and every shared setting to a brand.
The API carries the branch in its path -- `/api/t/<slug>/...` -- which the
middleware strips before routing, so every existing route works unchanged and
the eventual switch to per-gym domains deletes a branch of code rather than
rewriting anything.

Three things hold isolation up, and they fail in different directions:

* **Scoped managers.** `Model.objects` is filtered to the tenant in scope, and
  *raises* when there is none. Returning every row would be the bug; returning
  an empty set would hide it.
* **Membership-driven permissions.** `request.access` says what the caller is
  *at this gym*, read fresh from Membership on every request rather than baked
  into a token that keeps asserting a role after it is revoked.
* **A registry test.** `tenancy/tests_isolation.py` walks Django's model
  registry and fails if a model is neither scoped nor on an explicit exemption
  list -- which is what stops the next model added from quietly leaking.

Work outside a request -- the nightly reminder sweep, management commands --
iterates tenants and runs each inside its own scope.

### Custom domains

A gym adds `app.theirgym.com` from **Setup -> Web Address**, publishes one TXT
record at `_ironcore-verify.<domain>`, and clicks Check. Until that record
matches, the domain is inert -- it does not resolve, it is not an allowed host,
and it is not an accepted CORS origin.

That gate is not bureaucracy. The tenant is resolved *from* the hostname, so
honouring an unproved claim would let anyone who can type a domain name be
served another gym's data.

`ALLOWED_HOSTS` and CORS both became dynamic to support this. Verified
hostnames are cached for a minute and the cache is dropped the moment a domain
is verified or removed, so going live is immediate and a removed domain stops
being served at once.

**Certificates are the host's job, not this system's.** On Render and Vercel,
TLS is issued and renewed by the platform once a domain points at it -- they
terminate the connection, so they answer the ACME challenge. `tenancy/certificates.py`
therefore registers the domain with the host and records what it reports; it
holds no keys and runs no ACME client. With no `RENDER_API_KEY` configured it
says "pending" and tells you to add the domain in the dashboard, which is
truthful, rather than claiming a certificate exists.

### Outgoing email

Two senders exist and they are never allowed to blur:

* **The gym's identity** -- renewal reminders and invoices to *their* members,
  from their own domain, so a member sees the gym they joined.
* **The platform identity** -- billing, support and service notices to gym
  *owners*. Fixed, never tenant-branded. A message telling an owner their
  subscription lapsed must not arrive dressed as their own gym; that is how a
  legitimate mail comes to look like a forgery.

`sender_for(tenant)` and `platform_sender()` are the only two ways to pick a
From address. A gym with no verified sending domain falls back to the platform
one -- sending as a domain that cannot be authenticated is worse than not
trying, because it lands in spam and nobody learns the reminders stopped.

Setup is guided from **Setup -> Email Address**: the gym is shown the exact SPF
and DKIM rows to publish, each marked done or outstanding separately, because
with two records to add "not verified" sends an owner back to the one that was
already right.

**Provider: Postmark.** Its domains API returns the DKIM selector and value in
one call and reports per-record verification state, which is what makes a
guided screen possible rather than "go and read their docs"; and being
transactional-only, a gym's reminders do not share sending reputation with bulk
marketing. SendGrid is the better choice only if you later want campaigns from
the same account. The DKIM key is generated *by the provider* and cannot be
computed here, so with no `POSTMARK_ACCOUNT_TOKEN` configured the screen says
the record cannot be issued rather than showing an invented one.

### Website enquiry form

A gym pastes a contact form into their own marketing site and the people who
fill it in land directly in **Enquiries**, tagged `Gym website`. Keys are issued
from **Setup -> Website Form**, which also hands over the ready-made form code
with the key already in it.

**The key is not a secret, and nothing here pretends otherwise.** It sits in
client-side JavaScript on a public page, so anyone can read it. What makes that
survivable is its reach, not its secrecy:

* it can create one enquiry in one gym's pipeline and do nothing else -- no
  reading, no listing, no view of what is already there;
* it is rate limited **per key** (`leads`, 30/hour). Per-IP would be wrong here:
  a gym's form sits behind their CDN so visitors share an address, and one
  gym's spam would spend every other gym's allowance;
* a honeypot field (`company_website`) catches undirected form bots;
* origins can optionally be pinned, which turns a leaked key into one that only
  works from the gym's own site;
* revoking is one click, and a gym may hold several keys so a compromised one
  is replaced without taking the working form down first.

Only a hash is stored, so the plaintext is shown exactly once, at issue.

This is also the one path that answers **any** origin. A gym's marketing site is
a different host from the `app.` domain they verified for the portal and is
often not on this platform at all, so judging it by the verified list would mean
the form we hand them fails in every browser with a CORS error. Opening it costs
nothing: the browser was never what kept anyone out -- the key is public and
curl ignores CORS entirely -- and the endpoint authenticates on a header alone,
so a cookie riding along is ignored rather than trusted. `x-lead-key` is in
`CORS_ALLOW_HEADERS` for the same reason; a header the preflight omits is one
the browser refuses to send.

Spam is dropped **silently**: a submission that trips a check gets the same
`201 {"received": true}` as one that is accepted. Telling a bot which rule
caught it is a free lesson in getting past it, and a real visitor whose message
tripped a filter cannot act on the error anyway.

```
POST /api/t/<slug>/tenancy/leads/
X-Lead-Key: lead_...

{"name": "...", "phone": "...", "email": "...", "message": "..."}
```

`name` plus either `phone` or `email` is required -- a lead with no way to reach
them is not a lead, and insisting on both loses people who will only give one.

### Demo data

```
python manage.py seed_demo          # a full gym across every feature
python manage.py seed_demo --wipe   # remove it again
```

Creates an admin, two trainers and five members (each showing a different
state -- active, lapsed, paused, brand new), all with the password
`IronDemo123!`. The command prints the account list and a one-time device key
when it finishes.

### Scheduled commands

None of these are wired up automatically; run them from a scheduler (the
included `render.yaml` has a nightly cron service). All are safe to re-run.

| Command | What it does |
|---|---|
| `expire_subscriptions` | Flips lapsed members to expired, skipping anyone manually paused |
| `send_reminders` | Emails members 7 / 3 / 1 days before expiry, and once the day after. `--dry-run` lists who would be written to |
| `send_whatsapp_reminders` | The same nudge over WhatsApp. Shares the notification log with the email sweep, so a member is contacted on one channel, not both |
| `import_exercises` | Loads the bundled exercise catalogue |
| `import_foods` | Loads the starter food catalogue used by diet plans |

## Roles and portals

`User.role` is one of `member`, `trainer` or `admin`, and decides which portal
an account lands in after login (`/dashboard`, `/trainer`, `/admin`). Each portal
is closed to the other two roles on both the frontend (route guards) and the API
(permission classes) -- the frontend redirect is convenience, the API check is
the actual boundary.

| Role | Can reach |
|---|---|
| `member` | Own check-in, workouts, progress, billing + shared gym content |
| `trainer` | Assigned members (view + log workouts for them), own classes, own account |
| `admin` | Everything in the admin dashboard, including data import and Excel export |

- Self-signup always creates a `member`; only an admin can promote an account.
- `is_staff` is derived automatically from `role == admin` and exists only so
  Django's own `/admin/` site keeps working. Branch on `role` in app code.
- Promote a user via the admin dashboard's Trainers tab, Django admin, or
  `createsuperuser` (superusers are forced to `admin`).
- A class names the trainer who runs it directly -- their own account. There
  are no separate instructor profiles; the `instructors` app is kept only as a
  migrations shell, because other apps' migrations depend on it.

## Importing from other gym software

Admin dashboard -> **Import Data** takes a CSV or Excel export from another
platform (FitnessForce, GymForce, Torzil, GymMaster, ...) for members, billing
or trainers.

Of those platforms only GymMaster publishes its export schema, so the importer
does not hardcode one format per vendor. It normalises the header row and
matches it against a list of aliases per field, so `First Name`, `first_name`,
`member_firstname` and `FIRSTNAME` all resolve to the same field. Dates are
accepted in ~13 formats, amounts tolerate currency symbols and thousands
separators, and status/payment-method values are mapped through synonym tables
(`Frozen` -> paused, `Cancelled` -> expired, `NEFT` -> bank transfer, ...).

Because detection is a best guess, every import is two-stage: **preview** parses
and validates without writing anything and shows the detected mapping, which you
can correct column by column; **import** then commits. Rows with errors are
skipped and reported individually rather than failing the whole file. Re-running
the same file updates the existing rows (matched on email) instead of
duplicating them. A blank template in the canonical format is downloadable from
the same page.

Imported member/trainer accounts are created without a usable password, and are
enrolled at the gym that imported them. The member sets a first password with
**Forgot password** on the login page, or an admin sets one from **Members** --
the only route for a phone-only import, whose placeholder email cannot receive
a link. A trainer row now needs an email, since a trainer exists only as an
account.

## Notes

- Auth is JWT (SimpleJWT): short-lived access token held in memory on the
  frontend, refresh token as an httpOnly cookie. Refresh/logout blacklist old
  tokens.
- The check-in/out flow enforces "one open check-in per user" at the database
  level (a partial unique constraint), not just in application code.
- Run the frontend dev server on the same hostname as `VITE_API_URL` (both
  `localhost`, not one `localhost` and one `127.0.0.1`) -- browsers treat those
  as different sites and will drop the SameSite refresh cookie, which silently
  logs you out on every reload.
- Membership status, BMI, plan macros, referral status, discount usage and
  report figures are all computed on read. The only things written down are
  facts nothing else can produce: payments, measurements, check-ins, and what
  has already been emailed.
- Money never comes from the browser. Online checkout prices the order
  server-side and writes it to a `PaymentOrder`; Razorpay's callback and webhook
  can only confirm that order was paid, and the order's one-to-one link to a
  payment is what makes a doubled callback harmless.
- The front-desk QR code is an HMAC over a one-minute time window, so a
  screenshot stops working almost immediately and there is no table of codes to
  clean up.
- The WhatsApp assistant answers recognised questions straight from the database
  with no model in the loop. Only unrecognised questions reach Claude, and then
  with the member's facts already fetched and an instruction to answer only from
  them -- so it rephrases known truths rather than being trusted to know
  anything. With no API key it says what it can help with instead of guessing.
