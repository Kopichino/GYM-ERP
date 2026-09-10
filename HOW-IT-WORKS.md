# IRONCORE, in plain English

This document explains what the system does and why, without assuming you write
software. If you run a gym, work at one, or have just been handed this project,
start here. The technical companion is [README.md](README.md).

---

## What it is

IRONCORE is the software a gym runs on. One system covering the whole business:

- getting people through the door and knowing who is inside
- selling memberships and taking the money
- invoicing, expenses, and paying trainers their cut
- workout and diet plans
- classes, personal training, and staff rotas
- chasing leads, keeping members, and nudging the ones about to drift away

It replaces the usual pile — a spreadsheet for members, a notebook at the desk,
a WhatsApp group for announcements, and a separate app for billing — with one
place where those things agree with each other.

It is also **multi-gym**. One installation can run many gyms, each with its own
members, staff, branding, web address and email. A gym with three branches keeps
them separate but under one brand.

---

## Who uses it

There are three front doors, and everyone logs in at the same place. What you
see afterwards depends on who you are.

### Members

They can do the things that used to need a staff member:

- **Check in and out** by tapping a button, scanning the front-desk QR code, or
  putting a finger on the biometric terminal
- **Log workouts** — pick exercises, record sets and weights
- **Follow their plan** — a weekly workout split and a diet plan set by their
  trainer
- **Track progress** — weight, measurements, BMI, goals, and charts over time
- **See their membership** — when it expires, what they've paid, their invoices
- **Renew or buy** online by UPI or card
- **Book personal training** and see class timetables
- **Refer friends** and earn free time
- **Earn badges** and appear on a leaderboard, if they want to

### Trainers

- Their **assigned members only** — not the whole gym
- Log workouts on a member's behalf
- Write workout splits and diet plans for those members
- Run their own **classes** and manage their public instructor profile
- See their **PT bookings** and their own **earnings** — what commission they've
  made and what has been paid out

### Admins / owners

Everything else:

- Members, trainers, plans, offers, day passes
- Billing, invoices, expenses, commission
- Reports: revenue, churn, occupancy, class fill, PT utilisation
- Enquiries and the lead pipeline
- Announcements, instructors, the photo gallery, badges
- Schedule and staff rota
- Importing everything from your old gym software
- Branding, web address, email address, website contact form

Each portal is closed to the other two — both in the app and at the server.
The app redirect is convenience; the server check is the real lock.

---

## A normal day

**7:00 am** — A member taps their finger on the terminal at the door. The system
opens a visit for them. If their membership expired last week, the door does not
open and the desk sees why.

**7:40 am** — They finish, tap out, and their visit is closed. Their check-in
streak and consistency calendar update on their phone.

**10:00 am** — Someone fills in the contact form on the gym's website. It lands
in the **Enquiries** pipeline, marked as coming from the website, due for a call
today. Nobody had to check an inbox.

**11:15 am** — The front desk calls them, marks it *Contacted*, and books a
trial. When they join, one click converts the enquiry into a member — no
re-typing.

**2:00 pm** — A trainer logs a session for one of their members. The commission
on it is calculated using the rate that applied on that day, and is added to
their earnings.

**6:00 pm** — A member renews online by UPI. The price is decided by the server,
not the browser. A GST invoice is generated with the next number in the
sequence, and their expiry date moves.

**Midnight** — A scheduled job emails everyone whose membership expires in 7, 3
or 1 days, and once the day after. Nobody gets emailed twice, and members who
already got a WhatsApp nudge are skipped.

---

## What's in it, grouped by the job it does

### Getting people in the door

| | |
|---|---|
| **Check-in / out** | Tap, QR code, or fingerprint — all three end up as the same record |
| **Front-desk QR** | Changes every minute, so a screenshot is useless within seconds |
| **Biometric terminals** | Fingerprint readers and turnstiles, which check membership before opening |
| **Day passes** | Walk-in guests get counted in footfall like anyone else |

### Members and memberships

Plans, offers and discounts, member profiles and photos, membership status,
paused and expired states, and bulk import from your old system.

### Money

| | |
|---|---|
| **Payments** | Cash, card, UPI, bank transfer — one place they all land |
| **Online checkout** | UPI or card through Razorpay |
| **GST invoicing** | Correct, gapless numbering per financial year; CGST+SGST or IGST depending on state |
| **Expenses** | Categorised, with a date-range summary and a breakdown chart |
| **Trainer commission** | Rules per trainer, per plan, or gym-wide — the most specific one wins |
| **Reports** | Revenue, monthly recurring revenue, average revenue per member, churn, class fill, PT utilisation |

### Training

Exercise library, weekly workout splits, session logging, body stats and goals,
diet plans built from a food catalogue, and personal training bookings.

### Classes and staff

Class timetables with capacity limits, instructor profiles, and staff rotas
with shift-overlap checking.

### Growing and keeping the gym

