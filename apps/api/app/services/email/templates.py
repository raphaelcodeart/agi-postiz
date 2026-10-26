"""
Impaginazione e testi delle email transazionali.

Perche' HTML scritto a mano con le tabelle, nel 2026: i client email non sono
browser. Outlook su Windows impagina con il motore di Word (niente flex, niente
grid, ``border-radius`` ignorato), Gmail elimina i fogli di stile esterni e la
maggior parte di quelli interni, e molti client non caricano le immagini remote
finche' non glielo si chiede. Quello che sopravvive ovunque e' una tabella a
larghezza fissa con gli stili in linea; ogni scorciatoia moderna qui si paga con
un'email sfasciata su un client che non possiamo vedere.

Tre scelte che fanno la differenza su come arrivano davvero:

- il logo e' incorporato nel messaggio (``cid:``), non linkato: si vede anche a
  immagini remote bloccate e non somiglia a un pixel di tracciamento;
- ogni messaggio ha la sua versione a solo testo, che non e' un ripiego ma una
  parte: i filtri antispam guardano con sospetto un HTML senza alternativa;
- il pulsante e' una tabella con un colore di sfondo pieno, e sotto c'e' sempre
  il link in chiaro - chi legge da un client che sopprime i pulsanti deve poter
  comunque entrare.

Il colore viene dai token della landing (``.portal-skin`` in
apps/dashboard/app/globals.css): l'email e' la prima cosa che l'utente vede del
prodotto e deve somigliare alla pagina su cui atterra.
"""
import html
import pathlib
from typing import List, Optional, Tuple

from app.core.config import settings
from app.services.email.mailer import InlineImage

# --- Palette, dai token --pa-* della landing ------------------------------
INK = "#14131a"
INK_SOFT = "#3a3844"
MUTED = "#66636f"
LINE = "#e6e3dd"
BG = "#f4f2ee"
SURFACE = "#ffffff"
ACCENT = "#6c5ce0"
ACCENT_DARK = "#5344be"
GRADIENT = "linear-gradient(115deg, #7c6bd8 0%, #4fb3f5 34%, #f2685e 68%, #f6b25a 100%)"

FONT = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', "
    "Arial, sans-serif"
)

LOGO_CID = "agipost-logo"
_LOGO_PATH = pathlib.Path(__file__).with_name("assets") / "agipost-logo.png"


def logo_image() -> Optional[InlineImage]:
    """
    Il logo da incorporare, o None se il file non c'e'.

    Un asset mancante non deve impedire a un'email di conferma di partire: senza
    logo il messaggio resta leggibile e l'utente entra lo stesso, il che vale
    molto di piu' del marchio.
    """
    try:
        return InlineImage(cid=LOGO_CID, content=_LOGO_PATH.read_bytes(), subtype="png")
    except OSError:
        return None


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _button(url: str, label: str) -> str:
    """Pulsante a prova di client: tabella, sfondo pieno, nessuna dipendenza da CSS."""
    return f"""
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 auto;">
        <tr>
          <td align="center" bgcolor="{ACCENT}" style="border-radius:999px;">
            <a href="{_esc(url)}"
               style="display:inline-block;padding:15px 34px;font-family:{FONT};font-size:16px;
                      font-weight:600;line-height:1;color:#ffffff;text-decoration:none;
                      border-radius:999px;background-color:{ACCENT};border:1px solid {ACCENT_DARK};">
              {_esc(label)}
            </a>
          </td>
        </tr>
      </table>"""


def _fallback_link(url: str) -> str:
    """Il link in chiaro sotto il pulsante, per chi i pulsanti non li vede."""
    return f"""
      <p style="margin:22px 0 0;font-family:{FONT};font-size:13px;line-height:1.6;color:{MUTED};">
        Se il pulsante non funziona, copia e incolla questo indirizzo nel browser:<br>
        <a href="{_esc(url)}" style="color:{ACCENT};word-break:break-all;">{_esc(url)}</a>
      </p>"""


