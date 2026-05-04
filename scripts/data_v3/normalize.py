"""Field-level normalizers — pure functions, no I/O."""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

_STATE_FIXUPS = {
    "uttar pradesh": "Uttar Pradesh",
    "uttar pardesh": "Uttar Pradesh",
    "u.p.": "Uttar Pradesh",
    "up": "Uttar Pradesh",
    "tamilnadu": "Tamil Nadu",
    "tamil nadu": "Tamil Nadu",
    "jammu and kash": "Jammu & Kashmir",
    "jammu & kashmi": "Jammu & Kashmir",
    "jammu & kashmir": "Jammu & Kashmir",
    "new delhi": "Delhi",
    "delhi": "Delhi",
    "haryana": "Haryana",
    "rajasthan": "Rajasthan",
    "maharashtra": "Maharashtra",
    "kerala": "Kerala",
    "west bengal": "West Bengal",
    "gujarat": "Gujarat",
    "bihar": "Bihar",
    "punjab": "Punjab",
    "karnataka": "Karnataka",
}

_COUNTRY_FIXUPS = {
    "india": "India",
    "usa": "USA",
    "u.s.a.": "USA",
    "united states": "USA",
    "united states of america": "USA",
    "uk": "UK",
    "united kingdom": "UK",
    "netherlands": "Netherlands",
}


def clean_str(v) -> str:
    """Trim, collapse internal whitespace, drop literal 'nan'."""
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("nan", "none", "null", ""):
        return ""
    return re.sub(r"\s+", " ", s)


def title_name(v) -> str:
    """Title-case names but preserve common Indian honorifics & particles."""
    s = clean_str(v)
    if not s:
        return ""
    if s.isupper() or s.islower():
        s = s.title()
    return s


def clean_company(v) -> str:
    """Title-case if all-caps, otherwise leave the user's casing."""
    s = clean_str(v)
    if not s:
        return ""
    return s.title() if s.isupper() else s


def clean_email(v) -> str | None:
    """Extract the first valid email from a cell.

    The yarn-store source ships some cells as JSON-list strings —
    `["a@b.com","c@d.com"]` — and others as comma-separated. We scan
    for any valid email-shaped substring and take the first one.
    """
    s = clean_str(v)
    if not s or "@" not in s:
        return None
    m = _EMAIL_RE.search(s)
    return m.group(0).lower() if m else None


def clean_country(v) -> str:
    s = clean_str(v)
    if not s:
        return ""
    return _COUNTRY_FIXUPS.get(s.lower(), s)


def clean_state(v) -> str:
    s = clean_str(v)
    if not s:
        return ""
    return _STATE_FIXUPS.get(s.lower(), s.title())


def clean_phone(v, default_country_code: str | None = None) -> str | None:
    """Return E.164-ish format: '+<cc><digits>' or None.

    `default_country_code` is applied only when the input has no '+' prefix
    and is plausibly a national number ('+91' for India sources, '+1' for US).
    """
    s = clean_str(v)
    if not s:
        return None
    has_plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    if len(digits) < 7:
        return None
    if has_plus:
        return f"+{digits}"
    if default_country_code:
        cc = default_country_code.lstrip("+")
        if digits.startswith(cc) and len(digits) > 10:
            return f"+{digits}"
        return f"+{cc}{digits[-10:]}" if len(digits) >= 10 else f"+{cc}{digits}"
    return f"+{digits}"
