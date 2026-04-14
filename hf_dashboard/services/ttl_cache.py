"""Thread-safe TTL cache decorator, YAML-driven.

Gradio runs every handler in a worker thread, so `functools.lru_cache`
is correct (its internal dict access is thread-safe) but offers no
time-based expiry. This module adds that without forcing callers to
pick a magic-number TTL at definition time — every `@ttl_cache(bucket)`
call looks up its TTL in `config/cache/ttl.yml` at evaluation time.
Tuning the cache is a YAML-edit + restart, not a code change.

Design notes:

- **Nullary helpers only.** Cached functions should take no arguments,
  or only trivially-hashable ones (strings / ints / tuples). The common
  case is "load the current active segments" — the function opens its
  own DB session internally, fetches the data, closes the session,
  returns the value. The decorator then caches that return value under
  the function's qualified name for the bucket's TTL.

- **Bucket names are required.** There is no "just cache this for 60
  seconds" — every call must name a bucket from `config/cache/ttl.yml`.
  This forces us to put every tunable duration into one place.

- **Schema validation already ran.** `ConfigLoader.load_ttl_cache()`
  returns a Pydantic model with `extra="forbid"`, so if a decorator
  references a bucket that does not exist in the schema, the config
  loader raises at startup. We still guard with a fallback here so
  that diagnostic logging doesn't turn into a 500.

Usage:

    from services.ttl_cache import ttl_cache

    @ttl_cache("segments_list_seconds")
    def get_active_segments_cached() -> list[Segment]:
        from services.database import get_db
        db = get_db()
        try:
            return db.query(Segment).filter(Segment.is_active).all()
        finally:
            db.close()

    # Callers:
    segs = get_active_segments_cached()   # first call: DB query
    segs = get_active_segments_cached()   # second call inside TTL: cache hit
"""

from __future__ import annotations

import logging
import threading
import time
from functools import wraps
from typing import Any, Callable

_log = logging.getLogger(__name__)

# Qualified-name → (expires_at_unix, value)
_STORE: dict[str, tuple[float, Any]] = {}
_LOCK = threading.Lock()
_FALLBACK_SECONDS = 60


def _bucket_seconds(bucket_name: str) -> int:
    """Resolve a bucket name to its configured TTL via ConfigLoader.

    Falls back to `_FALLBACK_SECONDS` if the config file can't be
    loaded — the tracker should never blow up the caller.
    """
    try:
        from loader.config_loader import get_config_loader
        cfg = get_config_loader().load_ttl_cache().ttl_cache
        return int(getattr(cfg, bucket_name))
    except Exception as e:
        _log.warning(
            "ttl_cache: bucket %r not resolvable (%s), using fallback %ds",
            bucket_name, e, _FALLBACK_SECONDS,
        )
        return _FALLBACK_SECONDS


def ttl_cache(bucket_name: str) -> Callable:
    """Decorator factory. `bucket_name` must exist in `config/cache/ttl.yml`.

    Args:
        bucket_name: Key name in the TtlCacheDefinition schema. Looked
            up on each cache miss, so editing the YAML + restarting
            the Space applies the new TTL.
    """
    def deco(fn: Callable) -> Callable:
        qualname = f"{fn.__module__}.{fn.__qualname__}"

        @wraps(fn)
        def wrapped(*args, **kwargs):
            # Cache key includes args/kwargs so the same cached helper
            # can serve multiple arg combinations without collision.
            # All args / kwargs must be hashable — if not, the caller
            # should refactor to a nullary helper instead of asking the
            # cache layer to hash arbitrary objects.
            try:
                key = (qualname, args, tuple(sorted(kwargs.items())))
                hash(key)  # fail-fast if unhashable
            except TypeError as e:
                _log.warning(
                    "ttl_cache: %s called with unhashable args (%s); "
                    "bypassing cache", qualname, e,
                )
                return fn(*args, **kwargs)

            now = time.time()
            with _LOCK:
                hit = _STORE.get(key)
                if hit is not None and hit[0] > now:
                    return hit[1]

            value = fn(*args, **kwargs)
            ttl = _bucket_seconds(bucket_name)
            with _LOCK:
                _STORE[key] = (now + ttl, value)
            return value

        return wrapped
    return deco


def clear_all() -> None:
    """Drop every cached value. Useful after writes that invalidate a
    cached read (e.g. after a segment edit clear the segments bucket)."""
    with _LOCK:
        _STORE.clear()


def clear_for(bucket_name: str) -> None:  # noqa: ARG001 - placeholder
    """TODO: support per-bucket invalidation. Currently no-op except to
    clear everything, since the store is keyed on qualname, not bucket.
    Wire up if we start caching multiple buckets that need independent
    invalidation."""
    clear_all()


def stats() -> dict:
    """Return a small diagnostic snapshot of the cache state."""
    now = time.time()
    with _LOCK:
        return {
            "entries": len(_STORE),
            "live": sum(1 for (expires, _v) in _STORE.values() if expires > now),
            "expired": sum(1 for (expires, _v) in _STORE.values() if expires <= now),
        }
