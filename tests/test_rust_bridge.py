import pytest

from app.services.rust_bridge import RustDexBridge


class StubAnalytics:
    def __init__(self, solana_payload=None, bnb_payload=None, raise_for=None):
        self.solana_payload = solana_payload
        self.bnb_payload = bnb_payload
        self.raise_for = raise_for or set()
        self.calls = []

    async def fetch_solana_payload(self, token):
        self.calls.append(("sol", token))
        if "sol" in self.raise_for:
            raise RuntimeError("boom")
        return self.solana_payload

    async def fetch_bnb_payload(self, token):
        self.calls.append(("bnb", token))
        if "bnb" in self.raise_for:
            raise RuntimeError("boom")
        return self.bnb_payload


@pytest.mark.asyncio
async def test_fetch_dex_payload_delegates_to_service():
    analytics = StubAnalytics(solana_payload={"pairs": [{"pairAddress": "abc"}]})
    bridge = RustDexBridge(analytics_service=analytics)

    payload = await bridge.fetch_dex_payload("So123")

    assert payload == {"pairs": [{"pairAddress": "abc"}]}
    assert analytics.calls == [("sol", "So123")]


@pytest.mark.asyncio
async def test_fetch_bnb_payload_returns_none_on_error():
    analytics = StubAnalytics(bnb_payload={"symbol": "ABC"}, raise_for={"bnb"})
    bridge = RustDexBridge(analytics_service=analytics)

    payload = await bridge.fetch_bnb_payload("0xdead")

    assert payload is None
    assert analytics.calls == [("bnb", "0xdead")]
