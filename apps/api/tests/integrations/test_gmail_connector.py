import email
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from app.integrations.omnichannel.connectors.gmail import GmailConnector


def _connector(name="Supporto Mamify"):
    account = SimpleNamespace(external_account_id="support@gmail.com", name=name, config_json=None)
    return GmailConnector(account, "app-password")


def test_normalize_plain_text_message():
    raw = (
        b"From: Mario Rossi <mario@example.com>\r\n"
        b"To: support@gmail.com\r\n"
        b"Subject: Aiuto con il mio ordine\r\n"
        b"Message-ID: <abc123@example.com>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        b"Ciao, ho un problema con il mio ordine.\r\n"
    )
    parsed = email.message_from_bytes(raw)
    normalized = _connector()._normalize(parsed)

    assert normalized.external_user_id == "mario@example.com"
    assert normalized.customer_display_name == "Mario Rossi"
    assert "problema" in normalized.text
    assert normalized.external_message_id == "<abc123@example.com>"
    assert normalized.metadata["subject"] == "Aiuto con il mio ordine"


def test_normalize_multipart_prefers_plain_text_over_html():
    raw = (
        b"From: Mario Rossi <mario@example.com>\r\n"
        b"Subject: Test\r\n"
        b'Content-Type: multipart/alternative; boundary="BOUND"\r\n\r\n'
        b"--BOUND\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        b"Versione testo semplice\r\n"
        b"--BOUND\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n\r\n"
        b"<p>Versione HTML</p>\r\n"
        b"--BOUND--\r\n"
    )
    parsed = email.message_from_bytes(raw)
    normalized = _connector()._normalize(parsed)

    assert normalized.text.strip() == "Versione testo semplice"
    assert "<p>Versione HTML</p>" in normalized.metadata["html_body"]


def test_normalize_returns_none_without_a_sender_address():
    raw = b"Subject: Nessun mittente\r\n\r\nCorpo\r\n"
    parsed = email.message_from_bytes(raw)
    assert _connector()._normalize(parsed) is None


def test_send_message_falls_back_to_channel_name_subject_without_reply_to():
    connector = _connector(name="Supporto Mamify")
    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance

    with patch("app.integrations.omnichannel.connectors.gmail.smtplib.SMTP_SSL", return_value=smtp_instance):
        connector.send_message("mario@example.com", "Ciao Mario, grazie per averci scritto")

    smtp_instance.login.assert_called_once_with("support@gmail.com", "app-password")
    sent_message = smtp_instance.send_message.call_args[0][0]
    assert sent_message["To"] == "mario@example.com"
    assert sent_message["Subject"] == "Re: Supporto Mamify"
    assert sent_message["In-Reply-To"] is None
    assert "Ciao Mario" in sent_message.get_content()


def test_send_message_threads_reply_using_reply_to_metadata():
    connector = _connector(name="Supporto Mamify")
    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    reply_to = {"subject": "Aiuto con il mio ordine", "message_id": "<original-123@example.com>"}

    with patch("app.integrations.omnichannel.connectors.gmail.smtplib.SMTP_SSL", return_value=smtp_instance):
        connector.send_message("mario@example.com", "Ciao Mario", reply_to=reply_to)

    sent_message = smtp_instance.send_message.call_args[0][0]
    assert sent_message["Subject"] == "Re: Aiuto con il mio ordine"
    assert sent_message["In-Reply-To"] == "<original-123@example.com>"
    assert sent_message["References"] == "<original-123@example.com>"


def test_send_message_does_not_double_prefix_subject_already_starting_with_re():
    connector = _connector(name="Supporto Mamify")
    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    reply_to = {"subject": "Re: Aiuto con il mio ordine", "message_id": "<msg-2@example.com>"}

    with patch("app.integrations.omnichannel.connectors.gmail.smtplib.SMTP_SSL", return_value=smtp_instance):
        connector.send_message("mario@example.com", "Ciao Mario", reply_to=reply_to)

    sent_message = smtp_instance.send_message.call_args[0][0]
    assert sent_message["Subject"] == "Re: Aiuto con il mio ordine"
