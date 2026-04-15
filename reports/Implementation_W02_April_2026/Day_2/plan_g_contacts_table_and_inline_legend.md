# Contacts page — table alignment fix + inline legend + remove KPI cards

## Context

The Contacts page on the live HF Space has three visible problems the user flagged from a screenshot:

1. **Table columns don't align with their headers.** Long email addresses visually spill into the Phone column. Root cause: `components/styles.py::table_cell` produces a style string with no `overflow:hidden / text-overflow:ellipsis / white-space:nowrap`. The `<table>` itself already uses `table-layout:fixed` + a `<colgroup>` with per-column widths, so the fix is purely at the cell-style level — once cells clip, the fixed layout takes effect and the email column stays inside its 14% slot.
2. **Redundant KPI cards at the bottom of the filter sidebar** creating an awkward in-column scroller. The user wants them removed from Contacts and the data consolidated on Home.
3. **Sidebar has dead space below the 5 filter dropdowns.** The user explicitly said *do not compact the filters* — leave them stacked. Instead, fill the empty space below the dropdowns with an **inline legend** explaining Customer Types / Segments / Tags. A legend function already exists (`_build_legend()` at `contacts.py:303`), currently rendered into a modal triggered by the `ℹ Legend` footer button. Reuse the same function for the sidebar; the modal button stays.

### Review notes (post-exploration)

- **Home already has 3 of 4 Contacts KPIs:** `home.py:274–287` shows `Contacts` (= Total), `Opted In`, `Pending`. **`WA Ready` is missing** — Home has `24h Window` in Row 1 (WA messageable now) which is related but not the same metric. **Decision needed** — see Step 3b.
- **Keep the divider at line 430.** The existing `<div style="height:1px; ...">` separator belongs between filters and legend too, not just filters and the old KPI block. Do not delete it — only delete the `left_kpis = gr.HTML(value="")` on line 431.
- **`.contacts-legend details { ... }` CSS rule at `theme_css.py:343` is a dead selector** — `_build_legend()` renders plain `<div>` elements, no `<details>`. The inline legend won't pick up any unwanted modal-like framing from that rule. Safe to reuse.
- **`contacts-legend-modal` class has no CSS** — it's an unused hook. Dropping it for inline mode is a no-op but keeps the markup honest.
- **`render_kpi_row` is only imported once** in `contacts.py` (line 17) and called once (line 767). Removing both makes the import safely deletable.

No engine / schema / YAML changes. Pure UI.

## Files to modify

1. `hf_dashboard/components/styles.py` — fix `table_cell()` to clip overflow.
2. `hf_dashboard/pages/contacts.py` — remove KPI cards, add `inline` param to `_build_legend()`, render inline legend in sidebar, pass `title=` attributes on truncated cells.
3. `hf_dashboard/pages/home.py` — add `WA Ready` tuple to `row2` in the home KPI render (Step 3b).
4. `hf_dashboard/shared/theme_css.py` — optional, only if inline legend looks cramped during verification. The existing `.contacts-legend .legend-col { flex: 1 1 220px }` already wraps to a single column when the sidebar is <220px, so no change is expected on first pass.

## Implementation steps

### Step 1 — Fix table cell clipping (`components/styles.py:76`)

Current:
```python
def table_cell(font: str = "") -> str:
    c = _c("table")
    mono = "font-family:monospace;" if font == "monospace" else ""
    return f"padding:{c['cell_padding']}; font-size:{c['cell_font_size']}; {mono}"
```

Change to:
```python
def table_cell(font: str = "") -> str:
    c = _c("table")
    mono = "font-family:monospace;" if font == "monospace" else ""
    return (
        f"padding:{c['cell_padding']}; font-size:{c['cell_font_size']}; {mono}"
        f"overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"
    )
```

This alone snaps every column inside its `<colgroup>` width. Emails, phones, cities all truncate with `…` instead of bleeding into neighbors.

### Step 2 — Add `title=` attributes for hover-to-read (`pages/contacts.py:_build_table`)

In the row renderer (lines 174–269), for fields that commonly truncate — `email`, `phone`, `company`, `name`, `city`, `tags` — set `title="<full value>"` on the `<td>` so users can hover and see the complete text that got ellipsized. Escape with `html.escape()` (add `import html` at top).

Example for email branch (line 200):
```python
elif field == "email":
    font = col.get("font", "")
    display = contact.email if _is_real_email(contact.email) else missing
    raw = contact.email or ""
    cells += (
        f'<td style="{table_cell(font=font)}; color:#94a3b8;" '
        f'title="{html.escape(raw)}">{display}</td>'
    )
```

Apply the same pattern to `name`, `company`, `phone`, `city`, `tags` branches.

### Step 3 — Remove KPI cards from the contacts sidebar (`pages/contacts.py`)

- **Line 431**: delete `left_kpis = gr.HTML(value="")`. **Keep the divider on line 430** — it now separates filters from the inline legend added in Step 4.
- **Lines 767–772**: delete the `kpis = render_kpi_row([...])` block (including the four tuples).
- **Lines 763–765**: delete the now-orphaned `opted_in` / `pending` / `wa_ready` `db.query().count()` calls, since nothing else in `_apply` uses them. Leave the `total` count only if still needed — currently it is only used by the deleted KPI row, so delete it too.
- **Line 778**: change `return kpis, table, label, effective_page, total_pages, effective_page + 1` to `return table, label, effective_page, total_pages, effective_page + 1`.
- **Line 783**: `apply_outputs = [left_kpis, table_html, pag_label, page_state, total_pages_state, page_num]` → `apply_outputs = [table_html, pag_label, page_state, total_pages_state, page_num]`.
- **Line 17**: delete `from components.kpi_card import render_kpi_row` (single caller, confirmed via grep).

