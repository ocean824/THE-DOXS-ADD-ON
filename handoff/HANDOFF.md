# D.O.X Workspace → thedoxs.com handoff package

Purpose: fold the complete transaction-coordination workspace (CRM, checklists, documents, reviews, messaging, calendar, knowledge vault, AI gateway, Hermes/Dox/Traycer contracts) into the existing thedoxs.com Emergent app as `thedoxs.com/workspace`, using the main site's accounts for admin/team/client logins.

Package contents (this folder):

| File | Use |
|---|---|
| `HANDOFF.md` | This guide: architecture, inventory, data model, merge steps, caveats |
| `AUTH-ROLE-MAPPING.md` | How to swap this app's auth for thedoxs.com auth and map roles |
| `MERGE-PROMPT.md` | Copy-paste prompt for the Emergent agent working on thedoxs.com |
| `env.example` | Every environment variable the workspace needs |
| `openapi.json` | Full field-level API contract (regenerate with `GET /api/openapi.json`) |
| `dox-workspace-handoff.zip` | Source bundle: backend, frontend/src, docs, cli, tests (no node_modules/.env/build) |
| `../docs/API.md`, `HERMES-v1.md`, `DOX-v1.md`, `TRAYCER-v1.md` | External build contracts (unchanged by the merge) |

Also push this repository to GitHub with the chat "Save to GitHub" action so the thedoxs.com agent can read the live source.

---

## 1. Stack and shape

- Backend: FastAPI (`/app/backend`), Motor/MongoDB, Pydantic v2 strict models (`extra='forbid'`), UUID string ids (never BSON `_id` in responses), `/api` prefix on every route. Single `server.py` registers routers; each domain is one file (≈100 lines, dense style).
- Frontend: React 19 + react-router 7 + CRA/craco, shadcn/ui primitives in `src/components/ui`, one global stylesheet `src/App.css` (institutional dark theme: Plus Jakarta Sans / Cormorant Garamond / JetBrains Mono; CSS variables `--bg --surface --elevated --line --text --muted --gold --green --red --blue`). Data fetching via `src/lib/useData.js` (axios + global `crm-refresh` event); live updates via SSE `GET /api/events`.
- Managed services (all through the Emergent integrations proxy, keys server-side only): OpenAI GPT-5.2 via `EMERGENT_LLM_KEY` (emergentintegrations `LlmChat`), Resend email via `EMERGENT_EMAIL_KEY` (password reset), private object storage via the same `EMERGENT_LLM_KEY` (`/objstore` API).

## 2. Backend inventory

| File | Responsibility |
|---|---|
| `core.py` | Mongo client, `PERMS` matrix, `current_user` (cookie or bearer JWT, DB role re-read, origin check), `require(action)`, `Repo` (mandatory relationship scoping for every read/write), `activity()` feed+events, `settings()` |
| `schemas.py` | All request/response models (contacts, transactions, tasks, documents, reviews, threads, messages, AI, settings/knowledge rules, knowledge items/grants, Hermes grants, meetings) |
| `auth_routes.py` | login/refresh/logout/me/forgot/reset/change-password, bcrypt, rotating refresh sessions, throttling. **Replaced during merge** (see AUTH-ROLE-MAPPING.md) |
| `crm_routes.py` | contacts, pipeline stages, transactions (+8 auto tasks), tasks, activity, users/directory (owner admin), notification prefs, settings |
| `document_routes.py` | private uploads (20 MB, allow-list + signature check), download proxy, soft delete; client submissions |
| `review_routes.py` | review submit/decide/comments, compliance (tasks + required document categories) |
| `message_routes.py` | threads, messages, read receipts, mentions, notifications, SSE `/api/events` |
| `ai_routes.py` | GPT-5.2 streaming gateway, daily atomic counters, prompt-injection block list, templates incl. `knowledge`, owner logs |
| `knowledge_routes.py` | vault items, sync/upload, grants, `permitted_filter` (3-condition rule), Hermes confirmation + grant endpoints |
| `knowledge_extract.py` | text extraction for md/txt/csv/json/yaml/docx/xlsx/pptx/pdf |
| `calendar_routes.py` | meetings (propose/respond/reschedule/cancel), participant scoping |
| `integration_routes.py` | service keys (hashed), status, prompts, CLI download, owner confirmations, Hermes queue/decisions, Dox referral intake |
| `email_service.py` | Resend send with structural guardrails (fixed template) |
| `seed.py` | indexes (incl. text index on knowledge), default settings, first owner + sample workspace |
| `tests/` | `test_external_api_core.py` (13), `test_iteration2_features.py` (21) — run with `pytest` against `REACT_APP_BACKEND_URL` |

