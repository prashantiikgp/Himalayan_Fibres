"""Dedup logic — within-file and cross-file.

Within-file: collapse rows that share the same identity (email, then
phone, then company name). Field-level merge: keep the most-complete
non-empty value across the duplicates.

Cross-file: enforce CATEGORY_PRIORITY — if the same identity appears in
a higher-priority bucket, drop it from the lower one. This is what
guarantees the user's invariant: a lapsed client never appears under
carpet leads, an existing client never appears anywhere else, etc.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .schema import CATEGORY_PRIORITY, Category, ContactV3


@dataclass
class DedupStats:
    within_file_collapsed: dict[Category, int] = field(default_factory=lambda: defaultdict(int))
    cross_file_dropped: dict[tuple[Category, Category], int] = field(default_factory=lambda: defaultdict(int))
    unreachable_dropped: dict[Category, int] = field(default_factory=lambda: defaultdict(int))


def _merge(a: ContactV3, b: ContactV3) -> ContactV3:
    """Merge two records into one — keep the higher-priority category,
    fall back to non-empty fields from either side."""
    keep_cat = a.category if CATEGORY_PRIORITY[a.category] <= CATEGORY_PRIORITY[b.category] else b.category
    keep_src = a.source_file if keep_cat == a.category else b.source_file
    pick = lambda x, y: x if x else y
    return ContactV3(
        email=pick(a.email, b.email),
        phone=pick(a.phone, b.phone),
        first_name=pick(a.first_name, b.first_name),
        last_name=pick(a.last_name, b.last_name),
        company=pick(a.company, b.company),
        country=pick(a.country, b.country),
        category=keep_cat,
        source_file=keep_src,
    )


def dedup_within(rows: list[ContactV3], stats: DedupStats) -> list[ContactV3]:
    """Collapse intra-bucket duplicates by email -> phone -> company."""
    if not rows:
        return []
    cat = rows[0].category
    by_email: dict[str, ContactV3] = {}
    by_phone: dict[str, ContactV3] = {}
    by_company: dict[str, ContactV3] = {}
    keyless: list[ContactV3] = []

    for r in rows:
        ek = r.dedup_key_email()
        pk = r.dedup_key_phone()
        ck = r.dedup_key_company()

        # Try to find an existing partner via any key.
        partner = None
        if ek and ek in by_email:
            partner = by_email[ek]
        elif pk and pk in by_phone:
            partner = by_phone[pk]
        elif ck and ck in by_company:
            partner = by_company[ck]

        merged = _merge(partner, r) if partner else r
        if partner:
            stats.within_file_collapsed[cat] += 1

        # (Re)index merged record under all its keys.
        if merged.dedup_key_email():
            by_email[merged.dedup_key_email()] = merged
        if merged.dedup_key_phone():
            by_phone[merged.dedup_key_phone()] = merged
        if merged.dedup_key_company():
            by_company[merged.dedup_key_company()] = merged
        if not (ek or pk or ck):
            keyless.append(merged)

    # The same merged record may be present under multiple key indexes;
    # collapse by python identity.
    seen_ids: set[int] = set()
    out: list[ContactV3] = []
    for src in (by_email.values(), by_phone.values(), by_company.values()):
        for r in src:
            if id(r) in seen_ids:
                continue
            seen_ids.add(id(r))
            out.append(r)
    out.extend(keyless)
    return out


def dedup_across(buckets: dict[Category, list[ContactV3]], stats: DedupStats) -> dict[Category, list[ContactV3]]:
    """Enforce category priority across buckets.

    Build a global key index from highest-priority bucket downward; any
    later bucket that hits an existing key is dropped (and counted).
    """
    ordered = sorted(buckets.keys(), key=lambda c: CATEGORY_PRIORITY[c])
    global_email: dict[str, Category] = {}
    global_phone: dict[str, Category] = {}
    global_company: dict[str, Category] = {}
    out: dict[Category, list[ContactV3]] = {c: [] for c in ordered}

    for cat in ordered:
        for r in buckets.get(cat, []):
            ek = r.dedup_key_email()
            pk = r.dedup_key_phone()
            ck = r.dedup_key_company()

            collision_with: Category | None = None
            if ek and ek in global_email:
                collision_with = global_email[ek]
            elif pk and pk in global_phone:
                collision_with = global_phone[pk]
            elif ck and ck in global_company:
                collision_with = global_company[ck]

            if collision_with is not None:
                stats.cross_file_dropped[(cat, collision_with)] += 1
                continue

            out[cat].append(r)
            if ek:
                global_email[ek] = cat
            if pk:
                global_phone[pk] = cat
            if ck:
                global_company[ck] = cat

    return out


def drop_unreachable(rows: list[ContactV3], stats: DedupStats) -> list[ContactV3]:
    if not rows:
        return []
    cat = rows[0].category
    keep: list[ContactV3] = []
    for r in rows:
        if r.is_reachable():
            keep.append(r)
        else:
            stats.unreachable_dropped[cat] += 1
    return keep