def _layout(*, preheader: str, body_html: str, footer_note: str) -> str:
    """
    Guscio comune: barra del gradiente, testata con il marchio, contenuto, pie'.

    ``preheader`` e' la riga che il client mostra in anteprima accanto
    all'oggetto. Se non la si scrive, il client la prende da solo - di solito
    pescando il primo testo utile, che spesso e' "Se il pulsante non funziona".
    """
    logo_html = (
        f'<img src="cid:{LOGO_CID}" width="46" height="46" alt="AGI Post" '
        f'style="display:block;border:0;outline:none;text-decoration:none;">'
    )

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
 "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <!-- Il messaggio e' disegnato su fondo chiaro: senza questo, i client in tema
       scuro invertono i colori a modo loro e il testo scuro finisce su sfondo
       scuro. -->
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>AGI Post</title>
</head>
<body style="margin:0;padding:0;background-color:{BG};">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;">
    {_esc(preheader)}
  </div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background-color:{BG};margin:0;padding:0;">
    <tr>
      <td align="center" style="padding:32px 16px;">

        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
               style="width:100%;max-width:600px;background-color:{SURFACE};
                      border:1px solid {LINE};border-radius:22px;overflow:hidden;">
          <!-- Filo del gradiente del marchio. Outlook ignora background-image e
               mostra il viola pieno di bgcolor: e' il ripiego voluto. -->
          <tr>
            <td bgcolor="{ACCENT}" height="5"
                style="height:5px;line-height:5px;font-size:0;background-image:{GRADIENT};">&nbsp;</td>
          </tr>

          <tr>
            <td style="padding:34px 40px 0;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="padding-right:12px;vertical-align:middle;">{logo_html}</td>
                  <td style="vertical-align:middle;">
                    <div style="font-family:{FONT};font-size:19px;font-weight:700;
                                letter-spacing:-0.01em;color:{INK};">AGI Post</div>
                    <div style="font-family:{FONT};font-size:12px;font-weight:500;
                                letter-spacing:0.06em;text-transform:uppercase;color:{MUTED};
                                padding-top:3px;">Ecosistema Mamify</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:26px 40px 36px;">{body_html}
            </td>
          </tr>

          <tr>
            <td style="padding:0 40px;">
              <div style="height:1px;line-height:1px;font-size:0;background-color:{LINE};">&nbsp;</div>
            </td>
          </tr>

          <tr>
            <td style="padding:22px 40px 30px;">
              <p style="margin:0 0 12px;font-family:{FONT};font-size:12.5px;line-height:1.65;color:{MUTED};">
                {footer_note}
              </p>
              <p style="margin:0;font-family:{FONT};font-size:12.5px;line-height:1.65;color:{MUTED};">
                © 2026 Condividiamo Ltd &nbsp;·&nbsp;
                <a href="{_esc(settings.TERMS_URL)}" style="color:{MUTED};text-decoration:underline;">Termini e condizioni</a>
                &nbsp;·&nbsp;
                <a href="{_esc(settings.PRIVACY_POLICY_URL)}" style="color:{MUTED};text-decoration:underline;">Privacy</a>
                &nbsp;·&nbsp;
                <a href="{_esc(settings.COOKIE_POLICY_URL)}" style="color:{MUTED};text-decoration:underline;">Cookie</a>
              </p>
            </td>
          </tr>
        </table>

        <p style="margin:18px 0 0;font-family:{FONT};font-size:11.5px;line-height:1.6;color:{MUTED};
                  max-width:600px;">
          Messaggio automatico inviato da AGI Post. Non è una comunicazione
          pubblicitaria: riguarda solo il tuo account.
        </p>

      </td>
    </tr>
  </table>
