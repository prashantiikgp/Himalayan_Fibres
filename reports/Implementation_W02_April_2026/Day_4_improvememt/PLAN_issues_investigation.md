# Phase 9 — Issue Investigation & Resolution

## Implementation strategy

Phase 9 hunts down four production issues surfaced during Phase 7 verification on the live v2 Space. The headline issue is the SSL handshake timeout when sending templates (`API 502 on /api/v2/wa/template-sends: WhatsApp template send failed: _ssl.c:999: The handshake operation timed out`) — that's blocking real sends and is the user's top priority. The other three (sync's `one_or_none` tripping on duplicate rows, the Studio still showing the contact ID instead of name on direct URL navigation, and the HowToUse layout already covered in Phase 8.5) are smaller-blast-radius bugs that landed on the "flagged but not fixed" list during the Phase 7 verification pass.

The order of work is 9.1 (SSL timeout — diagnose first, fix second; it might be infrastructure rather than code) → 9.2 (sync duplicate-row crash — pure bug fix) → 9.3 (TemplateSheet contact-name fallback — UX polish). Risk concentration: 9.1 has a real chance of being unfixable from our side (HF Spaces network constraint to `graph.facebook.com`), in which case the deliverable becomes a clear retry/timeout story plus operator-visible diagnostics rather than a "no more timeouts ever" claim.

---

## Phase 9.1 — SSL handshake timeout to Meta WhatsApp Cloud API

### Problem recap

Sending a template via the `/api/v2/wa/template-sends` endpoint intermittently fails with:

```
HTTP 502 Bad Gateway
{"detail": "WhatsApp template send failed: _ssl.c:999: The handshake operation timed out"}
```

The error originates inside Python's `ssl` module during TLS handshake to `graph.facebook.com`. The request never reaches Meta — the TCP connection opens but the TLS negotiation stalls past httpx's connect-timeout budget.

Symptom characteristics observed during Phase 7 verification:
- Reproduced once on a fresh template send right after an idle period (cold connection)
- The same operator action retried ~30s later succeeded
- No correlation with template name, recipient, or payload size
- The HF Space was reporting **Running** (not building, not paused)

### Existing infrastructure (must read before designing the fix)

`hf_dashboard/services/wa_sender.py` already implements retry + timeout — the fix is **adjusting and extending** this, not building from scratch. Current state:

| Attribute | Value | Location |
|---|---|---|
| HTTP library | **httpx** (NOT `requests`) | `import httpx`, line 13 |
| Default timeout | `httpx.Timeout(connect=15.0, read=30.0, write=30.0, pool=5.0)` | line 62 |
| Retry helper | `_post_with_retry(url, *, json, json_ct=True)` | lines 64-99 |
| Retry attempts | `_MAX_RETRIES = 2` (3 total tries) | line 51 |
| Retry backoff | `_RETRY_BACKOFF_S = 1.5` × `2 ** attempt` → 1.5s, 3s | line 52, 95 |
| Retry catches | `httpx.ConnectError`, `httpx.ConnectTimeout`, `httpx.ReadTimeout`, `httpx.RemoteProtocolError` | lines 84-87 |

**Send paths that DO route through `_post_with_retry`:** `send_text` (line 128), `send_template` body call (line 210), `send_template` lang-fallback call (line 243).

**Meta-API call sites that BYPASS the retry helper** (raw `httpx.{post,get,delete}` with only `self._timeout`): media upload (line 261), `list_templates` (line 274), template details (line 297), submit-template-to-Meta (line 322), delete-template (line 335).

**Implication:** the SSL handshake failure on a template-send DID go through `_post_with_retry`, which DID try 3 times across ~4.5s of total backoff, and all attempts failed. So the fix is not "add retry"; it's "the existing retry's budget/scope is wrong for HF's egress reality."

### Root cause hypotheses (ranked, post-audit)

1. **The existing retry's total budget (~4.5s) is shorter than HF's egress hiccup duration.** HF's outbound TLS path has been observed to deadlock for 10-30s. Three attempts within 4.5s all hit the same dead window. **Most likely.** Fix: increase `_MAX_RETRIES` and/or backoff, possibly switch to true exponential with jitter (e.g., 2s, 5s, 12s for a ~20s budget).

2. **HF Space outbound network instability** — the underlying cause of #1. Other HF users have reported `_ssl.c:999` errors when calling external APIs. **Real but unfixable from our side beyond longer retry + better operator visibility.** This is what the diagnostics endpoint will help confirm.

3. **`httpx.ConnectError` may not wrap every flavor of `ssl.SSLError`.** In some httpx/anyio versions, `ssl.SSLError` raised during the OpenSSL `do_handshake()` call can escape as a bare `OSError` or `ssl.SSLError` rather than `httpx.ConnectError`, slipping past the retry catch entirely. **Plausible.** Fix: widen the catch to include `httpx.TransportError` (the parent of `ConnectError`/`ConnectTimeout`) plus `ssl.SSLError` and `OSError` (the latter narrowed by message check) as a belt-and-braces measure. Verify against the actual exception observed in the live Space logs (investigation step #2).

4. **The 502 is produced by HF's reverse proxy, not by our code.** When the worker hangs >30s, HF's edge returns 502 to the client. Our code might raise `WhatsAppSendTransientError` (or a similar exception) but the FastAPI 500 response never makes it back. **Possible** — would mean any `502 → 503` API-side change is cosmetic. Confirm in investigation step #4 by looking at the actual response source (the `detail` body shows our error string, suggesting it DOES come from FastAPI — so probably not this).

5. **`submit_template_to_meta` and other bypass call sites are vulnerable** to the same handshake timeout but get worse failure modes (no retry at all). **Real but secondary** — sends are the user-facing complaint. Address as part of the same fix by routing all Meta calls through one retry helper.

6. **MTU / fragmentation issue between HF and Meta.** Some Docker overlay networks have MTU mismatches that drop large TLS handshake packets. **Very unlikely** but cheap to check via `ip link show eth0` from the Space console.

### Investigation steps (do these before any code change)

1. **Confirm the audit table above** — re-verify `wa_sender.py` line numbers haven't drifted; map every Meta call site to retry-or-not. Output: a one-page table that says "send_template uses _post_with_retry, submit_template uses raw httpx.post." Owner: 30min.

2. **Capture the actual exception type in production.** Find the failed-send log line on the live Space (HF Spaces UI → "Logs" tab). Confirm whether the traceback ends in `httpx.ConnectError`, `ssl.SSLError`, `OSError`, or something else. This decides whether hypothesis #3 is in play. If logs are gone, add a structured exception log (`logger.exception("WA send failed: type=%s, msg=%s", type(e).__name__, e)`) inside `_post_with_retry`'s except block, deploy, and wait for the next failure.

3. **Trace the 502 to its source.** Three candidates:
   - FastAPI's default for an uncaught exception (returns 500, not 502 — probably not this)
   - `api_v2/routers/wa.py` explicitly returning 502 on a caught domain exception
   - HF's reverse proxy returning 502 on upstream timeout
   The user's screenshot shows `{"detail": "WhatsApp template send failed: _ssl.c:999..."}` which looks like our string — so probably (b). Verify by `grep -nE "502|HTTPException.*status_code" api_v2/routers/wa.py`.

4. **Reproduce locally with a deliberately delayed connection.** Use a Python `httpx` `MockTransport` that sleeps 20s on the first call then succeeds, against `WhatsAppSender.send_template`. Confirms the retry budget is the issue.

5. **Test from inside the HF Space console** (HF UI → Files → "Open in JupyterLab" or via terminal): run `time openssl s_client -connect graph.facebook.com:443 -servername graph.facebook.com < /dev/null` ten times in a row. If any of the ten takes > 5s, hypothesis #2 (HF egress) is confirmed.

6. **Check interface MTU** on the Space (`ip link show`) — rules out hypothesis #6 in 30 seconds.

### Files to modify (after investigation)

- `hf_dashboard/services/wa_sender.py`:
  - **Increase retry budget**: bump `_MAX_RETRIES` from 2 → 4 (5 total tries). Change backoff to `[2, 5, 10, 20]` seconds (manual table, not `2 ** attempt`) — total worst-case ~37s, well below any reasonable proxy timeout. Actual short-path stays fast (one success = no waiting).
  - **Widen the exception catch** in `_post_with_retry` to include `httpx.TransportError` (parent class catching ConnectError/ConnectTimeout/ReadTimeout/RemoteProtocolError plus future siblings) and `ssl.SSLError` (belt-and-braces for the bypass case described in hypothesis #3). After the audit (step #2) we can narrow this if production logs show only `httpx.ConnectError`.
  - **Promote `_post_with_retry` to handle GET and DELETE too** — rename to `_request_with_retry(method, url, **kw)`. Update call sites in `list_templates`, template-details, `submit_template_to_meta`, and `delete_template` to route through it. **Exception:** `submit_template_to_meta` retries are dangerous (could double-create a template at Meta) — keep it on the raw path with a longer timeout and explicit single-try behavior. Document the carve-out inline.
  - **Distinguish transient from terminal failures.** Add a domain exception `WhatsAppSendTransientError(Exception)` raised by `_request_with_retry` after exhausting retries on connection-level errors. HTTP 4xx/5xx responses from Meta are NOT transient (different remediation) — return as today.
  - **Structured logging on retry exhaustion**: log final exception type, the connect/read budgets, the elapsed time, and the call site (`url` arg). One log line per failed send tells the operator exactly what gave up.
- `api_v2/routers/wa.py` — catch `WhatsAppSendTransientError` from `template-sends` and `messages` endpoints. Return `HTTPException(status_code=503, detail={"message": "WhatsApp upstream temporarily unavailable. Please retry.", "retryable": True})`. Fall-through to existing error handling for non-transient failures.
- `vite_dashboard/src/api/wa.ts` — extend `sendTemplate` error handling to surface the `retryable: true` flag in the thrown error.
- `vite_dashboard/src/pages/wa-inbox/components/TemplateSheet.tsx` — when the mutation errors with `retryable === true`, render the error banner with a "Retry" button that re-fires the same payload. Plain non-retryable errors keep today's text-only banner.

### Files to create

- `api_v2/tests/test_wa_send_retries.py` — uses **`pytest-httpx`** (NOT `responses`/`requests-mock`, which are for the `requests` library). Tests:
  - `_request_with_retry` retries on `httpx.ConnectError` and succeeds on the 3rd attempt
  - `_request_with_retry` raises `WhatsAppSendTransientError` after 5 failed `httpx.ConnectError` attempts
  - Direct `ssl.SSLError` (not wrapped) is also caught and triggers the same retry path
  - HTTP 503 response from Meta is NOT retried (it's a Meta-side decision; we surface it as today)
  - `submit_template_to_meta` is NOT routed through retry (idempotency check — assert it raises immediately on a single failure)

### API additions

- `GET /api/v2/wa/diagnostics` — see "Operator-visible diagnostics" below. Adds one new endpoint.
- `template-sends` and `messages` error responses gain an optional `retryable: bool` field. Backwards-compatible; older frontends just ignore it.

### Schema/DB additions

None.

### Operator-visible diagnostics

`GET /api/v2/wa/diagnostics` (lives in `api_v2/routers/wa.py`):
- Performs a single test handshake to `graph.facebook.com:443` (a cheap unauthenticated request, e.g. `httpx.get("https://graph.facebook.com/v21.0/")` with a 5s timeout) and reports `connect_ms`, `tls_handshake_ms`, `total_ms`.
- Returns the active timeout config (`connect`, `read`, `write`, `pool`) and retry config (`max_retries`, backoff schedule).
- Returns `last_send_attempt_at`, `last_send_error_type`, `last_send_error_msg` from an in-process counter (singleton on the `WhatsAppSender` class — no DB write). Counter resets on Space restart, which is fine for incident triage.

Auth: open in v1 (the v2 Space has no `APP_PASSWORD`). When auth is added later, gate the endpoint behind it the same way the rest of `/api/v2/` will be gated. Tracked as a follow-up note in the endpoint's docstring; not blocking 9.1.

### Acceptance criteria

- **AC-9.1.1** With the live audit-table appendix completed, every Meta-API call site is documented as either "uses retry helper" or "intentionally bypasses retry (with reason)." No undocumented bypasses remain.
- **AC-9.1.2** Calling `WhatsAppSender.send_template` against a deliberately blackholed Meta endpoint (e.g. `httpx.MockTransport` returning `httpx.ConnectError` always) raises `WhatsAppSendTransientError` after the configured retry budget elapses (~37s with backoff `[2,5,10,20]`). Not "hangs forever" and not "raises after 4.5s."
- **AC-9.1.3** Calling `WhatsAppSender.send_template` against a `MockTransport` that fails the first 2 attempts with `httpx.ConnectError` then succeeds returns the success — the retry transparently absorbs the flap.
- **AC-9.1.4** Direct `ssl.SSLError` (raised by a `MockTransport`, not wrapped in `httpx.ConnectError`) is also caught and triggers retry — covers hypothesis #3.
- **AC-9.1.5** `submit_template_to_meta` does NOT retry on `ConnectError` (idempotency carve-out) — a unit test asserts the function raises after a single failed attempt.
- **AC-9.1.6** Sending a template on the live Space immediately after a 5-minute idle period succeeds. If it still fails (HF egress fully dead), the response is HTTP 503 with `retryable: true`, the frontend shows a Retry button, and clicking it re-fires the send.
- **AC-9.1.7** `GET /api/v2/wa/diagnostics` returns a JSON body with `tls_handshake_ms` < 500 under normal conditions, plus the active timeout/retry config and the last-send error fields.
- **AC-9.1.8** A failed send on the live Space writes one structured log line containing the exception type, total elapsed time, retry attempts, and the URL — visible in the HF Space logs UI for incident triage.

### Decisions to surface

- **D1** Retry backoff schedule. Recommendation: explicit `[2, 5, 10, 20]` (with ±20% jitter) for a ~37s worst case. **Reject `2 ** attempt`** — it's too aggressive at low attempts (1.5s) and not aggressive enough at the tail.
- **D2** Should we widen the exception catch to include `ssl.SSLError` and `OSError` immediately, or wait for the production log audit (investigation step #2) to confirm we need to? Recommendation: **include both immediately as a belt-and-braces measure** — false positives are harmless (they just route through retry that would otherwise raise), and we don't want a second incident before learning we needed to widen.
- **D3** Should we expose `tls_handshake_ms` in the diagnostics endpoint without auth? Recommendation: **yes for now** — the v2 Space has no auth gate, and the endpoint reveals nothing exploitable beyond what `openssl s_client` would show. Add a one-line docstring note: "TODO: gate behind APP_PASSWORD when auth lands; see Phase X." No blocker.
- **D4** Should `WhatsAppSendTransientError` carry the original exception as `__cause__`? Recommendation: **yes** — preserves the traceback for log forensics, costs nothing.

### Risks / unknowns

- **R1** If the root cause is HF's egress instability (hypothesis #2), longer retries will mask but not fix the issue — operators see "send took 30 seconds" occasionally. Mitigation: log retry counts; if >5% of sends require retries, file a ticket with HF support and include diagnostics-endpoint output as evidence.
- **R2** Bumping `_MAX_RETRIES` to 4 means a sustained outage stalls the user-facing request for ~37s. The frontend's send mutation must show a spinner the whole time and not time out at the browser's default ~30s. Mitigation: confirm `useSendTemplate` and the underlying `fetch`/axios call have no client-side timeout shorter than 45s; add one if so.
- **R3** The `retryable: true` field is an API-contract addition. Frontends that don't check it simply don't render a Retry button — backwards-compatible.
- **R4** Submit-to-Meta carve-out from retry means an SSL flap during template submission shows the operator a hard failure. Mitigation: surface a clear UI message ("Submission failed mid-flight; click again to retry") and rely on the operator to retry manually. Adding idempotency keys to Meta submissions is out of scope.
- **R5** The audit might surface a call site we missed. Mitigation: investigation step #1 explicitly enumerates every site; the AC-9.1.1 "no undocumented bypasses" gate prevents shipping with an unknown bypass.

---

## Phase 9.2 — Sync `one_or_none` crash on duplicate (name, language) rows

### Problem recap

During Phase 7 verification, clicking "Sync from Meta" on `/wa-templates` returned:

```
Sync failed: Multiple rows were found when one or none was required
```

Investigation showed `wa_templates` has duplicate `(name, language)` pairs for some templates — e.g. `followup_interest` exists as both `is_draft=True` and `is_draft=False`, `sample_shipped` similarly. The sync's existing-row lookup in `WhatsAppSender.sync_templates_from_meta` uses `.one_or_none()` which raises `MultipleResultsFound` whenever it sees these duplicates.

### Root cause

`hf_dashboard/services/wa_sender.py` line ~368 (the existing-template lookup inside `sync_templates_from_meta`):

```python
existing = (
    db.query(WATemplate)
    .filter(WATemplate.name == tpl["name"], WATemplate.language == lang)
    .one_or_none()
)
```

The duplicates exist because:
- A draft is created locally (`is_draft=True`) before submission
- The user clicks "Submit to Meta" which creates a Meta-side template
- Meta approves; the next Sync inserts the approved version as a separate row (the lookup at submission time may not have matched, or the submission flow created a fresh row)
- Now there are two rows with the same `(name, language)` — one draft, one approved

The fix is two-part: prevent future duplicates (constraint or explicit dedup in submit flow) and tolerate existing duplicates in the sync code (resolve to the non-draft row, or merge).

### Files to modify

- `hf_dashboard/services/wa_sender.py` — change the lookup to:
  ```python
  existing = (
      db.query(WATemplate)
      .filter(WATemplate.name == tpl["name"], WATemplate.language == lang)
      .order_by(WATemplate.is_draft.asc(), WATemplate.id.asc())  # non-drafts first, then oldest
      .first()
  )
  ```
  Then, after the update, delete any other rows with the same `(name, language)` (since Meta's sync has consolidated them):
  ```python
  duplicates = (
      db.query(WATemplate)
      .filter(
          WATemplate.name == tpl["name"],
          WATemplate.language == lang,
          WATemplate.id != existing.id,
      ).all()
  )
  for dup in duplicates:
      logger.warning("sync: removing duplicate WATemplate id=%s name=%s lang=%s", dup.id, dup.name, lang)
      db.delete(dup)
  ```
- `hf_dashboard/services/wa_sender.py` (submit path) — when submitting a draft to Meta, after success, look for any existing non-draft row with the same `(name, language)` and merge into it instead of leaving two rows.

### Files to create

- `scripts/migrations/2026_05_07_dedup_wa_templates.py` — one-shot cleanup script that scans for duplicate `(name, language)` rows in production and consolidates them. Rules (cover the ≥3 row case, not just 2):
  1. Group rows by `(name, language)`.
  2. **Keeper selection**: prefer the highest-id row with `is_draft=False`. If no non-draft row exists in the group, keep the highest-id `is_draft=True` row.
  3. **Field merge from losers into keeper** (only if keeper's value is empty/null): `meta_template_id`, `submitted_at`, `rejection_reason`. Other fields stay as the keeper has them — the keeper wins on conflict.
  4. **Delete losers** (all non-keeper rows in the group), with a per-row warning log.
  5. Idempotent (no duplicates → no-op). Defaults to `--dry-run`; requires `--confirm` to actually mutate (per D5).
- `api_v2/tests/test_wa_sync_duplicates.py` — unit test that creates two rows for the same `(name, language)`, runs sync, asserts only one row remains and it has the synced data.

### API additions
None.

### Schema/DB additions

Optionally add a partial unique constraint `UNIQUE(name, language) WHERE is_draft = False` so we can never have two non-draft rows for the same template. **Not strictly required** for the fix; the dedup logic in code is sufficient. If we add the constraint, also add an alembic-style migration script (we don't use alembic; a hand-written one matching the pattern in `scripts/migrations/`).

Recommendation: **skip the constraint for v1** — the dedup logic in sync handles it, and adding constraints to a Postgres prod DB without alembic adds operational risk. Revisit if duplicates re-appear after the fix.

### Acceptance criteria

- **AC-9.2.1** With two rows for `followup_interest` (one draft, one approved) in the DB, calling Sync from Meta no longer raises. The approved row is updated; the draft row is deleted.
- **AC-9.2.2** The dedup migration script run against the prod DB consolidates all existing duplicates without losing any `meta_template_id`.
- **AC-9.2.3** Re-running sync after dedup is a no-op (idempotent).
- **AC-9.2.4** Submitting a new draft to Meta and then syncing produces exactly one final row, not two.

### Decisions to surface

- **D4** Hard-delete duplicate drafts during sync, or soft-delete (set `is_deleted=True` flag — would require schema change)? Recommendation: **hard-delete with a warning log**. The data we lose (a stale draft already promoted to APPROVED) is not valuable.
- **D5** Should the dedup migration require a `--confirm` flag like other destructive scripts? Recommendation: yes, plus a `--dry-run` default that prints the planned changes without executing.

### Risks / unknowns

- **R5** If a draft has local edits the user wanted to keep separate from the synced version, hard-delete loses them. Mitigation: the migration's dry-run output shows exactly which rows will be deleted; the operator reviews before confirming.

---

## Phase 9.3 — TemplateSheet contact-name fallback on direct URL nav

### Problem recap

When a user navigates directly to `/wa-inbox?contact=<id>` (e.g. by sharing a link, or by URL state restoration after refresh) AND that contact has no existing WAChat row AND the user opens TemplateSheet, the sheet header reads "Sending to c19ff1ef-..." (the bare contact ID) instead of the contact's name. The new-conversation picker handles this by stashing the picked name in `pickedNames` state, but direct-URL nav has no such handoff.

### Root cause

`WAInboxPage.tsx:45-49` — the lookup chain is:

```ts
const selectedName = selected
  ? convList?.conversations.find((c) => c.contact_id === selected)?.contact_name
    ?? pickedNames[selected]
    ?? selected
  : "";
```

If the contact is not in `convList` (no existing chat) and not in `pickedNames` (not picked via the picker — e.g. direct URL), the fallback is `selected` (the ID). There is no third source — we never query `/api/v2/contacts/{id}` for the name.

### Files to modify

- `vite_dashboard/src/pages/wa-inbox/WAInboxPage.tsx` — extend the fallback chain with a `useContactDetail(selected)` call (the existing hook in `vite_dashboard/src/api/contacts.ts:101`) that fetches the contact when needed:
  ```ts
  const inConvList = !!convList?.conversations.find((c) => c.contact_id === selected);
  const { data: contactData } = useContactDetail(
    selected && !inConvList ? selected : null,
  );
  const selectedName = selected
    ? convList?.conversations.find((c) => c.contact_id === selected)?.contact_name
      ?? pickedNames[selected]
      ?? formatContactName(contactData)
      ?? selected
    : "";
  ```
- `vite_dashboard/src/api/contacts.ts` — no changes; `useContactDetail(contactId: string | null)` already exists at line 101. Verify it returns null/undefined when `contactId` is null (so the conditional fetch works).

### Files to create
None expected (the contacts API hook should already exist).

### API additions
None — `GET /api/v2/contacts/{id}` already exists.

### Schema/DB additions
None.

### Acceptance criteria

- **AC-9.3.1** Navigate directly to `/wa-inbox?contact=<id-of-contact-with-no-chat>`. Open TemplateSheet. Header reads "Sending to <Full Name>", not the ID.
- **AC-9.3.2** No extra request when the contact IS already in `convList` (the conditional fetch is gated).
- **AC-9.3.3** If the contact ID is invalid (404 from the contacts endpoint), the fallback to the bare ID still works (no broken UI).

### Decisions to surface
None.

### Risks / unknowns

- **R6** Adds a new request on direct-URL nav. Mitigation: gated by the conditional check; the contacts endpoint is fast and the result is cached by TanStack Query.

---

## Phase 9.4 — HowToUse accordion full-width (cross-reference)

**Owned by Phase 8.5** in `PLAN_broadcast_redesign.md`. The fix lives there unconditionally — no work happens under 9.4. Listed here only so the issue inventory is complete.

---

## Sequencing summary

```
9.1 (SSL timeout) — INVESTIGATE FIRST, then fix. Highest priority.
   ├── investigation steps (no code changes)
   ├── fix: shared HTTP session + retry + timeout
   └── verify on live Space

9.2 (sync duplicates) — independent of 9.1, can land in parallel
   ├── code fix to sync logic
   ├── one-shot dedup migration
   └── verify Sync from Meta works on /wa-templates

9.3 (contact-name fallback) — pure UI polish, lowest priority
```

**Total estimated time** (rough): 9.1 = 4-6h (mostly investigation), 9.2 = 2h, 9.3 = 30min. Single deploy at the end.

---

## What we're NOT doing in Phase 9

- Adding auth to the v2 Space (the `/diagnostics` endpoint will be open; `APP_PASSWORD` is unset by design)
- Migrating to a managed message queue (Celery, RQ) for sends — current sync send path is intentionally simple
- Switching off `requests` to `httpx` — the retry/timeout fix doesn't require a library swap
- Any rate-limiting on our side — Meta enforces theirs; we don't pre-throttle
