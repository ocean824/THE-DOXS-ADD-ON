# D.O.X Workspace API v1

The executable, field-level OpenAPI contract is available to signed-in users at `/api/openapi.json`; interactive documentation is `/api/docs`. Owners can download the JSON in Connections. Pydantic schemas define types, enum values, required fields and limits for every business request and JSON response. `POST /api/ai/chat` and `GET /api/events` stream SSE; document downloads return an attachment.

## Authentication

Base URL comes from configuration, never a desktop binary constant. All clients use HTTPS. Browser: POST `/api/auth/login` with `{email,password,client:"web"}`. The API sets `Secure; HttpOnly; SameSite=Lax` cookies; browser JavaScript never receives JWTs. Cookie-authenticated mutation requests must carry the configured application Origin. Desktop: use `client:"desktop"`, store returned access and refresh tokens in Windows secure storage, attach `Authorization: Bearer ...`. Access lasts 15 minutes; refresh session lasts 7 days. POST `/api/auth/refresh` rotates refresh tokens atomically. POST `/api/auth/logout` revokes the current session. Password change/reset revokes every session for that user. `/api/auth/me` always reads the current role from MongoDB. No self-registration.

Password reset accepts an email for lookup, uses only the existing user record's email, a fixed server-owned template and managed email delivery. Tokens are hashed at rest, single-use, valid 30 minutes and never logged. Passwords use bcrypt. Password length: 12-72 characters on creation/change (maximum 72 UTF-8 bytes). Login throttled by account; reset throttled by account.

## Authorization matrix

| Resource/action | Owner | Team member | Client |
|---|---|---|---|
| Contacts | all, create/update/delete | assigned, create/update only | denied |
| Pipeline stages | read, create/update | read | read |
| Transactions | all, create/update/access grants | assigned, create/update; no grants | linked, read-only |
| Checklist tasks | all, create/update | assigned transaction, create/update | denied |
| Documents | all, upload/download/remove | assigned transaction, upload/download | linked and `visibility=client`, download only |
| Reviews & comments | all; decisions; cannot decide own submission | assigned transaction, submit/comment | denied |
| Threads/messages | all, create/send | participating, create/send with validated relationships | participating, read/acknowledge only |
| Notifications/preferences | own | own | own |
| AI | unlimited; all logs | daily configured limit; scoped context | daily limit, scoped public context; no internal checklist template |
| Users/settings/service keys | owner only | denied | denied |

Missing/expired/revoked credentials: 401. Authenticated but forbidden action: 403. A record outside the principal's visible set: 404. Conflict: 409. Field validation: 422. Rate/AI usage limit: 429. Unavailable integration: 503. Unknown fields in request models are rejected. Object IDs are UUID strings, BSON `_id` never returned. Timestamps UTC ISO8601; business dates YYYY-MM-DD.

## API groups

- Auth: login, me, refresh, logout, forgot-password, reset-password, change-password.
- Contacts: GET/POST `/api/contacts`; GET/PUT/DELETE `/api/contacts/{id}`. Contact deletion conflicts if a transaction references it.
- Stages: GET/POST `/api/pipeline-stages`; PATCH `/api/pipeline-stages/{id}`. Renaming keeps stable stage IDs.
- Transactions: GET/POST `/api/transactions`; GET/PATCH `/api/transactions/{id}`. Create auto-populates eight checklist tasks. Owner-only assignment changes; linked contact IDs validated for visibility.
- Tasks: GET `/api/tasks`; GET/POST `/api/transactions/{id}/tasks`; PATCH `/api/tasks/{id}`.
- Documents: GET/POST `/api/transactions/{id}/documents`; GET `/api/documents/{id}/download`; DELETE `/api/documents/{id}`. Upload multipart `file`, `category`, `visibility`. Max20MB; allow-list PDF/DOCX/PNG/JPG/TXT, signature checking for binary types. Private object storage accessible only through authorized backend; soft-delete removes access.
- Reviews: GET `/api/reviews`; POST `/api/transactions/{id}/reviews`; GET `/api/reviews/{id}`; POST `/api/reviews/{id}/decision`; GET/POST `/api/reviews/{id}/comments`. Pending-only compare-and-set decisions; notes required for rejection/revision. Revised submissions create a fresh review.
- Messaging: GET/POST `/api/threads`; GET/POST `/api/threads/{id}/messages`; POST `/api/threads/{id}/read`. Read receipts in `read_by`; explicit `mention_ids` must belong to thread participants. Live updates via `/api/events`.
- Notifications: GET `/api/notifications`; PATCH `/api/notifications/{id}/read`; PATCH `/api/notification-preferences`. Due-task entries are computed from current task state with IDs `task-{task_id}`, not stored or markable as read.
- Users: owner GET/POST `/api/users`; PATCH `/api/users/{id}`. Account permission changes revoke sessions. `/api/directory` supplies visible people; no password hashes.
- Configuration: owner GET/PUT `/api/settings`. AI limits, opt-in autonomy and maximum value.
- AI: POST `/api/ai/chat`; GET `/api/ai/usage`; owner GET `/api/ai/logs`. Transaction-specific templates only; no agent tools or autonomous execution. Denied prompt patterns logged; model receives no server secrets and no unrelated records. Limits use atomic UTC daily counters. Failed provider requests are refunded from message count. AI output is a draft, not legal advice or proof of compliance.
- Activity: GET `/api/activity`, scoped before retrieval.
- Integrations: owner GET `/api/integrations/status`, GET `/api/integrations/prompts/{hermes|dox|traycer}`, POST `/api/integrations/keys`, DELETE `/api/integrations/keys/{service}`, POST `/api/integrations/reviews/{id}/confirmation`.
- Service-only: GET `/api/integrations/hermes/queue`; POST `/api/integrations/hermes/decisions`; POST `/api/integrations/dox/contacts`. Service keys are hashed at rest, rotatable, narrow-scope; user bearer tokens cannot authenticate as service keys. Mobile confirmations are owner-authenticated, decision/note-bound, expiring and single-use. Autonomous approvals independently require configured cap, all tasks completed and all document categories present. Decision receipts track authority evidence and idempotency.