</body>
</html>"""


def _paragraph(text: str, *, size: str = "15.5px", color: str = INK_SOFT, top: str = "0") -> str:
    return (
        f'<p style="margin:{top} 0 16px;font-family:{FONT};font-size:{size};'
        f'line-height:1.68;color:{color};">{text}</p>'
    )


# --------------------------------------------------------------------------
# Benvenuto e conferma dell'indirizzo
# --------------------------------------------------------------------------

def welcome_email(
    *, user_name: str, verify_url: str, retroactive: bool = False
) -> Tuple[str, str, str]:
    """
    (oggetto, html, testo) del messaggio di benvenuto.

    ``retroactive`` e' la variante per chi era iscritto prima che conferma e
    consenso esistessero: stesso link e stesso consenso, ma niente "benvenuto,
    il tuo account e' stato creato" e niente giro della casa - lo conosce gia'.
    Gli si dice invece perche' riceve questa email adesso.

    Il consenso e' esplicito e informato: il pulsante dice cosa fa, la riga
    sopra dice cosa si accetta cliccandolo, e i due documenti sono linkati prima
    del pulsante, non dopo. Un consenso raccolto con un link che dice solo
    "conferma" non e' un consenso che si possa difendere.
    """
    first_name = _esc(user_name.strip().split(" ")[0] or user_name.strip())
    privacy = _esc(settings.PRIVACY_POLICY_URL)
    terms = _esc(settings.TERMS_URL)

    steps: List[Tuple[str, str]] = [
        ("Collega i tuoi account social",
         "Autorizzi tu, dalla tua area, e revochi quando vuoi."),
        ("Ricevi le campagne",
         "Le vedi prima che partano e decidi se esserci."),
        ("Guarda i numeri veri",
         "Copertura, interazioni e andamento canale per canale."),
    ]
    steps_html = "".join(
        f"""
              <tr>
                <td style="padding:0 0 14px;vertical-align:top;width:26px;">
                  <div style="width:22px;height:22px;border-radius:999px;background-color:#efecfc;
                              font-family:{FONT};font-size:12px;font-weight:700;color:{ACCENT_DARK};
                              text-align:center;line-height:22px;">{index}</div>
                </td>
                <td style="padding:0 0 14px 10px;vertical-align:top;">
                  <div style="font-family:{FONT};font-size:14.5px;font-weight:600;color:{INK};">{_esc(title)}</div>
                  <div style="font-family:{FONT};font-size:13.5px;line-height:1.6;color:{MUTED};padding-top:2px;">{_esc(detail)}</div>
                </td>
              </tr>"""
        for index, (title, detail) in enumerate(steps, start=1)
    )

    if retroactive:
        heading = f"Ciao {first_name}, ci serve una conferma"
        intro = (
            "Abbiamo introdotto l'informativa privacy e i termini e condizioni di "
            "AGI Post, che quando ti sei iscritto non c'erano ancora. Per continuare "
            "a usare il portale ti chiediamo di accettarli e di confermare che questo "
            "indirizzo è tuo: così potrai anche recuperare l'accesso da solo se un "
            "giorno perdi la password."
        )
        button_label = "Conferma e continua"
    else:
        heading = f"Ciao {first_name}, benvenuto in AGI Post"
        intro = (
            "Il tuo account è stato creato. Manca un ultimo passaggio: confermare che "
            "questo indirizzo è davvero tuo. Serve a noi per poterti avvisare, e a te "
            "per poter recuperare l'accesso se un giorno perdi la password."
        )
        button_label = "Conferma e attiva il mio accesso"

    # Il giro della casa serve a chi entra per la prima volta, non a chi usa il
    # portale da mesi.
    tour_html = "" if retroactive else f"""
              <div style="height:1px;line-height:1px;font-size:0;background-color:{LINE};margin:30px 0 24px;">&nbsp;</div>

              <div style="font-family:{FONT};font-size:12px;font-weight:600;letter-spacing:0.07em;
                          text-transform:uppercase;color:{MUTED};padding-bottom:14px;">
                Cosa ti aspetta dentro
              </div>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">{steps_html}
              </table>
"""

    body_html = f"""
              <h1 style="margin:0 0 14px;font-family:{FONT};font-size:25px;line-height:1.28;
                         font-weight:700;letter-spacing:-0.02em;color:{INK};">
                {heading}
              </h1>
              {_paragraph(intro)}

              <p style="margin:0 0 20px;font-family:{FONT};font-size:14px;line-height:1.65;color:{MUTED};">
                Cliccando il pulsante confermi il tuo indirizzo e accetti
                la <a href="{privacy}" style="color:{ACCENT};">privacy</a> e i
                <a href="{terms}" style="color:{ACCENT};">termini e condizioni</a>.
              </p>

              {_button(verify_url, button_label)}
              {_fallback_link(verify_url)}
{tour_html}
              <p style="margin:22px 0 0;font-family:{FONT};font-size:13.5px;line-height:1.65;color:{MUTED};">
                Il link resta valido {settings.EMAIL_VERIFICATION_TTL_HOURS} ore. Se scade,
                puoi chiederne un altro dalla schermata che trovi entrando nel portale.
              </p>"""

    plain_first_name = user_name.strip().split(" ")[0]
    if retroactive:
        text_intro = f"""Ciao {plain_first_name}, ci serve una conferma.

