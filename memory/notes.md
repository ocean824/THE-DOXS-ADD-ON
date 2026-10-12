# Agent notes / learnings

- Access tokens (desktop bearer) expire in 15 min; use `source /app/scripts/tokens.sh` to refresh TOK/TTOK/CTOK before curl batches. A 307 from `/api/x/` usually means an empty id variable from an expired token.
- Playwright: use `wait_until="domcontentloaded"`; `/api/events` SSE keeps the network busy so `networkidle` never fires.
- Console warning "In HTML, <span> cannot be a child of <option>" is produced by `@emergentbase/visual-edits` babel plugin (dev mode only; wraps dynamic option text in `<span data-ve-dynamic>`). Not app code; ignore.
- Hermes service keys issued before 2026-06 get `knowledge:grant` added at startup by seed.py.