## Event streams

`GET /api/events` sends `event: ready`, `event: change` with JSON `{timestamp}`, and `event: expired` when session expires/revokes. Heartbeats maintain the connection. On change, refetch authorized resources; event payload itself carries no record contents. On expired, refresh/reconnect. Desktop can alternatively poll `/api/notifications` every60 seconds. The connection checks for authorized changes every2seconds; this is an open request, not a scheduled background job.

`POST /api/ai/chat` returns data frames with JSON `{type:"delta",text}`, `{type:"done",log_id}`, or `{type:"error",message}`. SSE boundaries can span network chunks; buffer until `\n\n`. Proxy buffering disabled. Logs persist the complete response or interrupted partial result.

## Current operational boundaries

This initial release serves a single organization. List endpoints cap results at500 (stages30, activity40); indexed cursor pagination is a future scaling task. No external Hermes phone runtime, Dox sender or Windows binary is bundled: use the versioned build contracts. No SSO, reverse-sync/outbound webhook dispatcher, e-signature provider, financial payment action, automated malware scanner, scheduled reminder emails, or billing checkout has been integrated. Required document matching is category-based, not semantic/legal review. Backup/restore, security review, concurrency hardening, data-retention policy and live third-party acceptance testing must be completed before treating this as a certified production system.
## Added: knowledge vault, calendar, client uploads

- Knowledge: GET `/api/knowledge/items`, GET `/api/knowledge/access`, GET `/api/knowledge/items/{id}` (all roles; filtered to permitted items). Owner: POST `/api/knowledge/sync` (JSON, text or base64 files; .md .txt .csv .json .yaml .docx .xlsx .pptx .pdf; server-side text extraction), POST `/api/knowledge/upload` (multipart), PATCH/DELETE `/api/knowledge/items/{id}`, GET/POST `/api/knowledge/grants`, DELETE `/api/knowledge/grants/{id}`. Permission rule: owner unrestricted; project items need active grant ∧ grant covers item.project_type ∧ user assigned/linked to item.transaction_id; shared items need a shared grant; optional path_prefix narrows any grant; grants may expire.
- Hermes knowledge contracts: owner POST `/api/integrations/knowledge/confirmation`; service POST `/api/integrations/hermes/knowledge/grants` (scope `knowledge:grant`; owner-confirmed token or Settings knowledge_rules). Settings gained `knowledge_rules {enabled,roles,scopes,project_types,path_prefixes}`.
- Owner GET `/api/integrations/cli` downloads the dox-vault Python CLI (Obsidian folder sync and CLI for Microsoft 365 SharePoint/OneDrive sync).
- AI: template `knowledge` with optional transaction; `done` frame includes `sources`. Logs store `knowledge_ids`.
- Calendar: GET/POST `/api/meetings`, PATCH `/api/meetings/{id}`, POST `/api/meetings/{id}/respond`, DELETE `/api/meetings/{id}`.
- Documents: clients may upload to linked transactions (`client_submitted`, forced `visibility=client`, staff notified). Documents now include `uploaded_by_name`.