Abbiamo introdotto l'informativa privacy e i termini e condizioni di AGI Post,
che quando ti sei iscritto non c'erano ancora. Per continuare a usare il
portale ti chiediamo di accettarli e di confermare che questo indirizzo è tuo:
così potrai anche recuperare l'accesso da solo se un giorno perdi la password.

Apri questo link per confermare e continuare:"""
        text_tour = ""
        text_ignore = (
            "Se non hai un account su AGI Post, ignora questo messaggio."
        )
    else:
        text_intro = f"""Ciao {plain_first_name}, benvenuto in AGI Post.

Il tuo account è stato creato. Manca un ultimo passaggio: confermare che questo
indirizzo è davvero tuo. Serve a noi per poterti avvisare, e a te per poter
recuperare l'accesso se un giorno perdi la password.

Apri questo link per confermare l'indirizzo e attivare l'accesso:"""
        text_tour = """
Cosa ti aspetta dentro:
1. Collega i tuoi account social - autorizzi tu e revochi quando vuoi.
2. Ricevi le campagne - le vedi prima che partano e decidi se esserci.
3. Guarda i numeri veri - copertura, interazioni e andamento canale per canale.
"""
        text_ignore = (
            "Se non ti sei registrato tu, ignora questo messaggio: senza la conferma\n"
            "l'account resta chiuso."
        )

    text_body = f"""{text_intro}

{verify_url}

Aprendo il link confermi il tuo indirizzo e accetti la privacy
({settings.PRIVACY_POLICY_URL}) e i termini e condizioni ({settings.TERMS_URL}).

Il link resta valido {settings.EMAIL_VERIFICATION_TTL_HOURS} ore. Se scade puoi
chiederne un altro entrando nel portale.
{text_tour}
{text_ignore}

--
AGI Post - Ecosistema Mamify
{settings.PORTAL_PUBLIC_BASE_URL}/portal
"""

    if retroactive:
        preheader = "Accetta privacy e termini e continua a usare AGI Post."
        footer_note = (
            "Hai ricevuto questo messaggio perché hai un account su AGI Post e ne "
            "hai chiesto la conferma dal portale. Se non sei stato tu, ignoralo."
        )
        subject = "Conferma per continuare a usare AGI Post"
    else:
        preheader = "Conferma il tuo indirizzo e attiva l'accesso ad AGI Post."
        footer_note = (
            "Hai ricevuto questo messaggio perché qualcuno ha registrato questo "
            "indirizzo su AGI Post. Se non sei stato tu, ignoralo: senza la "
            "conferma l'account resta chiuso."
        )
        subject = "Conferma il tuo indirizzo - AGI Post"

    html_body = _layout(preheader=preheader, body_html=body_html, footer_note=footer_note)
    return subject, html_body, text_body


# --------------------------------------------------------------------------
# Reset della password
# --------------------------------------------------------------------------

def password_reset_email(*, user_name: str, reset_url: str) -> Tuple[str, str, str]:
    """(oggetto, html, testo) del messaggio di reimpostazione password."""
    first_name = _esc(user_name.strip().split(" ")[0] or user_name.strip())
    minutes = settings.PASSWORD_RESET_TTL_MINUTES

    body_html = f"""
              <h1 style="margin:0 0 14px;font-family:{FONT};font-size:25px;line-height:1.28;
                         font-weight:700;letter-spacing:-0.02em;color:{INK};">
                Reimposta la tua password
              </h1>
              {_paragraph(f"Ciao {first_name}, abbiamo ricevuto una richiesta di reimpostazione della password del tuo account AGI Post. Scegline una nuova dal link qui sotto.")}

              {_button(reset_url, "Scegli una nuova password")}
              {_fallback_link(reset_url)}

              <div style="background-color:#faf8f4;border:1px solid {LINE};border-radius:14px;
                          padding:16px 18px;margin:28px 0 0;">
                <p style="margin:0;font-family:{FONT};font-size:13.5px;line-height:1.65;color:{INK_SOFT};">
                  <strong style="color:{INK};">Il link vale {minutes} minuti</strong> e può essere usato
                  una volta sola. Se scade, richiedine un altro dalla pagina di accesso.
                </p>
              </div>

              <p style="margin:20px 0 0;font-family:{FONT};font-size:13.5px;line-height:1.65;color:{MUTED};">
                Non hai chiesto tu il reset? Non devi fare niente: la password attuale
                resta valida e questo link scade da solo. Se pero' ricevi questo
                messaggio più volte senza averlo richiesto, scrivici.
              </p>"""

    text_body = f"""Ciao {user_name.strip().split(' ')[0]},

