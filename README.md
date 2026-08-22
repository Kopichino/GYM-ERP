# IRONCORE -- Gym ERP

A free-to-run gym platform: members self-service check in/out, log workouts, track
progress, and browse announcements/instructors/schedule/gallery. Admins get a
dashboard to manage content and export the member list to Excel.

Stack: Django REST Framework (backend) + React/Vite/TypeScript with React Three
Fiber (frontend). No AI/LLM APIs anywhere. Designed to run entirely on free
hosting tiers -- see `Deployment` below.

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

### Frontend

```
cd frontend
npm install
copy .env.example .env         # points at http://localhost:8000/api by default
npm run dev
```

App runs at `http://127.0.0.1:5173/`.

### First-time data

The workout catalog (`Exercise`) and instructor/schedule/announcement content
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
| `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` | backend | Must list the deployed frontend's exact origin |
| `CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET` | backend | Required in production for media uploads |
| `VITE_API_URL` | frontend | Backend API base URL |

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

## Notes

- Auth is JWT (SimpleJWT): short-lived access token held in memory on the
  frontend, refresh token as an httpOnly cookie. Refresh/logout blacklist old
  tokens.
- `is_staff` is the only role flag -- there is no separate admin/instructor
  role system. Promote a user to staff via Django admin or `createsuperuser`.
- The check-in/out flow enforces "one open check-in per user" at the database
  level (a partial unique constraint), not just in application code.
