"""
Cosa deve esserci dentro le email che mandiamo.

Non si verifica l'estetica - quella si guarda con gli occhi - ma le cose che
rendono un messaggio utilizzabile e difendibile: il link ci deve essere, deve
esserci anche per chi legge solo testo, il consenso va dichiarato prima del
pulsante, e niente di quello che scrive l'utente deve poter diventare HTML.
"""
from app.services.email import templates


def test_welcome_carries_the_link_in_both_versions():
    """
    Chi legge in solo testo - e chi usa un client che sopprime i pulsanti - deve
    avere comunque un modo di entrare.
    """
    subject, html_body, text_body = templates.welcome_email(
        user_name="Marco Rossi", verify_url="https://portale.example/portal/verify-email?token=abc"
    )

    assert "AGI Post" in subject
    assert "https://portale.example/portal/verify-email?token=abc" in html_body
    assert "https://portale.example/portal/verify-email?token=abc" in text_body


def test_welcome_declares_the_consent_before_the_button():
    """
    Il clic vale come accettazione: se il testo non lo dice, e non linka i due
    documenti, il consenso raccolto non e' informato - e non e' difendibile.
    """
    _, html_body, text_body = templates.welcome_email(
        user_name="Marco", verify_url="https://portale.example/x"
    )

    consenso = html_body.index(">privacy</a>")
    pulsante = html_body.index("Conferma e attiva il mio accesso")
    assert consenso < pulsante

    assert "privacy" in text_body
    assert "termini e condizioni" in text_body


def test_user_name_cannot_inject_html():
    """
    Il nome arriva da un modulo pubblico. Se finisse nell'HTML senza escape, chi
    si registra deciderebbe il contenuto di un'email spedita dal nostro dominio.
    """
    _, html_body, _ = templates.welcome_email(
        user_name='<script>alert("x")</script>', verify_url="https://portale.example/x"
    )

    assert "<script>" not in html_body
    assert "&lt;script&gt;" in html_body


def test_reset_states_the_validity_and_the_way_out():
    """
    Le due cose che chi riceve un reset non richiesto ha bisogno di leggere:
    quanto dura, e che non deve fare niente.
    """
    subject, html_body, text_body = templates.password_reset_email(
        user_name="Marco", reset_url="https://portale.example/portal/reset-password?token=xyz"
    )

    assert "password" in subject.lower()
    assert "https://portale.example/portal/reset-password?token=xyz" in html_body
    assert "https://portale.example/portal/reset-password?token=xyz" in text_body
    assert "Non hai chiesto tu il reset" in text_body


def test_every_message_has_a_text_alternative_with_content():
    """Un HTML senza alternativa testuale e' un segnale che i filtri antispam pesano."""
    for _, _, text_body in (
        templates.welcome_email(user_name="Marco", verify_url="https://x.example/a"),
        templates.password_reset_email(user_name="Marco", reset_url="https://x.example/b"),
    ):
        assert len(text_body.strip()) > 200
        assert "<" not in text_body.replace("<https", "")


def test_logo_is_available_as_an_inline_attachment():
    """
    Il marchio viaggia dentro il messaggio: si vede anche a immagini remote
    bloccate, e non somiglia a un pixel di tracciamento.
    """
    logo = templates.logo_image()

    assert logo is not None, "manca apps/api/app/services/email/assets/agipost-logo.png"
    assert logo.content.startswith(b"\x89PNG")
    assert logo.cid == templates.LOGO_CID

    _, html_body, _ = templates.welcome_email(user_name="Marco", verify_url="https://x.example/a")
    assert f'src="cid:{templates.LOGO_CID}"' in html_body


# --- canali social insufficienti ---------------------------------------------

def test_channel_requirement_carries_the_link_and_the_channels_in_both_versions():
    subject, html_body, text_body = templates.channel_requirement_email(
        user_name="Marco Rossi",
        connected_channels=[("instagram", "marco.rossi")],
        required_channels=2,
        channels_url="https://portale.example/portal/channels",
    )

    assert "AGI Post" in subject
    assert "Manca un canale" in subject
    for body in (html_body, text_body):
        assert "https://portale.example/portal/channels" in body
        assert "Instagram" in body
        assert "marco.rossi" in body
        assert "almeno 2 canali" in body


def test_channel_requirement_speaks_differently_to_who_has_nothing():
    subject, html_body, text_body = templates.channel_requirement_email(
        user_name="Marco",
        connected_channels=[],
        required_channels=2,
        channels_url="https://portale.example/portal/channels",
    )

    assert "Collega i tuoi canali social" in subject
    assert "nessun canale" in html_body.lower()
    assert "nessun account social collegato" in text_body


def test_channel_requirement_never_turns_user_data_into_html():
    _, html_body, _ = templates.channel_requirement_email(
        user_name="<b>Marco</b>",
        connected_channels=[("instagram", "<script>alert(1)</script>")],
        required_channels=2,
        channels_url="https://portale.example/portal/channels",
    )
    assert "<b>Marco</b>" not in html_body
    assert "<script>" not in html_body
    assert "&lt;script&gt;" in html_body