abbiamo ricevuto una richiesta di reimpostazione della password del tuo account
AGI Post. Apri questo link per sceglierne una nuova:

{reset_url}

Il link vale {minutes} minuti e può essere usato una volta sola. Se scade,
richiedine un altro dalla pagina di accesso.

Non hai chiesto tu il reset? Non devi fare niente: la tua password attuale resta
valida e questo link scade da solo.

--
AGI Post - Ecosistema Mamify
{settings.PORTAL_PUBLIC_BASE_URL}/portal
"""

    html_body = _layout(
        preheader="Il link per scegliere una nuova password AGI Post.",
        body_html=body_html,
        footer_note=(
            "Hai ricevuto questo messaggio perché è stato chiesto un reset della "
            "password per questo indirizzo. Se non sei stato tu, la tua password "
            "attuale resta valida."
        ),
    )
    return "Reimposta la tua password - AGI Post", html_body, text_body


# --------------------------------------------------------------------------
# Canali social insufficienti
# --------------------------------------------------------------------------

# Nomi leggibili delle piattaforme, come li mostra la dashboard
# (components/shared/platform-badge.tsx). Buffer e bundle.social riportano X
# come "twitter": il nome che l'utente riconosce e' X.
_PLATFORM_LABELS = {
    "instagram": "Instagram",
    "facebook": "Facebook",
    "linkedin": "LinkedIn",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "twitter": "X (Twitter)",
    "threads": "Threads",
    "pinterest": "Pinterest",
    "bluesky": "Bluesky",
    "mastodon": "Mastodon",
    "googlebusiness": "Google Business",
}


def platform_label(platform: str) -> str:
    return _PLATFORM_LABELS.get(platform.lower(), platform.replace("_", " ").title())


def channel_requirement_email(
    *,
    user_name: str,
    connected_channels: List[Tuple[str, str]],
    required_channels: int,
    channels_url: str,
) -> Tuple[str, str, str]:
    """
    (oggetto, html, testo) dell'avviso "hai meno canali social del richiesto".

    ``connected_channels`` sono coppie (piattaforma, nome) dei canali che
    contano davvero - collegati e utilizzabili dalle campagne - e sono
    elencati nel messaggio: chi legge deve riconoscere subito cosa gli viene
    gia' contato e cosa manca, non ricevere un numero e basta. Con zero canali
    il tono e' "partiamo", con uno e' "manca poco": sono due situazioni
    diverse e un testo unico suonerebbe sbagliato a meta' dei destinatari.

    E' una comunicazione di servizio sullo stato dell'account, non marketing,
    e lo dice: e' quello che la distingue, per il destinatario e per i filtri.
    """
    first_name_raw = user_name.strip().split(" ")[0] or user_name.strip()
    first_name = _esc(first_name_raw)
    connected = len(connected_channels)
    # "Rispondi a questa email" ha senso solo se le risposte arrivano a una
    # casella letta da qualcuno (EMAIL_REPLY_TO); il mittente noreply non lo e'.
    help_channel = (
        "rispondi a questa email" if settings.EMAIL_REPLY_TO
        else "scrivi a chi gestisce il progetto"
    )
    missing = max(required_channels - connected, 0)

    if connected == 0:
        subject = "Collega i tuoi canali social per partire - AGI Post"
        heading = f"Ciao {first_name}, i tuoi canali social non sono ancora collegati"
        intro = (
            f"Il progetto AGI Post prevede che ogni promoter abbia almeno "
            f"<strong style=\"color:{INK};\">{required_channels} canali social</strong> collegati e attivi: "
            "sono il mezzo con cui le campagne raggiungono il tuo pubblico. Al momento al tuo "
            "account non risulta collegato nessun canale, quindi le campagne non possono "
            "includerti e i tuoi risultati restano fermi."
        )
        intro_text = (
            f"Il progetto AGI Post prevede che ogni promoter abbia almeno {required_channels} canali\n"
            "social collegati e attivi: sono il mezzo con cui le campagne raggiungono il tuo\n"
            "pubblico. Al momento al tuo account non risulta collegato nessun canale, quindi\n"
            "le campagne non possono includerti e i tuoi risultati restano fermi."
        )
        status_title = "Nessun canale collegato"
        preheader = f"Il progetto prevede almeno {required_channels} canali social: al momento non ne hai nessuno."
    else:
        subject = "Manca un canale social al tuo profilo - AGI Post" if missing == 1 else (
            f"Mancano {missing} canali social al tuo profilo - AGI Post"
        )
        heading = f"Ciao {first_name}, il tuo profilo non è ancora completo"
        intro = (
            f"Il progetto AGI Post prevede che ogni promoter abbia almeno "
            f"<strong style=\"color:{INK};\">{required_channels} canali social</strong> collegati e attivi. "
            f"Al momento al tuo account ne risulta {'uno solo' if connected == 1 else connected}: "
            f"{'ne manca ancora uno' if missing == 1 else f'ne mancano ancora {missing}'} perché le campagne "
            "possano raggiungere il tuo pubblico come previsto."
        )
        intro_text = (
            f"Il progetto AGI Post prevede che ogni promoter abbia almeno {required_channels} canali\n"
            f"social collegati e attivi. Al momento al tuo account ne risulta "
            f"{'uno solo' if connected == 1 else connected}:\n"
            f"{'ne manca ancora uno' if missing == 1 else f'ne mancano ancora {missing}'} perché le campagne "
            "possano raggiungere il tuo\npubblico come previsto."
        )
        status_title = "Un canale collegato" if connected == 1 else f"{connected} canali collegati"
        preheader = (
            f"Il progetto prevede almeno {required_channels} canali social: al momento ne hai "
            f"{'uno solo' if connected == 1 else connected}."
        )

    if connected_channels:
        channels_rows = "".join(
            f"""
                <tr>
                  <td style="padding:6px 0;font-family:{FONT};font-size:14px;color:{INK};">
                    <span style="display:inline-block;min-width:92px;font-weight:600;color:{ACCENT_DARK};">{_esc(platform_label(platform))}</span>
                    <span style="color:{INK_SOFT};">{_esc(name)}</span>
                  </td>
                </tr>"""
            for platform, name in connected_channels
        )
        channels_html = f"""
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top:8px;">{channels_rows}
                </table>"""
    else:
        channels_html = f"""
                <p style="margin:8px 0 0;font-family:{FONT};font-size:14px;line-height:1.6;color:{MUTED};">
                  Non risulta nessun account social collegato al tuo profilo.
                </p>"""

    status_html = f"""
              <div style="background-color:#fff7ed;border:1px solid #fed7aa;border-radius:14px;
                          padding:18px 20px;margin:6px 0 26px;">
                <div style="font-family:{FONT};font-size:12px;font-weight:600;letter-spacing:0.07em;
                            text-transform:uppercase;color:#b45309;">Situazione attuale</div>
                <div style="font-family:{FONT};font-size:17px;font-weight:700;color:{INK};padding-top:6px;">
                  {_esc(status_title)} <span style="font-weight:500;color:{MUTED};">· richiesti almeno {required_channels}</span>
                </div>{channels_html}
              </div>"""

    steps: List[Tuple[str, str]] = [
        ("Entra nel portale",
         "Con il tuo indirizzo email e la tua password. Se non hai ancora una password, "
         "registrati con questo stesso indirizzo: ritroverai il tuo account."),
        ("Apri la sezione “I tuoi canali”",
         f"Collega almeno {'un altro account' if missing == 1 else f'altri {missing} account'} social "
         "tra Instagram, Facebook, LinkedIn, TikTok, YouTube, X e Threads. Autorizzi tu, "
         "direttamente dal social, e puoi revocare quando vuoi."),
        ("Fatto",
         "Da quel momento rientri nelle campagne e i risultati dei tuoi canali compaiono nelle statistiche."),
    ]
    steps_html = "".join(
        f"""
              <tr>
                <td style="padding:0 0 14px;vertical-align:top;width:26px;">
                  <div style="width:22px;height:22px;border-radius:999px;background-color:#efecfc;
                              font-family:{FONT};font-size:12px;font-weight:700;color:{ACCENT_DARK};
                              text-align:center;line-height:22px;">{index}</div>
                </td>
                <td style="padding:0 0 14px 10px;vertical-align:top;">
                  <div style="font-family:{FONT};font-size:14.5px;font-weight:600;color:{INK};">{_esc(title)}</div>
                  <div style="font-family:{FONT};font-size:13.5px;line-height:1.6;color:{MUTED};padding-top:2px;">{_esc(detail)}</div>
                </td>
              </tr>"""
        for index, (title, detail) in enumerate(steps, start=1)
    )

    body_html = f"""
              <h1 style="margin:0 0 14px;font-family:{FONT};font-size:25px;line-height:1.28;
                         font-weight:700;letter-spacing:-0.02em;color:{INK};">
                {heading}
              </h1>
              {_paragraph(intro)}
              {status_html}

              <div style="font-family:{FONT};font-size:12px;font-weight:600;letter-spacing:0.07em;
                          text-transform:uppercase;color:{MUTED};padding-bottom:14px;">
                Cosa fare, in tre passi
              </div>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">{steps_html}
              </table>

              <div style="padding-top:10px;">
              {_button(channels_url, "Collega i tuoi canali")}
              </div>
              {_fallback_link(channels_url)}

              <p style="margin:26px 0 0;font-family:{FONT};font-size:13.5px;line-height:1.65;color:{MUTED};">
                Hai già collegato i canali o pensi che ci sia un errore? Può volerci qualche
                minuto perché la sincronizzazione li veda; se il problema resta, {_esc(help_channel)}
                e lo verifichiamo insieme.
              </p>"""

    if connected_channels:
        channels_text = "\n".join(
            f"  - {platform_label(platform)}: {name}" for platform, name in connected_channels
        )
    else:
        channels_text = "  - nessun account social collegato"

    text_body = f"""Ciao {first_name_raw},

