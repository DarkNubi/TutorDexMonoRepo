#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _sign_hs256(message: bytes, secret: bytes) -> bytes:
    return hmac.new(secret, message, hashlib.sha256).digest()


def make_jwt(*, secret: str, role: str, issuer: str, ttl_seconds: int) -> str:
    now = int(time.time())
    header: Dict[str, Any] = {"alg": "HS256", "typ": "JWT"}
    payload: Dict[str, Any] = {
        "role": role,
        "iss": issuer,
        "iat": now,
        "exp": now + int(ttl_seconds),
    }

    header_b64 = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = _b64url(_sign_hs256(signing_input, secret.encode("utf-8")))
    return f"{header_b64}.{payload_b64}.{sig}"


def main() -> int:
    p = argparse.ArgumentParser(description="Generate an HS256 Supabase JWT for PostgREST role mapping (ops_agent).")
    p.add_argument("--secret", required=True, help="Supabase JWT secret (do not print/log this).")
    p.add_argument("--role", default="ops_agent", help="Role claim to embed (default: ops_agent).")
    p.add_argument("--issuer", default="supabase", help="Issuer claim (default: supabase).")
    p.add_argument("--ttl-seconds", type=int, default=3600, help="Token TTL in seconds (default: 3600).")
    args = p.parse_args()

    token = make_jwt(secret=str(args.secret), role=str(args.role), issuer=str(args.issuer), ttl_seconds=int(args.ttl_seconds))
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

