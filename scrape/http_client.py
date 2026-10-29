"""Polite HTTP access to the booking engine, with a disk cache.

Direct requests from many datacenter networks receive a Cloudflare hard
block (an immediate "Sorry, you have been blocked" page, not a JavaScript
challenge). When that happens, `auto` transport switches to the public
r.jina.ai reader, which fetches the same URL from another network and
returns the raw HTML. That fallback is a workaround for the block, not a
different price source.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path

from scrape.parse import is_cloudflare_block

DIRECT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    "Referer": "https://m.clubhotels.co.il/club-hotel-eilat?r=1",
}

READER_PREFIX = "https://r.jina.ai/"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    pass


class CloudflareBlocked(FetchError):
    pass


@dataclass
class FetchResult:
    url: str
    status: int
    body: str
    transport: str
    from_cache: bool


class Client:
    def __init__(
        self,
        *,
        cache_dir: Path,
        delay_seconds: float,
        retries: int,
        timeout: float,
        cache_hours: float,
        refresh: bool,
        transport: str,
    ) -> None:
        if transport not in {"auto", "direct", "reader"}:
            raise ValueError("transport must be auto, direct, or reader")
        self.cache_dir = cache_dir
        self.delay_seconds = delay_seconds
        self.retries = retries
        self.timeout = timeout
        self.cache_hours = cache_hours
        self.refresh = refresh
        self.transport = transport
        self._direct_blocked = transport == "reader"
        self._reader_notice_printed = False
        self._next_request_at = 0.0
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_html(self, url: str) -> FetchResult:
        cached = None if self.refresh else self._read_cache(url)
        if cached is not None:
            return cached
        self._throttle()
        if self.transport == "reader" or (self.transport == "auto" and self._direct_blocked):
            result = self._fetch_with_retries(url, transport="reader")
        elif self.transport == "direct":
            result = self._fetch_with_retries(url, transport="direct")
        else:
            try:
                result = self._fetch_with_retries(url, transport="direct")
            except CloudflareBlocked:
                self._direct_blocked = True
                self._announce_reader()
                self._throttle()
                result = self._fetch_with_retries(url, transport="reader")
        self._write_cache(result)
        return result

    def _announce_reader(self) -> None:
        if self._reader_notice_printed:
            return
        self._reader_notice_printed = True
        print(
            "Cloudflare blocked a direct request from this network "
            "(hard block, not a solvable challenge). "
            "Continuing via the r.jina.ai reader, which requests the same "
            "BE_Rooms.aspx URL from another IP. Use --transport direct on a "
            "network that is not blocked.",
            flush=True,
        )

    def _throttle(self) -> None:
        wait = self._next_request_at - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        jitter = random.uniform(0, min(0.4, self.delay_seconds * 0.25))
        self._next_request_at = time.monotonic() + self.delay_seconds + jitter

    def _fetch_with_retries(self, url: str, *, transport: str) -> FetchResult:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                status, body = _request(url, transport=transport, timeout=self.timeout)
            except (TimeoutError, urllib.error.URLError, http.client.HTTPException, OSError) as exc:
                last_error = exc
                _backoff(attempt)
                continue
            if is_cloudflare_block(status, body):
                if transport == "direct":
                    raise CloudflareBlocked(
                        "Cloudflare returned a hard block for BE_Rooms.aspx"
                    )
                last_error = CloudflareBlocked("reader response looked like a Cloudflare block")
                _backoff(attempt)
                continue
            if status in RETRY_STATUSES:
                last_error = FetchError(f"HTTP {status}")
                _backoff(attempt)
                continue
            if status != 200:
                raise FetchError(f"HTTP {status} for {url}")
            if transport == "reader" and "roomData" not in body and "no-results-text" not in body and "<html" not in body.lower():
                last_error = FetchError("reader did not return booking HTML")
                _backoff(attempt)
                continue
            return FetchResult(url, status, body, transport, False)
        raise FetchError(f"gave up after {self.retries} attempts for {url}: {last_error}")

    def post_json(self, url: str, payload: dict) -> FetchResult:
        """POST a JSON body and return the response text.

        Used for the availability calendar. This does not fall back to the
        HTML reader: a failure is the caller's signal to keep the old crawl.
        """
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        key = url + "\n" + encoded.decode("utf-8")
        cached = None if self.refresh else self._read_cache(key)
        if cached is not None:
            return FetchResult(url, cached.status, cached.body, cached.transport, True)
        self._throttle()
        result = self._post_with_retries(url, encoded)
        self._write_cache(result, key=key)
        return result

    def _post_with_retries(self, url: str, body: bytes) -> FetchResult:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                status, text = _post(url, body, timeout=self.timeout)
            except (TimeoutError, urllib.error.URLError, http.client.HTTPException, OSError) as exc:
                last_error = exc
                _backoff(attempt)
                continue
            if is_cloudflare_block(status, text) or status in RETRY_STATUSES:
                last_error = FetchError(f"HTTP {status}")
                _backoff(attempt)
                continue
            if status != 200:
                raise FetchError(f"HTTP {status} for {url}")
            return FetchResult(url, status, text, "direct", False)
        raise FetchError(f"gave up after {self.retries} attempts for {url}: {last_error}")

    def _cache_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / digest[:2] / f"{digest}.json"

    def _read_cache(self, key: str) -> FetchResult | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fetched = datetime.fromisoformat(payload["fetched_at"])
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            return None
        age_hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
        if age_hours > self.cache_hours:
            return None
        return FetchResult(
            url=key,
            status=int(payload["status"]),
            body=payload["body"],
            transport=payload.get("transport", "cache"),
            from_cache=True,
        )

    def _write_cache(self, result: FetchResult, *, key: str | None = None) -> None:
        path = self._cache_path(key or result.url)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "url": result.url,
            "status": result.status,
            "transport": result.transport,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "body": result.body,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _post(url: str, body: bytes, *, timeout: float) -> tuple[int, str]:
    headers = {
        "User-Agent": DIRECT_HEADERS["User-Agent"],
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": DIRECT_HEADERS["Accept-Language"],
        "Content-Type": "application/json; charset=utf-8",
        "Referer": "https://m.clubhotels.co.il",
        "Origin": "https://m.clubhotels.co.il",
    }
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _decode(response.read(), response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, _decode(exc.read(), exc.headers)


def _request(url: str, *, transport: str, timeout: float) -> tuple[int, str]:
    if transport == "reader":
        target = READER_PREFIX + url
        headers = {
            "User-Agent": DIRECT_HEADERS["User-Agent"],
            "Accept": "text/html",
            "X-Return-Format": "html",
        }
    else:
        target = url
        headers = dict(DIRECT_HEADERS)
    request = urllib.request.Request(target, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _decode(response.read(), response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, _decode(exc.read(), exc.headers)


def _decode(body: bytes, headers: Message) -> str:
    charset = headers.get_content_charset() or "utf-8"
    return body.decode(charset, errors="replace")


def _backoff(attempt: int) -> None:
    time.sleep(min(20.0, 1.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.4))
