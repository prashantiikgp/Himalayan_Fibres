"""Pydantic schemas for the dashboard's cache configuration.

Kept separate from theme / WA schemas so services under
`hf_dashboard/services/` can import cache config without pulling in
the rest of the engine graph. Matches the engine-config-rule pattern
from `engines/theme_schemas.py`: every YAML file under
`hf_dashboard/config/` must have a matching Pydantic model so typos
or stale keys fail loudly at load time, not silently as
`get(..., default)` misses at runtime.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TtlCacheDefinition(BaseModel):
    """Per-bucket TTL durations in seconds.

    Add a new bucket by adding a field here AND a matching key in
    `config/cache/ttl.yml`. Pydantic's `extra="forbid"` means the
    dashboard will refuse to start if the YAML has a key this schema
    does not declare — that's the point, so typos can't land unnoticed.
    """
    model_config = ConfigDict(extra="forbid")

    segments_list_seconds: int = Field(300, ge=1)
    home_activity_seconds: int = Field(60, ge=1)
    home_counts_seconds: int = Field(60, ge=1)
    wa_templates_seconds: int = Field(300, ge=1)
    lifecycle_counts_seconds: int = Field(60, ge=1)


class TtlCacheFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ttl_cache: TtlCacheDefinition
