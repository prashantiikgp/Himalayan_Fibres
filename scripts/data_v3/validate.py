"""Post-clean sanity checks. Fail loudly if invariants break."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .schema import Category, ContactV3


@dataclass
class ValidationResult:
    counts_per_category: dict[Category, int]
    emails_per_category: dict[Category, int]
    phones_per_category: dict[Category, int]
    countries_per_category: dict[Category, dict[str, int]]
    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate(buckets: dict[Category, list[ContactV3]]) -> ValidationResult:
    errors: list[str] = []
    counts: dict[Category, int] = {}
    emails: dict[Category, int] = {}
    phones: dict[Category, int] = {}
    countries: dict[Category, dict[str, int]] = {}

    seen_email: dict[str, Category] = {}
    seen_phone: dict[str, Category] = {}

    for cat, rows in buckets.items():
        counts[cat] = len(rows)
        emails[cat] = sum(1 for r in rows if r.email)
        phones[cat] = sum(1 for r in rows if r.phone)
        countries[cat] = dict(Counter(r.country or "(unknown)" for r in rows))

        for r in rows:
            if not r.is_reachable():
                errors.append(f"unreachable row survived: {cat.value} / {r.company!r}")
            if r.email:
                if r.email in seen_email and seen_email[r.email] != cat:
                    errors.append(
                        f"email {r.email!r} is in both {seen_email[r.email].value} and {cat.value}"
                    )
                seen_email[r.email] = cat
            pk = r.dedup_key_phone()
            if pk:
                if pk in seen_phone and seen_phone[pk] != cat:
                    errors.append(
                        f"phone {pk!r} is in both {seen_phone[pk].value} and {cat.value}"
                    )
                seen_phone[pk] = cat

    return ValidationResult(counts, emails, phones, countries, errors)
