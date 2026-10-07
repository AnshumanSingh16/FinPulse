"""API authentication: hashed API keys, roles and the organisation each key acts for.

Keys are configured as ``API_KEYS`` — comma-separated ``name:role:sha256hex[:org_uuid]`` entries.
Only the SHA-256 of a key is ever configured or stored; the key itself is shown once, when it is
generated (``finpulse auth new-key``). Presented keys are compared in constant time.

Roles, each including the ones before it:
  viewer   read entities, metrics, passports, warnings, stress catalogue, investigations
  analyst  + run stress tests, agents and investigations (these cost compute and LLM calls)
  admin    + reset the demo data

Without keys, authentication is off — allowed only in development and test, where every
request acts as a local administrator of the demo organisation. Staging and production refuse
to start without keys (``validate_security``).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass
from typing import Literal

from finpulse.synthetic.ids import DEMO_ORG_ID

Role = Literal["viewer", "analyst", "admin"]
ROLES: tuple[Role, ...] = ("viewer", "analyst", "admin")
KEY_PREFIX = "fpk_"
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_HEX = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ApiKey:
    name: str
    role: Role
    sha256: str
    org_id: uuid.UUID = DEMO_ORG_ID


@dataclass(frozen=True)
class Principal:
    """Who is calling: a named key (or the local developer when auth is off)."""

    name: str
    role: Role
    org_id: uuid.UUID
    authenticated: bool

    def can(self, role: Role) -> bool:
        return ROLES.index(self.role) >= ROLES.index(role)


LOCAL_DEVELOPER = Principal("local-development", "admin", DEMO_ORG_ID, authenticated=False)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def parse_api_keys(raw: str | None) -> list[ApiKey]:
    """Parse ``API_KEYS``; raises ``ValueError`` (never echoing a hash) on a malformed entry."""
    keys: list[ApiKey] = []
    for n, entry in enumerate(e.strip() for e in (raw or "").split(",")):
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) not in (3, 4):
            raise ValueError(f"API_KEYS entry {n + 1}: expected name:role:sha256[:org_uuid]")
        name, role, digest = parts[0], parts[1], parts[2].lower()
        if not _NAME.match(name):
            raise ValueError(f"API_KEYS entry {n + 1}: invalid name")
        if role not in ROLES:
            raise ValueError(f"API_KEYS entry {n + 1}: role must be one of {', '.join(ROLES)}")
        if not _HEX.match(digest):
            raise ValueError(f"API_KEYS entry {n + 1}: the key must be given as its SHA-256 hex")
        org = uuid.UUID(parts[3]) if len(parts) == 4 else DEMO_ORG_ID
        keys.append(ApiKey(name, role, digest, org))
    if len({k.name for k in keys}) != len(keys):
        raise ValueError("API_KEYS: key names must be unique")
    return keys


def authenticate(presented: str, keys: list[ApiKey]) -> Principal | None:
    digest = hash_key(presented)
    match: ApiKey | None = None
    for key in keys:  # compare against every key, in constant time, before deciding
        if hmac.compare_digest(digest, key.sha256):
            match = key
    if match is None:
        return None
    return Principal(match.name, match.role, match.org_id, authenticated=True)
