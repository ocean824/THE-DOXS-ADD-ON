# Auth and role mapping: thedoxs.com accounts → D.O.X Workspace

The workspace never trusts the client for roles. Everything flows through one dependency, `core.current_user()`, which returns a dict with at least:

```python
{'id': '<stable user id>', 'name': 'Display Name', 'email': 'x@y', 'role': 'OWNER'|'TEAM_MEMBER'|'CLIENT', 'active': True,
 'notification_preferences': {'messages':True,'tasks':True,'mentions':True}, '_session_id': '<opaque>', '_expires': <unix ts>}
```

Everything downstream (`require()`, `Repo`, `permitted_filter`, activity audiences, thread/meeting participants) keys on `id` and `role` only.

## Role mapping

| thedoxs.com account | Workspace role | Gets |
|---|---|---|
| Site admin / owner | `OWNER` | everything: all records, users, policies, service keys, AI logs, review decisions, knowledge vault admin, grants |
| Staff / coordinator / agent | `TEAM_MEMBER` | assigned contacts/transactions/threads, checklists, uploads, review submissions, AI with daily limit, vault items they are granted |
| Customer / buyer / seller portal user | `CLIENT` | read-only linked transactions, client-visible documents (+ own submissions), participating threads (read), calendar on linked transactions, AI with client limit, vault items they are granted |
| Anyone else / logged-out | — | 401 |

If the site has finer roles (e.g. `editor`, `marketing`), map anything that should not see client files to no workspace access (return 401/403 from `current_user`), not to `CLIENT`.

## Implementation (replace `core.current_user`)

```python
# core.py — replace the JWT/cookie block with the site's session lookup
ROLE_MAP = {'admin': 'OWNER', 'owner': 'OWNER', 'staff': 'TEAM_MEMBER', 'agent': 'TEAM_MEMBER', 'customer': 'CLIENT'}

async def current_user(request: Request, credentials=Depends(bearer)):
    site_user = await site_auth.resolve(request, credentials)      # the main site's existing dependency / helper
    if not site_user or not site_user.get('active', True): raise HTTPException(401, 'Please sign in')
    role = ROLE_MAP.get(site_user['role'])
    if not role: raise HTTPException(403, 'Workspace access is not enabled for this account')
    profile = await db.users.find_one({'id': site_user['id']}, {'_id':0,'password_hash':0}) or {}
    user = {'id': site_user['id'], 'name': site_user.get('name') or site_user['email'], 'email': site_user['email'],
            'role': role, 'active': True,
            'notification_preferences': profile.get('notification_preferences', {'messages':True,'tasks':True,'mentions':True}),
            '_session_id': site_user.get('session_id','site'), '_expires': site_user.get('exp', 2**31-1)}
    if not credentials and request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('origin') != ORIGIN:
        raise HTTPException(403, 'Invalid request origin')
    await db.users.update_one({'id': user['id']}, {'$set': {k:user[k] for k in ('name','email','role','active')}}, upsert=True)
    return user
```

Notes:
- The upsert keeps `db.users` populated so `/api/directory`, participant validation, task assignees, grants and notifications keep working (they look people up by `id` in `users`). Role is written from the site every request, so changing a role on the site takes effect immediately.
- `/api/users` (owner admin: create/deactivate/role change) should be removed or re-pointed at the site's user management; `Settings.js` "Team & access" tab can then link to the site's admin page.
- `/api/notification-preferences` keeps working (writes to `db.users`).
- Delete `auth_routes.py` login/refresh/forgot/reset/change-password, or keep them disabled. Keep an endpoint that returns the mapped user (`GET /api/auth/me` shape = `UserOut`) so `frontend/src/lib/auth.js` needs no change beyond the login redirect.
- Desktop/CLI clients (Traycer, dox-vault) currently log in with `client:"desktop"` to get bearer tokens. After the merge they need the site's token endpoint; expose one bearer-token login for owners/staff (short access + rotating refresh) or an API-key flow, and update `cli/dox_vault.py: login()` and `docs/TRAYCER-v1.md` accordingly.
- Session revocation: `/api/events` SSE checks `_session_id` every 10 s and `_expires`; return the site's session id/expiry so revocations still end streams.

## Frontend (`src/lib/auth.js`)

- Replace `login()` with a redirect to the site's login page (`/login?next=/workspace`) and `logout()` with the site's logout call.
- `AuthProvider` still fetches `GET /api/auth/me` on load; on 401 it should redirect to the site login instead of rendering the workspace `Login.js`. `Login.js` and `/reset-password` become unnecessary.
- `Protected` in `App.js` already renders the shell only when `user` exists.

## Data migration

- Existing workspace data (if any was created in the preview): export `transactions, contacts, tasks, documents, reviews, review_comments, threads, messages, notifications, activities, pipeline_stages, settings, knowledge_items, knowledge_grants, meetings, service_keys` with `mongodump`/`mongoexport`, and rewrite `assigned_ids/client_ids/participant_ids/created_by/uploaded_by/organizer_id/user_id/actor_id` from workspace user ids to site user ids (`users.email` is the join key). Documents reference `storage_path` in the Emergent object store; the new deployment reaches the same bucket when it uses the same `EMERGENT_LLM_KEY`.
- Fresh start: run `seed()` with the sample block removed; it only creates indexes, pipeline stages and default settings.
