# D.O.X Workspace — Product requirements and delivery record

## Original problem statement

Build a production-ready full-stack CRM web application for a real estate transaction coordination team. Model the design and workflows on Knock CRM (knockcrm.com): clean, card-based pipelines, left sidebar navigation, modern dashboard with activity feed.

USERS & AUTHENTICATION: Email/password login with bcrypt, password reset via email, JWT secure sessions and HTTPS. OWNER full access, manages users, sees all transactions, LLM usage logs, controls billing/config. TEAM MEMBER assigned contacts, transactions and threads; cannot delete contacts, manage users or see LLM logs. CLIENT view-only own transactions, documents and message threads; cannot see team internals. Enforce server-side permissions on every endpoint.

CORE: Dashboard contacts buyers/sellers/partners, tags/notes/communication history, customizable Lead → Appointment → Contract → Closing pipeline, role-filtered activity feed. Transactions link property/buyer/seller/agent/dates; checklist auto-populates with title, inspection, EMD and payoff tasks; due dates, assignees, completion, overdue highlighting; role-visible document uploads. Review queue with owner side-by-side checklist, missing-documents and comments, approve/reject/revision, full audit trail. Threaded messaging with client/team/owner, real-time changes, read receipts, mentions, notification preferences; attach to contacts/transactions.

AI: server proxy /api/ai/chat, server-only external LLM key, owner unlimited/team N/client M daily messages, usage tracking, task templates client-email/status/closing-recap/missing-checklist, log prompts/responses owner-only, block credential/system/other-user-data extraction attempts.

TECHNICAL: Full source to GitHub; REST and precise OpenAPI request/response schemas consumed by separate Windows desktop app. Collections: users,contacts,transactions,tasks,documents,reviews,review_comments,threads,messages,ai_usage_logs. Theme/color/animation/tone match www.thedoxs.com and www.losslessholdings.com. Communicate with Hermes agent and Dox website; return copy-paste prompts for Dox/Hermes/Traycer. Hermes should relay approvals through its phone-agent connection to Traycer and website team.

Context supplied: Traycer is a separately built Electron/Tauri Windows11 client with Windows Credential Manager tokens, dashboard/tasks/transactions/documents/messages/AI panel, OS notifications, offline indicator, auto-updates/installer and base URL settings. It must not duplicate backend business logic or hold LLM keys. Hermes is the architect/approval bridge maintaining versioned standalone build prompts for website, gateway and desktop. CRM API is single source of truth; all endpoints authenticated and role checked.

## Explicit choices / changes

- Hermes API does not exist yet: provide connection contracts and complete prompts rather than fabricate connectivity.
- Working first AI provider: OpenAI GPT-5.2 via Emergent universal key.
- Both explicit owner-confirmed mobile approval and optional autonomous approval under owner-configured rules. Default autonomy OFF; server checks value cap, all tasks complete, all required documents present; rejected/revised requires human confirmation.
- Managed Resend for password resets; generated initial owner password.
- **Latest owner email instruction: xcyclone8@outlook.com**, replacing earlier ocean824@gmail.com. Initial owner display name Ocean.

## Personas

Owner/operations lead: oversight, approvals, access/config, ecosystem controls. Coordinator/team member: assigned contacts, deadlines, checklists, files and conversations. Client: read-only own closing status/shared files/messages. Hermes service: approval queue + policy-checked decisions only. Dox service: referral/contact ingestion only. Traycer: user-authenticated desktop client.

## Architecture decisions

Single shared organization, RBAC plus record relationships, no invented tenancy. React19/router, shadcn components, custom dark institutional CSS, Plus Jakarta Sans/Cormorant Garamond/JetBrains Mono, property photography. FastAPI modular routers, strict Pydantic schemas, Motor/MongoDB, UUID public IDs and no BSON serialization. Mandatory Repo scopes transaction/contact/task/document/review/thread reads and mutations. Bcrypt passwords, short JWT access sessions, rotating refresh tokens hashed in DB, database role re-read, session revocation; HttpOnly Secure cookies plus origin checks for browser; explicit desktop token mode. Async SSE change feed and streamed AI. Private object storage via backend. Managed Resend fixed reset templates with structural send guardrails. Service keys narrow-scope and hash-only, rotating/revocable. Owner confirmation hash, 5-minute TTL, exact decision/note binding. External systems not fabricated.

