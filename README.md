**Project**
- **Name:** DAM Platform
- **Description:** Enterprise-focused Digital Asset Management (DAM) / Content Management platform for images, video, documents and creative assets. Provides metadata, tagging, versioning, role-based access, audit trails and an extensible foundation for AI features (OCR, object/face recognition, auto-tagging, duplicate detection).

**Status**
- **Current:** Backend scaffold with models, API routes and basic auth; Next.js frontend scaffold.
- **Goal:** Working end-to-end MVP: authenticated upload → persistent storage → searchable library with metadata and audit logging.

**Quick Links**
- **Backend entry:** [app/main.py](app/main.py)
- **Database setup:** [app/database.py](app/database.py)
- **Models:** [app/models/__init__.py](app/models/__init__.py)
- **Requirements:** [requirements.txt](requirements.txt)
- **Frontend starter:** [frontend/app/page.tsx](frontend/app/page.tsx)

**Prerequisites**
- Python 3.10+ and virtualenv (or equivalent)
- Node.js 18+ and npm/yarn for frontend
- PostgreSQL (recommended for production) or SQLite for local dev

**Environment variables (.env)**
- **DATABASE_URL:** database connection (e.g., `postgresql://user:pass@localhost:5432/damdb`)
- **SECRET_KEY:** JWT secret for auth
- Optional: storage credentials (S3/Azure/Blob) when using remote storage

**Local setup — Backend**
- Create and activate virtual environment:
```bash
python -m venv venv
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate
```
- Install dependencies:
```bash
pip install -r requirements.txt
```
- Create `.env` with `DATABASE_URL` and `SECRET_KEY`. For quick local testing you can use SQLite:
```text
DATABASE_URL=sqlite:///./dev.db
SECRET_KEY=replace-this-in-prod
```
- Initialize DB/tables (the app auto-creates tables on startup via SQLAlchemy). Start the API:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- Open API docs: http://localhost:8000/docs

**Local setup — Frontend**
- From `frontend`:
```bash
cd frontend
npm install
npm run dev
```
- Default dev URL: http://localhost:3000 (update CORS in `app/main.py` if needed)

**Core developer flows to test manually (MVP)**
- Sign up: `POST /auth/signup` → returns JWT token
- Login: `POST /auth/login` → get token for Authorization Bearer header
- Upload asset (MVP currently stores metadata; implement storage in `app/api/assets.py`): `POST /assets/` (requires authenticated user)
- List assets: `GET /assets/` (supports `skip`, `limit`, `asset_type`, `status`, `tag`)
- Get asset detail: `GET /assets/{id}`
- Tagging: `POST /assets/{id}/tags/{tag_id}` and `DELETE /assets/{id}/tags/{tag_id}`
- Roles and audit endpoints: `/roles`, `/users`, `/audit-logs`