Python extras beyond the Emergent base image: `emergentintegrations`, `python-docx`, `openpyxl`, `python-pptx`, `pypdf`, `httpx`, `bcrypt`, `PyJWT`, `motor` (all pinned in `requirements.txt`).

## 3. Frontend inventory (`frontend/src`)

| Path | Responsibility |
|---|---|
| `App.js` | Routes: `/login`, `/reset-password`, protected shell with `/`, `/transactions[/:id]`, `/calendar`, `/contacts`, `/tasks`, `/reviews`, `/messages`, `/assistant`, `/knowledge`, `/settings`, `/integrations` (owner). Role guards `Staff`, `Owner` |
| `components/Shell.js` | Sidebar/topbar, notifications, global search, SSE connection, role-filtered nav |
| `components/Common.js` | `Btn Field Modal Badge Avatar PageHeader SectionTitle Empty Loading ErrorState` |
| `components/Pipeline.js`, `TransactionCard.js`, `TransactionForm.js` | board + create form |
| `components/KnowledgePanels.js` | vault upload (file/Obsidian folder pickers), items table, grants, CLI sync tools |
| `pages/*.js` | Dashboard, Transactions, TransactionDetail, Contacts, Tasks, Reviews, Messages, Calendar, Assistant, Knowledge, Settings, Integrations, Login |
| `lib/api.js` | axios instance (`${REACT_APP_BACKEND_URL}/api`, cookies, 401→refresh interceptor), helpers |
| `lib/auth.js` | `AuthProvider` / `useAuth` (user, login, logout) — **adapter point for thedoxs.com auth** |
| `lib/useData.js` | fetch hook with global refresh |
| `App.css`, `index.css` | complete theme; fonts imported in `index.css` |

Every interactive element carries a `data-testid`.

## 4. Data model (MongoDB collections)

`users` (id, name, email, role OWNER|TEAM_MEMBER|CLIENT, active, password_hash, notification_preferences) · `sessions` · `password_resets` · `rate_limits` · `contacts` (assigned_ids) · `pipeline_stages` · `transactions` (assigned_ids, client_ids, buyer_id, seller_id, 3 dates, stage_id, review_status, required_documents, sample) · `tasks` · `documents` (storage_path, visibility internal|client, client_submitted, is_deleted) · `reviews`, `review_comments` · `threads` (participant_ids), `messages` (read_by, mention_ids) · `notifications` · `activities`, `events` (SSE change feed) · `ai_usage_logs`, `ai_daily_usage` · `settings` (id `workspace`: limits, autonomy, `knowledge_rules`) · `service_keys` (sha256 hash, scopes) · `integration_receipts` (idempotency) · `approval_confirmations` (TTL) · `authorization_logs` · `knowledge_items` (path unique, text index) · `knowledge_grants` · `meetings`.

Visibility rules live in `core.Repo.scope()`; the knowledge rule lives in `knowledge_routes.permitted_filter()`. Keep both when merging — they are the security boundary.

## 5. Merge steps (same codebase, mounted at `/workspace`)