## Implemented — 2026-10-12

- Auth/login/logout/refresh/reset/change-password, owner initialization, RBAC and scope filters; owner user create/deactivate/role update, directory, notification preferences.
- Dashboard, visual pipeline drag/drop and list, transaction create/detail/assignment, three milestone dates, eight auto-populated tasks; task completion/due/assignee updates.
- Contacts CRUD (owner-only delete), tags/notes, role-visible list, pipeline add/rename/color.
- Private document upload/download and visibility controls; soft deletion; 20MB/type/signature checks.
- Review submit/approve/reject/revision, self-decision prevention, comments and audit trail, compliance display.
- Threads linked to transactions/contacts, staff send, client view/read receipts, mentions, persisted notifications and computed due-task notices; live SSE invalidation.
- GPT-5.2 streaming gateway, role-specific daily atomic counters, scoped context, blocked-request logging, owner prompt/response log view.
- Owner policies and opt-in autonomous authority; owner-confirmed Hermes token flow; service queue/decision with idempotency and distinct Dox referral endpoint.
- Connections page with real key/status lifecycle, API schema download and versioned copy-paste prompts; README and endpoint guide.
- Clearly labeled sample properties with inactive sample coordinator profiles for initial review.
- Initial frontend production build compiles; external owner login, dashboard, transactions and OpenAPI smoke checks passed. Full test-agent matrix pending at this checkpoint.

## Implemented — 2026-06 (fork 2): knowledge vault, Office/CLI sync, client uploads, calendar

User decisions: knowledge source = local Obsidian vault (owner copies/syncs it in); access to project knowledge needs ALL of approved grant + matching project type + active involvement in the linked transaction, plus a separately approved shared library; grant authority = owner directly, Hermes relaying an explicit owner confirmation, or Hermes under owner-configured knowledge-access rules. "Office CLI" = Microsoft 365 integration via the CLI for Microsoft 365 (Word/Excel/PowerPoint/PDF into the vault). Client uploads land immediately as client-submitted (no review gate). Calendar = built-in (no Google sync).

- Knowledge vault backend (`knowledge_routes.py`, `knowledge_extract.py`): `knowledge_items` (path-unique, text extracted from .md/.txt/.csv/.json/.yaml/.docx/.xlsx/.pptx/.pdf, Mongo text index), `knowledge_grants` (scope shared|project, path_prefix, project_types, expires_at, authority owner|hermes_owner_confirmed|hermes_rule). `permitted_filter()` enforces the three-condition rule; owner unrestricted. Endpoints: items/access/item detail (all roles, filtered), owner sync (JSON text/base64, ≤100 files, ≤25 MB each, deleted_paths), owner multipart upload, patch/delete item, grants CRUD. Hermes: owner `POST /api/integrations/knowledge/confirmation` (single-use 5-min token bound to exact grant body) and service `POST /api/integrations/hermes/knowledge/grants` (scope `knowledge:grant`, idempotent; token path or `settings.knowledge_rules` path). Settings gained `knowledge_rules`.
- AI gateway: template `knowledge` (transaction optional, prompt required) retrieves top permitted items via `$text`, logs `knowledge_ids`, `done` frame carries `sources`; other templates also receive up to 3 permitted items linked to the transaction.
- dox-vault CLI (`/app/cli/dox_vault.py`, served by owner-only `GET /api/integrations/cli`): `login` (desktop tokens in ~/.dox-vault.json), `folder` (Obsidian/local folder, --prune), `m365` (shells out to `m365 file list` / `m365 spo file get --asFile`), `status`.
- Client document uploads: CLIENT may upload to linked transactions; visibility forced `client`, `client_submitted`, `uploaded_by_name`; assigned staff + owners notified; activity visible to client.
- Calendar (`calendar_routes.py`, `/calendar`): meetings scoped by participant (owner all); propose (participants must be owners or assigned/linked people), accept/decline, reschedule resets responses, organizer/owner cancel; month/week grid merged with contract/contingency/closing milestones; upcoming list; notifications link to `/calendar?meeting=`.
- Frontend: Knowledge vault page (owner tabs: items / grants / sync tools with CLI download; non-owner: permitted list + preview), Assistant rewritten SSE handling (AbortController, 60 s idle timeout, explicit done, source chips, `?template=` deep link), Calendar page, nav items for all roles, Settings "Hermes knowledge-access rules" section, Connections "Knowledge sync" card, Messages new-thread submit disabled until a participant is picked.
- Docs appended: `docs/API.md`, `docs/HERMES-v1.md`, `docs/TRAYCER-v1.md`. Test accounts in `/app/memory/test_credentials.md`; token helper `/app/scripts/tokens.sh`.
- Verification: testing agent iteration_2 — backend 34/34 (`tests/test_iteration2_features.py` + core regression), all owner/client UI flows pass. Known non-issue: console "<span> cannot be a child of <option>" comes from the Emergent dev-only visual-edits babel plugin (`data-ve-dynamic` spans), not app code; absent in production builds.

