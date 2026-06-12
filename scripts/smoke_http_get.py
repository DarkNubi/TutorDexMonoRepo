#!/usr/bin/env python3
from __future__ import annotations

import sys
import urllib.error
import urllib.request


def check(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            ok = status < 300
            print(("OK" if ok else "FAIL") + f": GET {url} status={status}")
            return ok
    except urllib.error.HTTPError as e:
        print(f"FAIL: GET {url} status={getattr(e, 'code', 'unknown')}")
        return False
    except Exception as e:
        print(f"FAIL: GET {url} error={e}")
        return False


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"Usage: {argv[0]} URL [URL2 ...]")
        return 2
    ok_all = True
    for url in argv[1:]:
        ok_all = check(url) and ok_all
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

