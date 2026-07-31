from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class FetchError(RuntimeError):
    """Raised when a source cannot be fetched within the security policy."""


@dataclass(frozen=True, slots=True)
class FetchResult:
    body: bytes
    final_url: str
    content_type: str
    retrieval: str


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, validate, max_redirects: int):
        super().__init__()
        self.validate = validate
        self.max_redirects = max_redirects

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        count = int(req.headers.get("X-Lagebericht-Redirects", "0")) + 1
        if count > self.max_redirects:
            raise FetchError("redirect limit exceeded")
        self.validate(target)
        redirected = super().redirect_request(req, fp, code, msg, headers, target)
        if redirected is not None:
            redirected.add_header("X-Lagebericht-Redirects", str(count))
        return redirected


class SafeFetcher:
    def __init__(
        self,
        *,
        max_bytes: int = 2_000_000,
        timeout_seconds: float = 15.0,
        max_redirects: int = 3,
        allow_test_http: bool = False,
        allow_private_hosts: bool = False,
    ):
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds
        self.max_redirects = max_redirects
        self.allow_test_http = allow_test_http
        self.allow_private_hosts = allow_private_hosts

    def _validate_url(self, url: str, allowed_domains: frozenset[str]) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "https" and not (self.allow_test_http and parsed.scheme == "http"):
            raise FetchError("source URL must use https")
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host or host not in {domain.lower().rstrip(".") for domain in allowed_domains}:
            raise FetchError(f"host {host!r} is not allowlisted")
        if parsed.username or parsed.password:
            raise FetchError("userinfo in source URLs is forbidden")
        if not self.allow_private_hosts:
            try:
                addresses = {row[4][0] for row in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
            except socket.gaierror as exc:
                raise FetchError(f"cannot resolve source host: {exc}") from exc
            for value in addresses:
                ip = ipaddress.ip_address(value)
                if not ip.is_global:
                    raise FetchError(f"source resolves to non-public address {ip}")

    def fetch(self, url: str, allowed_domains: frozenset[str]) -> FetchResult:
        validate = lambda target: self._validate_url(target, allowed_domains)
        validate(url)
        opener = build_opener(_SafeRedirectHandler(validate, self.max_redirects))
        request = Request(url, headers={
            "User-Agent": "PersoenlicherLagebericht/0.1 (+static personal briefing)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8",
        })
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                final_url = response.geturl()
                validate(final_url)
                length = response.headers.get("Content-Length")
                if length and int(length) > self.max_bytes:
                    raise FetchError("response exceeds size limit")
                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise FetchError("response exceeds size limit")
                content_type = response.headers.get_content_type()
                return FetchResult(body, final_url, content_type, "full")
        except FetchError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise FetchError(f"source request failed: {exc}") from exc

