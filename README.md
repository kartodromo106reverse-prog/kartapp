from app import FeedPoller


class DummyResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


class DummyClient:
    def __init__(self, get_func):
        self._get_func = get_func

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def get(self, url, **kwargs):
        return self._get_func(url, **kwargs)


def test_feed_poller_marks_success(monkeypatch):
    def fake_get(url, **kwargs):
        assert url == "https://live.apex-timing.com/lignano-circuit/"
        return DummyResponse("<html>ok</html>")

    import app

    monkeypatch.setattr(app.httpx, "Client", lambda timeout=None: DummyClient(fake_get))

    poller = FeedPoller("https://live.apex-timing.com/lignano-circuit/", interval_seconds=1)
    poller._fetch_once()

    state = poller.get_state()
    assert state.status == "ok"
    assert "ok" in state.payload
    assert state.error is None


def test_feed_poller_marks_error(monkeypatch):
    def fake_get(url, **kwargs):
        raise RuntimeError("network down")

    import app

    monkeypatch.setattr(app.httpx, "Client", lambda timeout=None: DummyClient(fake_get))

    poller = FeedPoller("https://live.apex-timing.com/lignano-circuit/", interval_seconds=1)
    poller._fetch_once()

    state = poller.get_state()
    assert state.status == "error"
    assert "network down" in state.error
