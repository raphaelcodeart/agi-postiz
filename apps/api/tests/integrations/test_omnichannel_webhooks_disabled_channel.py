from types import SimpleNamespace
from unittest.mock import MagicMock
import app.api.v1.omnichannel_webhooks as webhooks_module


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeDb:
    def __init__(self, account):
        self._account = account

    def query(self, model):
        return _FakeQuery(self._account)


class _FakeRequest:
    def __init__(self):
        self.headers = {}

    async def json(self):
        return {"update_id": 1}

    async def body(self):
        return b"{}"


def _fake_connector():
    connector = MagicMock()
    connector.verify_webhook.return_value = True
    connector.parse_webhook.side_effect = AssertionError("must not parse a webhook body for a disabled channel")
    return connector


async def test_telegram_webhook_skips_ingestion_when_channel_disabled(monkeypatch):
    account = SimpleNamespace(id="acc-1", channel="telegram", status="disabled", webhook_secret="s", owner_id="owner-1")
    connector = _fake_connector()
    monkeypatch.setattr(webhooks_module, "get_connector", lambda acc: connector)
    ingest_called = MagicMock()
    monkeypatch.setattr(webhooks_module, "_ingest_and_trigger", ingest_called)

    result = await webhooks_module.telegram_webhook(
        channel_account_id="acc-1", request=_FakeRequest(), db=_FakeDb(account)
    )

    assert result == {"ok": True}
    ingest_called.assert_not_called()


async def test_telegram_webhook_ingests_when_channel_enabled(monkeypatch):
    account = SimpleNamespace(id="acc-1", channel="telegram", status="connected", webhook_secret="s", owner_id="owner-1")
    connector = MagicMock()
    connector.verify_webhook.return_value = True
    connector.parse_webhook.return_value = []
    monkeypatch.setattr(webhooks_module, "get_connector", lambda acc: connector)
    ingest_called = MagicMock(return_value=[])
    monkeypatch.setattr(webhooks_module, "_ingest_and_trigger", ingest_called)

    result = await webhooks_module.telegram_webhook(
        channel_account_id="acc-1", request=_FakeRequest(), db=_FakeDb(account)
    )

    assert result == {"ok": True}
    ingest_called.assert_called_once()


async def test_meta_webhook_receive_skips_ingestion_when_channel_disabled(monkeypatch):
    account = SimpleNamespace(id="acc-1", channel="whatsapp", status="disabled", webhook_secret="s", owner_id="owner-1")
    connector = _fake_connector()
    monkeypatch.setattr(webhooks_module, "get_connector", lambda acc: connector)
    ingest_called = MagicMock()
    monkeypatch.setattr(webhooks_module, "_ingest_and_trigger", ingest_called)

    result = await webhooks_module._meta_webhook_receive(
        "whatsapp", channel_account_id="acc-1", request=_FakeRequest(), db=_FakeDb(account)
    )

    assert result == {"ok": True}
    ingest_called.assert_not_called()
