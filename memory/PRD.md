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

## Prioritized backlog and next tasks

P0 for external rollout: owner changes temporary password; connect and acceptance-test actual Hermes phone runtime, Dox sender and separately built Traycer; configure actual live application origin and service secrets; full security/operational review before sensitive real client records.

P1: backed-up/restorable MongoDB and private document retention, document malware scanning, cursor pagination beyond initial list caps, stronger distributed rate limits/auth throttling and race handling, webhook/outbox dispatcher with signed delivery retries if reverse sync is needed, transactional uniqueness for simultaneous review submissions, completed/archived transaction lifecycle.

P2: appointment/calendar integration, deeper compliance/template builder, e-signature provider, performance reporting, enterprise SSO, billing/payment controls once business rules/provider chosen. No Windows installer, external phone service, actual Dox code changes, SSO or outbound synchronization were built in this repository.

## Verification record

Testing agent report and resulting fixes will be recorded here after initial end-to-end verification. Tests must cover OWNER, two independently assigned TEAM_MEMBER accounts, linked/unlinked CLIENT, anonymous, Hermes and Dox service scopes; actual storage, email accepted test recipient, and GPT-5.2 streaming; mobile overflow and main user flows.