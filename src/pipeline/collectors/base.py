import ssl
import time

import httpx

USER_AGENT = "fuel-price-radar/1.0 (+github.com/isistomin/fuel-price-radar)"
MAX_ATTEMPTS = 3
BACKOFF_S = [1.5, 3.0]  # pauses between attempts


def _ssl_context() -> ssl.SSLContext:
    # sedeaplicaciones.minetur.gob.es speaks only TLS 1.2 with legacy
    # RSA-key-exchange ciphers; OpenSSL 3 excludes those at the default
    # security level, so the gov server drops the handshake.
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    return ctx


class RateLimitedError(RuntimeError):
    """Server told us to slow down (HTTP 429). Do not retry."""


def polite_get(url: str, *, client: httpx.Client | None = None) -> httpx.Response:
    """GET with our User-Agent and retries; raises RateLimitedError on 429."""
    own_client = client is None
    if own_client:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=60, verify=_ssl_context()
        )
    try:
        last_exc: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = client.get(url)
                if resp.status_code == 429:
                    raise RateLimitedError(f"got 429 from {url}")
                resp.raise_for_status()
                return resp
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt < MAX_ATTEMPTS:
                    time.sleep(BACKOFF_S[attempt - 1])
        raise last_exc
    finally:
        if own_client:
            client.close()