| | |
|---|---|
| **Enquiries** | A lead pipeline with call reminders and stages |
| **Website form** | Your own site's contact form posts straight into that pipeline |
| **Referrals** | Members refer friends; the reward is paid as free membership time |
| **Retention** | Who has stopped coming, worked out from their actual check-in history |
| **Feedback / NPS** | Members rate visits and PT sessions |
| **Announcements & gallery** | Gym news and member photos, with moderation |

### Communication

Email reminders before and after expiry, the same over WhatsApp, and a WhatsApp
assistant that answers questions like "when does my membership end?" straight
from the database.

### Motivation

Badges and milestones, personal-record moments ("🎉 New PR!"), and an
**opt-in** leaderboard. Members who would rather not appear publicly can still
see their own standing privately — and if fewer than five people are in a pool,
nobody is ranked at all, because a "3rd of 4" tells you nothing useful and tells
everyone else too much.

---

## Running more than one gym

This is the part that turns a gym app into a platform.

### The shape of it

```
Organisation  (the brand)          "Iron Fitness"
     |
     +-- Tenant  (a branch)        "Iron Fitness — Andheri"
     +-- Tenant  (a branch)        "Iron Fitness — Bandra"
```

Anything operational — members, check-ins, payments, classes — belongs to a
**branch**. Anything shared — the brand, the logo — belongs to the
**organisation**.

### People can belong to more than one gym

A person has **one account**, and separate memberships at each gym. That matters
in real life:

- a trainer coaching at two unrelated gyms
- an owner overseeing three branches
- a member with a day pass visiting a different gym while travelling

Their role is attached to the *membership*, not to the person. Someone can be a
trainer at one gym and a member at another, and the system never confuses the
two. Crucially, it is re-checked on every request, so revoking someone's access
takes effect immediately rather than whenever their login happens to expire.

### Gyms cannot see each other

This is the promise the whole platform rests on, so it is enforced in three
independent ways:

1. **Everything is filtered by default.** Asking for "all members" gives you
   this gym's members. There is no way to forget the filter — and if no gym is
   in context, the system refuses to answer rather than guessing.
2. **Permissions are per gym.** Being an admin at Gym A grants nothing at Gym B.
3. **An automatic audit.** A test walks every table in the system and fails the
   build if a new one isn't isolated. This is what stops the next feature
   someone adds from quietly leaking.

The practical test: a user logged in for Gym A gets nothing back for a Gym B
record, *even if they type in a real Gym B ID*.

### Each gym looks like its own product

| Feature | What the gym does | What members see |
|---|---|---|
| **Branding** | Upload a logo, pick colours and a font | The app in their gym's colours |
| **Web address** | Add `app.theirgym.com`, publish one DNS record, click Check | Their own address, not a shared link |
| **Email** | Add two DNS records | Reminders arriving from *their* domain |
| **Website form** | Copy a snippet into their marketing site | A contact form that feeds the pipeline |

Each of these is set up by the gym owner, on screen, with the exact values to
copy and a clear "done" or "not found yet" per record. No support ticket, no
developer.

Two deliberate rules:

- **A domain does nothing until it is proved.** You publish a verification
  record before the address works. This isn't red tape — the system works out
  *which gym you are* from the address, so accepting an unproved claim would let
  anyone who can type a domain name be served someone else's data.
- **Platform mail is never dressed as a gym.** Billing and account notices to
  gym owners come from a fixed platform address. An email saying "your
  subscription lapsed" must not arrive looking like the gym's own mail — that is
  how a genuine message comes to look like a scam.

---

## The one idea behind most of the design

**If a number can be worked out, it is worked out — not stored.**

Take membership status. The obvious approach is a column saying `active` or
`expired`, updated whenever something happens. The problem is that it can drift:
a payment gets recorded and the column doesn't update, and now the member is
active in one place and expired in another. Which one is right? Nobody knows.

So instead, membership status is *read off the payment history* every time
somebody asks. There is no second copy to disagree with the first.

The same idea runs through the system:

| Instead of storing... | It works it out from... |
|---|---|
| Membership status | The payments actually recorded |
| BMI | Height and the latest weight |
| Diet plan calories and macros | The grams in the plan × the food catalogue |
| "At risk" members | Their real check-in history |
| Referral rewards earned | The referrals that actually converted |
| Available PT slots | The trainer's weekly pattern, minus days off, minus bookings |
| Every report figure | The underlying records, on read |

Only facts nothing else can produce are written down: **payments, measurements,
check-ins, and what has already been emailed.**

The trade is that some screens do a little more work to load. The gain is that
two numbers in this system can never disagree — which is worth far more in a
business where the numbers are money.

---

## Things that quietly protect you

Small decisions that only show their value on a bad day.

**Two people, one slot.** If two members tap "book" on the same PT slot at the
same instant, exactly one gets it. The database itself refuses the second, so it
holds even if two servers are running. Same for check-ins: one open visit per
person, no matter how many times the button is tapped.

**Invoice numbers can't skip.** GST invoices must be numbered without gaps
within a financial year. The system takes a lock while issuing one, so a burst
of simultaneous checkouts still produces `1, 2, 3` and never `1, 3`.

