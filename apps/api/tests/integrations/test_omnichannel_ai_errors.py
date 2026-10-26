"""
Cosa l'operatore legge quando OpenAI rifiuta la richiesta.

Il 2026-09-22 un 429 e' arrivato in dashboard come "internal server error":
la chiave era stata accettata dalla pagina Impostazioni (validate_api_key
elenca i modelli, cosa che funziona anche a credito zero) e l'account non
aveva piu' credito. Il motivo vero stava nel corpo della risposta di OpenAI,
che scartavamo. Le proprieta' inchiodate qui non sono "la chiamata
funziona", ma "il motivo del rifiuto arriva fino allo schermo".
"""
import json

import pytest

from app.integrations.omnichannel.ai import _describe_openai_error


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload


def _openai_error(message, code=None, type_="invalid_request_error"):
    return {"error": {"message": message, "type": type_, "code": code}}


def test_credito_esaurito_lo_dice_e_indica_dove_ricaricare():
    """Payload reale, catturato in produzione il 2026-09-22. Si noti che
    `code` e `type` NON coincidono: leggerne uno solo (`code or type`) fa
    cadere questo caso nel ramo del limite di frequenza, che consiglia di
    aspettare invece di ricaricare."""
    response = _FakeResponse(
        {
            "error": {
                "message": (
                    "You have no credits remaining. Add credits to continue using the API "
                    "at https://platform.openai.com/settings/organization/billing/."
                ),
                "type": "insufficient_quota",
                "param": None,
                "code": "credit_balance_exhausted",
            }
        },
        status_code=429,
    )

    detail = _describe_openai_error(response)

    assert "credito" in detail.lower()
    assert "billing" in detail
    assert "frequenza" not in detail


def test_anche_la_forma_con_solo_insufficient_quota_e_riconosciuta():
    """L'altra forma documentata da OpenAI, con il marcatore su `code`."""
    response = _FakeResponse(
        _openai_error(
            "You exceeded your current quota, please check your plan and billing details.",
            code="insufficient_quota",
            type_="insufficient_quota",
        ),
        status_code=429,
    )

    assert "credito" in _describe_openai_error(response).lower()


def test_un_429_di_frequenza_non_viene_scambiato_per_credito_esaurito():
    """Le due cose hanno lo stesso codice HTTP ma rimedi opposti: aspettare
    qualche secondo, oppure ricaricare l'account."""
    response = _FakeResponse(
        _openai_error("Rate limit reached for gpt-4o-mini", code="rate_limit_exceeded", type_="rate_limit_error"),
        status_code=429,
    )

    detail = _describe_openai_error(response)

    assert "frequenza" in detail
    assert "credito" not in detail.lower()
    assert "Rate limit reached for gpt-4o-mini" in detail


def test_chiave_rifiutata_manda_alle_impostazioni():
    response = _FakeResponse(_openai_error("Incorrect API key provided"), status_code=401)

    detail = _describe_openai_error(response)

    assert "401" in detail
    assert "Impostazioni" in detail


def test_un_errore_qualsiasi_riporta_il_messaggio_di_openai():
    response = _FakeResponse(_openai_error("The model `gpt-4o-mini` does not exist"), status_code=404)

    detail = _describe_openai_error(response)

    assert "404" in detail
    assert "does not exist" in detail


def test_corpo_non_json_non_fa_esplodere_la_descrizione():
    """Un 502 dal proxy davanti a OpenAI risponde HTML, non JSON."""
    detail = _describe_openai_error(_FakeResponse("<html>Bad Gateway</html>", status_code=502))

    assert detail == "OpenAI ha risposto con errore (502)"


def test_corpo_json_senza_campo_error_ricade_sul_solo_codice():
    detail = _describe_openai_error(_FakeResponse({"detail": "boh"}, status_code=500))

    assert detail == "OpenAI ha risposto con errore (500)"
