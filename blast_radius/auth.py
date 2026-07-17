"""Access-gate primitives: a stateless signed cookie token and a small in-memory
brute-force throttle. No external dependencies — HMAC-SHA256 over stdlib.

The token is ``base64url(payload).base64url(hmac(secret, encoded))`` where the
payload is ``"<role>:<issued_unix_seconds>"``. Verification is constant-time and
rejects tampered, expired, or future-dated tokens. The secret never leaves the
server, so a client cannot forge or read a valid role."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

# Cookie carrying the signed access token. Lives here (not main.py) so API
# routers can check roles without importing the app module (circular import).
ACCESS_COOKIE = "br_access"


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _signature(secret: str, encoded: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256
    ).digest()
    return _b64encode(digest)


def issue_token(secret: str, role: str, *, issued_at: float | None = None) -> str:
    """Return a signed cookie value granting ``role``."""
    issued = int(time.time() if issued_at is None else issued_at)
    encoded = _b64encode(f"{role}:{issued}".encode("utf-8"))
    return f"{encoded}.{_signature(secret, encoded)}"


def verify_token(
    secret: str,
    token: str | None,
    *,
    max_age_seconds: int,
    now: float | None = None,
) -> str | None:
    """Return the role if ``token`` is a valid, unexpired signature, else None."""
    if not secret or not token or "." not in token:
        return None
    encoded, _, signature = token.partition(".")
    expected = _signature(secret, encoded)
    try:
        # compare_digest raises TypeError on non-ASCII str, and the signature
        # segment is attacker-controlled (raw Cookie bytes survive as latin-1).
        # Compare as bytes and fail closed on any non-ASCII rather than 500.
        matched = hmac.compare_digest(signature.encode("ascii"), expected.encode("ascii"))
    except UnicodeEncodeError:
        return None
    if not matched:
        return None
    try:
        role, separator, issued_text = _b64decode(encoded).decode("utf-8").rpartition(
            ":"
        )
        issued = int(issued_text)
    except (ValueError, UnicodeDecodeError):
        return None
    if not separator or not role:
        return None
    current = time.time() if now is None else now
    # Reject expired tokens and clearly future-dated ones (clock skew tolerance).
    if current - issued > max_age_seconds or issued > current + 60:
        return None
    return role


class AttemptLimiter:
    """Sliding-window per-key failure counter to blunt access-code guessing.

    Tracked keys are hard-capped so a client rotating identifiers cannot grow the
    table without bound (memory-exhaustion DoS); when full we sweep expired keys
    and, if still full, evict the least-recently-active one."""

    def __init__(
        self,
        max_attempts: int = 8,
        window_seconds: int = 300,
        max_keys: int = 4096,
    ) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._max_keys = max_keys
        self._hits: dict[str, list[float]] = {}

    def _live(self, hits: list[float], current: float) -> list[float]:
        return [t for t in hits if current - t < self._window]

    def _recent(self, key: str, current: float) -> list[float]:
        hits = self._live(self._hits.get(key, []), current)
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def _sweep(self, current: float) -> None:
        for key in list(self._hits):
            live = self._live(self._hits[key], current)
            if live:
                self._hits[key] = live
            else:
                self._hits.pop(key, None)

    def blocked(self, key: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        return len(self._recent(key, current)) >= self._max

    def record(self, key: str, *, now: float | None = None) -> None:
        current = time.time() if now is None else now
        if key not in self._hits and len(self._hits) >= self._max_keys:
            self._sweep(current)
            if len(self._hits) >= self._max_keys:
                oldest = min(self._hits, key=lambda existing: max(self._hits[existing]))
                self._hits.pop(oldest, None)
        self._hits.setdefault(key, []).append(current)