### Step 3b — Add `WA Ready` to the Home KPI row (`pages/home.py:282–287`)

Home currently has `Opted In`, `Pending`, `Email Campaigns`, `WA Campaigns` in Row 2. The user's stated assumption is that moving KPI cards to Home is a no-op because Home "already has that" — but `WA Ready` (contacts with a non-null `wa_id`) is genuinely missing. Two options:

- **Option A (recommended):** add a 5th tuple to `row2` in `home.py` for `WA Ready`. The `wa_ready` count is already computed inside Home's `_refresh` — if not, add one `db.query(Contact).filter(Contact.wa_id.isnot(None)).count()` call mirroring the one being deleted from `contacts.py`. `render_kpi_row` handles 5-tuples fine (it uses `flex:1` per card).
- **Option B:** accept the loss. `24h Window` in Row 1 arguably covers "WA messageability" well enough for the home dashboard, and `WA Ready` is still computable on demand.

**Going with Option A.** It's 4 lines in `home.py` and matches the user's mental model of "Home is where the keycards live". If the 5-card row looks visually cramped during verification, switch to Option B at that point — no plan rewrite needed.

### Step 4 — Render the inline legend in the sidebar (`pages/contacts.py:412–431`)

**Signature change** (`contacts.py:303`): `def _build_legend(inline: bool = False) -> str:`

Inside the function, branch the top wrapper:

```python
if inline:
    wrapper_class = "contacts-legend contacts-legend-inline"
    heading_html = f'<h4 style="margin:0 0 8px 0; font-size:11px; text-transform:uppercase; letter-spacing:.4px; color:#e7eaf3;">{summary}</h4>'
else:
    wrapper_class = "contacts-legend contacts-legend-modal"
    heading_html = f'<div class="hf-modal-title">{summary}</div>'
```

Then render `<div class="{wrapper_class}">{heading_html}<div class="legend-body">...</div></div>`.

**Call sites:**
- **Line 510** (modal) stays as `_build_legend()` — uses default `inline=False`, no behavior change.
- **Inside the left column** (replacing the deleted `left_kpis` at line 431), add:
  ```python
  gr.HTML(value=_build_legend(inline=True))
  ```
  Line 430 (the existing divider) stays as-is and now separates the filters from the inline legend.

`_build_legend()` already emits the `.contacts-legend` / `.legend-body` / `.legend-col` / `.legend-pill` / `.legend-tag` classes that `shared/theme_css.py` already styles. Because `.legend-col` uses `flex: 1 1 220px` with `flex-wrap: wrap`, inside the narrow sidebar (~200px) the three columns will stack vertically — the intended behavior.

**Performance note:** `_build_legend()` queries `count_segment_members()` per segment on every page build. In `build(ctx)` the inline legend HTML is baked into `gr.HTML(value=...)` at construction time — same as the modal call already does — so it's computed once per navigation, not per filter change. No extra DB load from adding the inline render.

### Step 5 — CSS sanity check (`shared/theme_css.py:207`)

The `.page-left-col` rule already has `max-height: calc(100vh - 110px); overflow-y: auto`. That means if the legend plus filters overflow the viewport, the sidebar scrolls internally — exactly the behavior we want, and it does not produce the "nonsense scroller" the user complained about because the Home page layout was the context of that complaint (the keycards created the awkward scroll, not the sidebar).

No CSS changes expected. If the inline legend looks too cramped during verification, add a new `.page-left-col .contacts-legend .legend-col { flex-basis: 100% }` rule so each section goes full-width of the sidebar without waiting on the 220px flex-basis breakpoint.

## Verification

Per `CLAUDE.md`: never run the app locally. Deploy-first, verify on the live Space.

1. `python scripts/deploy_hf.py` — uploads `hf_dashboard/` to the HF Space.
2. Wait for the Space to report **Running** at https://huggingface.co/spaces/prashantiitkgp08/himalayan-fibers-dashboard.
3. Drive the live URL with Playwright MCP tools (headless) against https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space/:
   - Navigate to **Contacts**.
   - Screenshot the full page — assert: no KPI cards in the left column, inline legend visible under the 5 filters, table columns aligned to headers, long emails ending in `…`.
   - Hover a truncated email cell with `browser_hover` + screenshot — assert `title` tooltip contains the full email.
   - Change the `Segment` dropdown (e.g. to `End Consumer`) and confirm the table re-renders — this is the critical check that removing `left_kpis` from `apply_outputs` and the `kpis` return value didn't desync the handler inputs/outputs.
   - Trigger search, pagination next/prev, and tag multiselect — each must still re-render the table without a Python error in the Space logs.
   - Click the **ℹ Legend** footer button — assert the modal still opens with the large 3-column legend (this confirms the `inline=False` default path still works).
   - Navigate to **Home** — screenshot Row 2 and assert the new `WA Ready` card renders alongside `Opted In` / `Pending` / `Email Campaigns` / `WA Campaigns`.
4. If the inline legend looks cramped or `WA Ready` on Home looks overflowed, apply the fallback CSS tweak in `theme_css.py` and/or fall back to Option B in Step 3b. Re-deploy and re-verify.

## Rollback

All edits land in at most four files: `hf_dashboard/components/styles.py`, `hf_dashboard/pages/contacts.py`, `hf_dashboard/pages/home.py`, and optionally `hf_dashboard/shared/theme_css.py`. `git checkout -- <those>` reverts cleanly. No DB migrations, no YAML changes, no new dependencies. The HF Space rolls back on the next `scripts/deploy_hf.py` upload.
