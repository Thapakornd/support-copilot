"""Polite, bounded downloads of allowlisted MongoDB Markdown documentation."""

import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from support_copilot.knowledge.prepare import digest

ORIGIN = "https://www.mongodb.com"
USER_AGENT = "SupportCopilotDemo/0.1"


def validate_url(url: str, *, robots: bool = False) -> None:
    parts = urlsplit(url)
    path = unquote(parts.path)
    if (
        parts.scheme != "https"
        or parts.netloc != "www.mongodb.com"
        or parts.fragment
        or "\\" in path
        or any(c in url for c in "\r\n\t")
        or any(segment in {".", ".."} for segment in path.split("/"))
    ):
        raise ValueError(f"URL outside approved documentation scope: {url}")
    if robots and path == "/robots.txt" and not parts.query:
        return
    if not path.startswith("/docs/") or not path.endswith(".md"):
        raise ValueError(f"Expected an official /docs/ Markdown URL: {url}")


class Downloader:
    def __init__(self, client: httpx.Client, delay: float = 1.0, sleep=time.sleep):
        self.client = client
        self.delay = delay
        self.sleep = sleep
        self.robots = None

    def _request(self, url: str) -> httpx.Response:
        for attempt in range(3):
            self.sleep(self.delay)
            try:
                response = self.client.get(
                    url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=30,
                    follow_redirects=False,
                )
            except httpx.RequestError:
                if attempt == 2:
                    raise
                self.sleep(2**attempt)
                continue
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                retry = response.headers.get("Retry-After", "")
                try:
                    wait = float(retry)
                except ValueError:
                    try:
                        wait = (
                            parsedate_to_datetime(retry) - datetime.now(UTC)
                        ).total_seconds()
                    except ValueError, TypeError, OverflowError:
                        wait = 2**attempt
                self.sleep(min(60, max(0, wait)))
                continue
            return response
        raise RuntimeError("Retry limit reached")

    def _check_robots(self, url: str) -> None:
        if self.robots is None:
            response = self._request(ORIGIN + "/robots.txt")
            if response.status_code != 200:
                raise ValueError(f"robots.txt unavailable: HTTP {response.status_code}")
            body = response.text
            if "<html" in body.lower() or "user-agent:" not in body.lower():
                raise ValueError("Invalid robots.txt response")
            self.robots = RobotFileParser()
            self.robots.parse(body.splitlines())
            # Never request faster than a publisher-specified crawl delay.
            self.delay = max(self.delay, self.robots.crawl_delay(USER_AGENT) or 0)
        browser_url = (
            urlsplit(url)
            ._replace(path=urlsplit(url).path.removesuffix(".md") + "/", query="")
            .geturl()
        )
        if not self.robots.can_fetch(USER_AGENT, url) or not self.robots.can_fetch(
            USER_AGENT, browser_url
        ):
            raise ValueError(f"robots.txt disallows {url}")

    def fetch(self, url: str) -> dict:
        current = url
        for _ in range(6):
            validate_url(current)
            self._check_robots(current)
            response = self._request(current)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("Redirect is missing Location")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            markdown = response.text
            return {
                "markdown": markdown,
                "resolved_fetch_url": current,
                "fetched_at": datetime.now(UTC).isoformat(),
                "status_code": response.status_code,
                "content_type": response.headers.get("Content-Type", ""),
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "raw_sha256": digest(markdown),
            }
        raise ValueError("Too many documentation redirects")