**The browser never decides the price.** Online checkout is priced on the
server. The payment provider's callback can only confirm *that* order was paid —
it cannot say what it cost. A doubled callback is harmless.

**The QR code expires in a minute.** It's a signed code over a one-minute
window, so a screenshot passed around the car park stops working almost
immediately, and there's no table of used codes to clean up.

**Deleting asks first.** Every destructive action names what is actually lost —
"5 members will lose this badge", not "Are you sure?".

**Failed imports don't lose the file.** Import is two stages: preview shows what
it detected and lets you correct it column by column; only then does it commit.
Bad rows are skipped and listed individually rather than failing the lot.
Re-running the same file updates rows rather than duplicating them.

**Colour means one thing.** Green is only ever good news, red only ever
destructive or bad, amber "look at this", blue "just a number". A button that
completes something is never green just because it's the happy path.

---

## Moving in from other software

Admin → **Import Data** takes a CSV or Excel export from FitnessForce, GymForce,
Torzil, GymMaster or similar, for members, billing or trainers.

Only one of those vendors publishes its export format, so the importer doesn't
hardcode one layout per vendor. It reads your header row and matches it against
a list of known names — `First Name`, `first_name`, `member_firstname` and
`FIRSTNAME` all land in the same place. It accepts about 13 date formats, copes
with currency symbols and thousands separators, and translates status words
(`Frozen` → paused, `Cancelled` → expired, `NEFT` → bank transfer).

Because that detection is a *guess*, nothing is written until you have seen it
and approved it.

Imported accounts are created without a working password, so nobody can log into
them until a password is set.

---

## How it's built

You don't need this to use the system, but here it is.

- **Backend**: Django (Python) with Django REST Framework. One module per
  feature area — 28 of them.
- **Frontend**: React with TypeScript, built by Vite. Some 3D via React Three
  Fiber.
- **Database**: PostgreSQL in production, SQLite for local development.
- **Login**: short-lived tokens held in memory, with a longer-lived refresh
  token in a secure cookie the JavaScript can't read.
- **Tests**: about 1,000 of them, including tests that fire genuinely
  simultaneous requests to prove the "only one wins" rules actually hold.

### Everything paid for is optional

Online payment, WhatsApp, email and the AI assistant each switch on only
when their credentials are set. Without them the feature **hides itself and says
why**, rather than appearing and then failing when someone tries to use it.

---

## What it costs to run

It is designed to run on free tiers end to end:

| Piece | Service | Cost |
|---|---|---|
| Database | Neon | Free tier |
| Images and uploads | Cloudinary | Free tier |
| Backend | Render | Free tier |
| Frontend | Vercel | Free tier |
| Error reporting | Sentry | Free tier |

One caveat worth knowing: Render's free servers go to sleep after 15 minutes
idle. The app shows "waking up the server…" on a cold start rather than an
unexplained spinner.

Costs only start when you add optional services — a payment gateway takes its
percentage, WhatsApp Business charges per conversation, and the email provider
has a free allowance before it charges.

---

## Getting it running

The short version, for someone who has the code and a terminal:

```bash
cd backend && python -m venv venv && venv\Scripts\activate && pip install -r requirements.txt && python manage.py migrate && python manage.py runserver
```

```bash
cd frontend && npm install && npm run dev
```

Then open `http://localhost:5173`.

To fill it with a realistic gym to click around — an admin, two trainers and
five members in different states (active, lapsed, paused, brand new):

```bash
python manage.py seed_demo
```

It prints the logins when it finishes. `seed_demo --wipe` removes it again.

Full setup, environment variables and deployment steps are in
[README.md](README.md).

---

## Questions people ask

**Can a member see another member's data?**
No. Members reach their own records and shared gym content — announcements, the
timetable, instructors, the gallery. That's it.

**Can a trainer see the whole gym?**
No — only the members assigned to them.

**What happens when a membership expires?**
The member is emailed at 7, 3 and 1 days before, and once the day after. After
expiry the door won't open, and the member portal shows renewal instead. Nothing
is deleted; renewing picks up where they left off.

**Can someone be paused rather than expired?**
Yes. A manual pause is respected — the nightly job that expires lapsed members
skips anyone deliberately paused.

**What if the internet goes down at the front desk?**
Check-in needs the server. The biometric terminals talk to it directly with
their own key rather than through a browser session, so a laptop problem doesn't
stop the door.

**Can two branches share members?**
They share *people*, not memberships. One account, separate memberships. A
member of Andheri visiting Bandra is a day-pass guest there unless they hold a
membership at both.

**Is the leaderboard compulsory?**
No. It's opt-in, and opting out still lets you see your own standing privately
without appearing to anyone else.

**Who owns the data?**
Each gym's data belongs to that gym and is isolated from every other gym.
Export to Excel is available from the admin dashboard.

---

*This document describes what the system does. For setup, environment variables,
deployment and the reasoning behind specific technical decisions, see
[README.md](README.md).*
