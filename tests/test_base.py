import httpx
import pytest

from pipeline.collectors import base
from pipeline.collectors.base import RateLimitedError, polite_get


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda _: None)


def make_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_success_first_try():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text="hi")

    resp = polite_get("https://api.test/", client=make_client(handler))
    assert resp.text == "hi"
    assert len(calls) == 1


def test_retries_transient_errors_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(500)
        return httpx.Response(200, text="ok")

    resp = polite_get("https://api.test/", client=make_client(handler))
    assert resp.status_code == 200
    assert len(calls) == 3


def test_gives_up_after_max_attempts():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    with pytest.raises(httpx.HTTPStatusError):
        polite_get("https://api.test/", client=make_client(handler))
    assert len(calls) == 3


def test_429_stops_immediately_without_retries():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429)

    with pytest.raises(RateLimitedError):
        polite_get("https://api.test/", client=make_client(handler))
    assert len(calls) == 1