## Handoff package — 2026-06

User decision: fold the workspace into thedoxs.com (same codebase/DB) at `thedoxs.com/workspace`, using the main site's existing auth with a role mapping (site admin → OWNER, staff → TEAM_MEMBER, customers → CLIENT).
- `/app/handoff/`: `HANDOFF.md` (architecture, inventory, data model, 9 merge steps, caveats), `AUTH-ROLE-MAPPING.md` (replacement `current_user()` adapter, role table, frontend auth changes, data migration), `MERGE-PROMPT.md` (copy-paste prompt for the thedoxs.com agent), `env.example`, `openapi.json` (63 paths), `dox-workspace-handoff.zip` (127 files; rebuild with `scripts/build_handoff.sh`).
- Owner-only endpoints `GET /api/integrations/handoff` (zip) and `GET /api/integrations/handoff/guide`; Connections page "Handoff package" section with download + guide modal. Verified: owner 200, team member 403, UI modal renders.

## Prioritized backlog and next tasks

P0 (new): owner runs `dox_vault.py login` + `folder` against the real Obsidian vault; install CLI for Microsoft 365 and run `m365` sync against the actual SharePoint/OneDrive folder; grant first team/client vault access.
P1 (new): semantic (embedding) retrieval instead of Mongo text search once the vault grows; scheduled vault re-sync (cron) from Traycer; meeting reminders (notification 24 h before) and .ics export; Google Calendar sync if later requested; client-upload "received" acknowledgement by staff if the owner wants a review gate.


P0 for external rollout: owner changes temporary password; connect and acceptance-test actual Hermes phone runtime, Dox sender and separately built Traycer; configure actual live application origin and service secrets; full security/operational review before sensitive real client records.

P1: backed-up/restorable MongoDB and private document retention, document malware scanning, cursor pagination beyond initial list caps, stronger distributed rate limits/auth throttling and race handling, webhook/outbox dispatcher with signed delivery retries if reverse sync is needed, transactional uniqueness for simultaneous review submissions, completed/archived transaction lifecycle.

P2: appointment/calendar integration, deeper compliance/template builder, e-signature provider, performance reporting, enterprise SSO, billing/payment controls once business rules/provider chosen. No Windows installer, external phone service, actual Dox code changes, SSO or outbound synchronization were built in this repository.

## Verification record

Testing agent report and resulting fixes will be recorded here after initial end-to-end verification. Tests must cover OWNER, two independently assigned TEAM_MEMBER accounts, linked/unlinked CLIENT, anonymous, Hermes and Dox service scopes; actual storage, email accepted test recipient, and GPT-5.2 streaming; mobile overflow and main user flows.