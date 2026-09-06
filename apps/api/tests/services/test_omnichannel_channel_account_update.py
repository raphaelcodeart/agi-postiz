import json
from types import SimpleNamespace
from app.core.security import EncryptionService
from app.schemas.schemas import OmniChannelAccountUpdate
from app.services.omnichannel_service import OmnichannelService


class _FakeDb:
    def commit(self):
        pass

    def refresh(self, obj):
        pass


def _account(channel="whatsapp", access_token_encrypted=None, external_account_id=None):
    return SimpleNamespace(
        channel=channel,
        name="Test",
        external_account_id=external_account_id,
        access_token_encrypted=access_token_encrypted,
        config_json=None,
    )


def test_update_with_no_credentials_leaves_them_untouched():
    account = _account(access_token_encrypted="unchanged-blob")
    OmnichannelService.update_channel_account(_FakeDb(), account, OmniChannelAccountUpdate())
    assert account.access_token_encrypted == "unchanged-blob"


def test_update_with_access_token_encrypts_meta_secret_pair():
    account = _account()
    OmnichannelService.update_channel_account(
        _FakeDb(), account, OmniChannelAccountUpdate(access_token="new-token", app_secret="new-secret")
    )
    decrypted = json.loads(EncryptionService.decrypt(account.access_token_encrypted))
    assert decrypted == {"access_token": "new-token", "app_secret": "new-secret"}


def test_update_app_secret_only_merges_into_existing_blob_without_retyping_token():
    existing_blob = EncryptionService.encrypt(json.dumps({"access_token": "old-token", "app_secret": "old-secret"}))
    account = _account(access_token_encrypted=existing_blob)
    OmnichannelService.update_channel_account(
        _FakeDb(), account, OmniChannelAccountUpdate(app_secret="rotated-secret")
    )
    decrypted = json.loads(EncryptionService.decrypt(account.access_token_encrypted))
    assert decrypted == {"access_token": "old-token", "app_secret": "rotated-secret"}


def test_update_external_account_id_for_whatsapp_phone_number():
    account = _account(external_account_id=None)
    OmnichannelService.update_channel_account(
        _FakeDb(), account, OmniChannelAccountUpdate(external_account_id="123456")
    )
    assert account.external_account_id == "123456"


def test_update_name_only_does_not_touch_credentials():
    account = _account(access_token_encrypted="unchanged-blob", external_account_id="keep-me")
    OmnichannelService.update_channel_account(_FakeDb(), account, OmniChannelAccountUpdate(name="Renamed"))
    assert account.name == "Renamed"
    assert account.access_token_encrypted == "unchanged-blob"
    assert account.external_account_id == "keep-me"


def test_toggle_disables_a_connected_channel():
    account = _account()
    account.status = "connected"
    OmnichannelService.toggle_channel_account_status(_FakeDb(), account)
    assert account.status == "disabled"


def test_toggle_re_enables_a_disabled_channel():
    account = _account()
    account.status = "disabled"
    OmnichannelService.toggle_channel_account_status(_FakeDb(), account)
    assert account.status == "connected"


def test_toggle_twice_returns_to_the_original_status():
    account = _account()
    account.status = "connected"
    OmnichannelService.toggle_channel_account_status(_FakeDb(), account)
    OmnichannelService.toggle_channel_account_status(_FakeDb(), account)
    assert account.status == "connected"
