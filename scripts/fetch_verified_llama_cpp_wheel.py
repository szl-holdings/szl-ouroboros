#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch the exact official llama-cpp-python CPU wheel for keyless review.

The bytes are installed only after HTTPS-host, elapsed-time, byte-size, and
SHA-256 verification. This helper has no model, secret, repository, deployment,
or provider mutation authority.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

WHEEL = "llama_cpp_python-0.3.35-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl"
URL = "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.35/" + WHEEL
EXPECTED_SIZE = 23_912_624
EXPECTED_SHA256 = "d172f3d3c8cdd194c3c47c71cb077ed6e61354a2d0f939ceeac0c8fd29999596"
ALLOWED_HOSTS = frozenset(
    {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
)
MAX_SECONDS = 120.0
SOCKET_TIMEOUT = 20.0


def validate_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        raise ValueError("wheel transport requires an approved HTTPS release host")


class ReleaseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def verify_existing(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size != EXPECTED_SIZE:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == EXPECTED_SHA256


def fetch_wheel(directory: Path) -> Path:
    validate_url(URL)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / WHEEL
    if verify_existing(target):
        return target

    temporary: Path | None = None
    started = time.monotonic()
    digest = hashlib.sha256()
    total = 0
    opener = urllib.request.build_opener(ReleaseRedirects())
    request = urllib.request.Request(
        URL,
        headers={"User-Agent": "SZL-Ouroboros-Open-Reviewer/1.0"},
    )
    try:
        with opener.open(request, timeout=SOCKET_TIMEOUT) as response:
            validate_url(response.geturl())
            if response.status != 200:
                raise ValueError("wheel transport did not return HTTP 200")
            with tempfile.NamedTemporaryFile(
                prefix=".open-reviewer-wheel-",
                dir=directory,
                delete=False,
            ) as out:
                temporary = Path(out.name)
                while True:
                    if time.monotonic() - started > MAX_SECONDS:
                        raise TimeoutError("wheel transport exceeded its elapsed-time budget")
                    chunk = response.read(min(1024 * 1024, EXPECTED_SIZE - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > EXPECTED_SIZE:
                        raise ValueError("wheel exceeds its pinned byte size")
                    digest.update(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
        if total != EXPECTED_SIZE:
            raise ValueError("wheel is truncated or has an unexpected byte size")
        if digest.hexdigest() != EXPECTED_SHA256:
            raise ValueError("wheel SHA-256 does not match the pinned release")
        os.replace(temporary, target)
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("/tmp/szl-wheels"))
    args = parser.parse_args()
    result = fetch_wheel(args.directory)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
