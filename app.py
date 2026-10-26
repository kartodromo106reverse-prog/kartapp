from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import streamlit as st


APEX_FEED_URL = os.getenv("APEX_FEED_URL", "https://live.apex-timing.com/lignano-circuit/")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))


@dataclass
class FeedState:
    status: str = "idle"
    message: str = "Waiting for first response..."
    payload: str = ""
    last_updated: str | None = None
    error: str | None = None

    def ok(self, payload: str) -> None:
        self.status = "ok"
        self.message = "Feed reachable"
        self.payload = payload
        self.last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        self.error = None

    def error_state(self, error: str) -> None:
        self.status = "error"
        self.message = "Unable to reach Apex feed"
        self.payload = ""
        self.last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        self.error = str(error)


class FeedPoller:
    def __init__(self, feed_url: str, interval_seconds: int = POLL_INTERVAL_SECONDS):
        self.feed_url = feed_url
        self.interval_seconds = interval_seconds
        self._state = FeedState()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._poll_loop, name="apex-feed-poller", daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _poll_loop(self) -> None:
        self._fetch_once()
        while not self._stop_event.wait(self.interval_seconds):
            self._fetch_once()

    def _fetch_once(self) -> None:
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = client.get(
                    self.feed_url,
                    headers={"User-Agent": "kartapp-monitor/1.0"},
                )

            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code}")

            payload = response.text.strip() or "<empty response>"
            with self._lock:
                self._state.ok(payload)
        except Exception as exc:  # pragma: no cover - real network behavior may vary
            with self._lock:
                self._state.error_state(str(exc))

    def get_state(self) -> FeedState:
        with self._lock:
            return FeedState(
                status=self._state.status,
                message=self._state.message,
                payload=self._state.payload,
                last_updated=self._state.last_updated,
                error=self._state.error,
            )


@st.cache_resource(show_spinner=False)
def build_poller() -> FeedPoller:
    poller = FeedPoller(APEX_FEED_URL, interval_seconds=POLL_INTERVAL_SECONDS)
    poller.start()
    return poller


def render_app() -> None:
    st.set_page_config(page_title="Apex Feed Monitor", layout="wide")
    st.title("Apex live feed monitor")
    st.caption(f"Source: {APEX_FEED_URL}")

    poller = build_poller()
    state = poller.get_state()

    status_color = "#38b000" if state.status == "ok" else "#ef476f"
    st.markdown(
        f"<div style='padding: 1rem; border-radius: 0.75rem; background: #111827; color: white; border: 1px solid #2b2f3a;'>"
        f"<strong>Status:</strong> <span style='color:{status_color};'>{state.status.upper()}</span></div>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Current state", state.status.upper())
    with col2:
        st.metric("Last update", state.last_updated or "—")

    if state.error:
        st.warning(state.error)
    else:
        st.success(state.message)

    st.subheader("Latest payload")
    st.code(state.payload[:8000] if state.payload else "No payload available yet.", language="text")

    with st.expander("Debug"):
        st.write({
            "url": APEX_FEED_URL,
            "interval_seconds": POLL_INTERVAL_SECONDS,
            "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "status": state.status,
            "error": state.error,
            "last_updated": state.last_updated,
        })


if __name__ == "__main__":
    render_app()