{intro_text}

SITUAZIONE ATTUALE - {status_title} (richiesti almeno {required_channels})
{channels_text}

COSA FARE, IN TRE PASSI
1. Entra nel portale con il tuo indirizzo email e la tua password. Se non hai
   ancora una password, registrati con questo stesso indirizzo: ritroverai il
   tuo account.
2. Apri la sezione "I tuoi canali" e collega almeno {'un altro account' if missing == 1 else f'altri {missing} account'}
   social tra Instagram, Facebook, LinkedIn, TikTok, YouTube, X e Threads.
   Autorizzi tu, direttamente dal social, e puoi revocare quando vuoi.
3. Fatto: da quel momento rientri nelle campagne e i risultati dei tuoi canali
   compaiono nelle statistiche.

Collega i tuoi canali da qui:

{channels_url}

Hai già collegato i canali o pensi che ci sia un errore? Può volerci qualche
minuto perché la sincronizzazione li veda; se il problema resta, {help_channel}
e lo verifichiamo insieme.

--
AGI Post - Ecosistema Mamify
{settings.PORTAL_PUBLIC_BASE_URL}/portal
"""

    html_body = _layout(
        preheader=preheader,
        body_html=body_html,
        footer_note=(
            "Hai ricevuto questo messaggio perché il tuo account AGI Post ha meno canali "
            "social collegati di quanti il progetto ne richieda. È una comunicazione di "
            "servizio sullo stato del tuo account, non una pubblicità."
        ),
    )
    return subject, html_body, text_body