1. **Copy backend files** from the bundle into the main backend. Register routers in the main `server.py`; keep the `/api` prefix. If the main site already has `/api/users` or `/api/settings`, rename the workspace ones to `/api/workspace/users` and `/api/workspace/settings` (two frontend paths: `Settings.js`, `KnowledgePanels.js`, `Messages.js`/`TransactionForm.js` use `/directory`, not `/users`).
2. **Swap auth** per `AUTH-ROLE-MAPPING.md`: implement `current_user()` in `core.py` on top of the main site's session/JWT and map the site's roles → `OWNER | TEAM_MEMBER | CLIENT`. Delete or disable `auth_routes.py` login/reset endpoints (keep `/api/auth/me` semantics or point the frontend at the site's equivalent). Remove `INITIAL_OWNER_*` seeding of a password; `seed.py` should instead promote the site admin account(s) to `OWNER` on startup.
3. **Database**: reuse the main site's `MONGO_URL`/`DB_NAME`. Collections above are new except `users` — if the site already has `users`, either (a) store workspace fields (`role`, `active`, `notification_preferences`) on the same documents, or (b) keep a `workspace_profiles` collection keyed by the site user id and have `current_user()` join it. Option (a) is simpler; `Repo` only needs `user['id']` and `user['role']`.
4. **Frontend**: copy `src/pages`, `src/components` (except `ui/` if the site already has shadcn — reuse theirs), `src/lib`, `App.css`, fonts import. Mount the workspace router at `/workspace`: either `<BrowserRouter basename="/workspace">` for a separate entry, or nest `<Route path="/workspace/*" element={<WorkspaceApp/>}>` and change the absolute paths in `Shell.js` `mainNav`, `App.js` routes, and `navigate('/...')` calls to be relative (or prefix with `/workspace`). Grep for `navigate(` and `to="/`; all links live in `Shell.js`, `Dashboard.js`, `TransactionDetail.js`, `Messages.js`, `Calendar.js`, `Knowledge.js`, `Assistant.js`, `Integrations.js`, and notification `link` values produced by the backend (`/messages?thread=`, `/transactions/{id}`, `/calendar?meeting=`, `/knowledge`) — prefix those four backend link builders with `/workspace`.
5. **Theme**: `App.css` is self-contained (class-based, no Tailwind dependency except shadcn primitives). If the site's global CSS sets body fonts/colors, scope the workspace by wrapping `<div className="workspace">` (already the root class) and leaving site styles outside.
6. **Environment**: add the variables in `env.example` that the site does not already have (`EMERGENT_LLM_KEY`, `EMERGENT_EMAIL_KEY`, `EMAIL_FROM_NAME`, `EMAIL_REPLY_TO`, `APP_ORIGIN=https://thedoxs.com`). `APP_ORIGIN` must equal the browser origin — it is used for CSRF origin checks on cookie-authenticated mutations and for reset-email links.
7. **Dependencies**: backend `pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/` plus `python-docx openpyxl python-pptx pypdf`; frontend already standard (`axios lucide-react sonner react-router-dom`).
8. **Integrations**: Hermes/Dox service keys continue to work unchanged (`/api/integrations/*`); the Dox referral endpoint `POST /api/integrations/dox/contacts` can now be called in-process from the site's own lead form instead of over HTTP. The `dox-vault` CLI only needs the new base URL (`python dox_vault.py login --base-url https://thedoxs.com`).
9. **Verify** with the two pytest files (set `REACT_APP_BACKEND_URL`, owner/team/client credentials) and the UI flows listed in `/app/test_reports/iteration_2.json`.

## 6. Caveats carried over

- Single organization; no tenancy. List endpoints cap at 500.
- Knowledge retrieval is Mongo text search (keyword), not embeddings.
- Hydration-warning noise in Emergent preview comes from the dev-only visual-edits plugin, not app code.
- Hermes phone runtime, Dox website changes, Traycer binary are external builds; contracts in `docs/`.
- Sample properties/contacts are seeded only when no OWNER exists; skip `seed()` sample block when merging into a live database.
