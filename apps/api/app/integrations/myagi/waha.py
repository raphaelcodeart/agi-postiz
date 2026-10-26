"""
Client per WAHA (WhatsApp HTTP API, https://waha.devlike.pro), il motore del
gateway myAGI. Una sessione WAHA = un numero WhatsApp collegato = un canale
`whatsapp_myagi` dell'Omnichannel Responder; il nome della sessione deriva
dall'id del canale (`session_name_for`), cosi' il legame e' deterministico e
non serve salvarlo da nessuna parte.

Riferimenti (docs WAHA, lette il 2026-10-26):
  POST /api/sessions                 {"name", "start", "config": {"webhooks": [...]}}
  GET  /api/sessions/{name}          -> {"name", "status", "config", "me": {"id", "pushName"}, ...}
  POST /api/sessions/{name}/start|stop|logout|restart
  DELETE /api/sessions/{name}
  GET  /api/{name}/auth/qr           Accept: application/json -> {"mimetype", "data" (base64)}
  POST /api/sendText                 {"session", "chatId": "3933...@c.us", "text"}
  GET  /api/server/version
  header X-Api-Key, stati: STOPPED, STARTING, SCAN_QR_CODE, WORKING, FAILED

Il container non e' esposto fuori dalla rete Docker: ci parla solo l'API, e
il webhook che WAHA chiama e' l'URL interno dell'API (http://api:8000/...),
con il segreto del canale nel path e la firma HMAC-SHA512 del corpo
(`X-Webhook-Hmac`) come seconda prova - vedi connectors/whatsapp_myagi.py.
"""
import uuid
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.integrations.omnichannel.exceptions import ConnectorError

SESSION_PREFIX = "agi_"
# Stati WAHA -> stato del canale (omni_channel_accounts.status). "disabled" e'
# dell'amministratore e non viene mai sovrascritto.
STATUS_MAP = {
    "WORKING": "connected",
    "SCAN_QR_CODE": "pending",
    "STARTING": "pending",
    "STOPPED": "error",
    "FAILED": "error",
    "PASSKEY_REQUIRED": "pending",
}


def session_name_for(channel_account_id: uuid.UUID) -> str:
    return f"{SESSION_PREFIX}{channel_account_id.hex}"


def webhook_url_for(channel_account_id: uuid.UUID, webhook_secret: str) -> str:
    base = settings.MYAGI_WEBHOOK_BASE_URL.rstrip("/")
    return f"{base}/api/v1/omnichannel-responder/webhooks/myagi/{channel_account_id}/{webhook_secret}"


def is_configured() -> bool:
    return bool(settings.MYAGI_WA_URL)


class WahaClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, timeout: float = 20.0):
        self.base_url = (base_url or settings.MYAGI_WA_URL or "").rstrip("/")
        if not self.base_url:
            raise ConnectorError("Gateway myAGI non configurato (MYAGI_WA_URL)")
        self._api_key = api_key if api_key is not None else (settings.MYAGI_WA_API_KEY or "")
        self.timeout = timeout

    # ------------------------------------------------------------------ http
    def _headers(self, accept: str = "application/json") -> Dict[str, str]:
        headers = {"Accept": accept, "Content-Type": "application/json"}
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        return headers

    def _request(self, method: str, path: str, json: Optional[Dict[str, Any]] = None, ok_statuses=(200, 201), accept: str = "application/json") -> Any:
        try:
            response = httpx.request(method, f"{self.base_url}{path}", json=json, headers=self._headers(accept), timeout=self.timeout)
        except httpx.RequestError as e:
            raise ConnectorError(f"Gateway myAGI non raggiungibile: {e.__class__.__name__}") from e
        if response.status_code == 401:
            raise ConnectorError("Il gateway myAGI ha rifiutato la chiave (MYAGI_WA_API_KEY)", status_code=401)
        if response.status_code not in ok_statuses:
            raise ConnectorError(self._describe_error(response), status_code=response.status_code)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text[:500]}

    @staticmethod
    def _describe_error(response: httpx.Response) -> str:
        try:
            body = response.json()
            detail = body.get("message") or body.get("error") or body
            # Su sendText a sessione non pronta WAHA dice anche in che stato e':
            # e' l'informazione che serve all'operatore (riscansionare il QR
            # o riavviare), quindi la si riporta.
            if isinstance(body, dict) and body.get("status"):
                detail = f"{detail} (stato sessione: {body['status']})"
        except ValueError:
            detail = response.text[:300]
        return f"Il gateway myAGI ha risposto {response.status_code}: {detail}"

    # -------------------------------------------------------------- sessioni
    def server_version(self) -> Dict[str, Any]:
        data = self._request("GET", "/api/server/version")
        return data if isinstance(data, dict) else {"version": str(data)}

    def get_session(self, name: str) -> Optional[Dict[str, Any]]:
        """None se la sessione non esiste sul gateway."""
        try:
            data = self._request("GET", f"/api/sessions/{name}")
        except ConnectorError as e:
            if e.status_code == 404:
                return None
            raise
        return data if isinstance(data, dict) else None

    @staticmethod
    def _session_config(webhook_url: str, hmac_key: str) -> Dict[str, Any]:
        return {
            "webhooks": [
                {
                    "url": webhook_url,
                    # Solo i messaggi: ack, presenze e cambi di stato non sono
                    # cose che un cliente ha scritto.
                    "events": ["message"],
                    "hmac": {"key": hmac_key},
                    "retries": {"delaySeconds": 2, "attempts": 5, "policy": "linear"},
                }
            ],
        }

    def ensure_session(self, name: str, webhook_url: str, hmac_key: str) -> Dict[str, Any]:
        """
        Crea la sessione se manca, altrimenti la (ri)avvia. Idempotente: e'
        quello che la pagina myAGI chiama premendo "Avvia", anche piu' volte.
        """
        existing = self.get_session(name)
        if existing is None:
            created = self._request("POST", "/api/sessions", json={"name": name, "start": True, "config": self._session_config(webhook_url, hmac_key)})
            return created if isinstance(created, dict) else {"name": name, "status": "STARTING"}
        # PUT /api/sessions/{name} RIAVVIA la sessione (verificato dal vivo il
        # 2026-10-26): va fatto solo se il webhook e' cambiato davvero (URL o
        # segreto), altrimenti "Avvia" su un numero gia' collegato lo
        # scollegherebbe per qualche secondo a ogni click.
        wanted = self._session_config(webhook_url, hmac_key)
        current = ((existing.get("config") or {}).get("webhooks") or [{}])[0]
        if current.get("url") != webhook_url or ((current.get("hmac") or {}).get("key")) != hmac_key:
            updated = self._request("PUT", f"/api/sessions/{name}", json={"config": wanted}, ok_statuses=(200, 201, 204))
            return updated if isinstance(updated, dict) else existing
        if existing.get("status") in ("STOPPED", "FAILED"):
            started = self._request("POST", f"/api/sessions/{name}/start", ok_statuses=(200, 201, 204))
            return started if isinstance(started, dict) else existing
        return existing

    def restart_session(self, name: str) -> Any:
        return self._request("POST", f"/api/sessions/{name}/restart", ok_statuses=(200, 201, 204))

    def stop_session(self, name: str) -> Any:
        return self._request("POST", f"/api/sessions/{name}/stop", ok_statuses=(200, 201, 204))

    def logout_session(self, name: str) -> Any:
        """Scollega il telefono (come "Disconnetti" da WhatsApp Web): la sessione resta, servira' un nuovo QR."""
        return self._request("POST", f"/api/sessions/{name}/logout", ok_statuses=(200, 201, 204))

    def delete_session(self, name: str) -> None:
        try:
            self._request("DELETE", f"/api/sessions/{name}", ok_statuses=(200, 204))
        except ConnectorError as e:
            if e.status_code != 404:
                raise

    def qr_code(self, name: str) -> Optional[Dict[str, str]]:
        """
        {"mimetype": "image/png", "data": "<base64>"} oppure None se la sessione
        non e' in attesa di scansione (gia' collegata, ferma, in avvio).
        """
        try:
            data = self._request("GET", f"/api/{name}/auth/qr", accept="application/json")
        except ConnectorError as e:
            # WAHA risponde 422 quando lo stato non e' SCAN_QR_CODE.
            if e.status_code in (404, 422):
                return None
            raise
        if isinstance(data, dict) and data.get("data"):
            return {"mimetype": data.get("mimetype") or "image/png", "data": data["data"]}
        return None

    # ----------------------------------------------------------------- invio
    def send_text(self, name: str, chat_id: str, text: str) -> Dict[str, Any]:
        data = self._request("POST", "/api/sendText", json={"session": name, "chatId": chat_id, "text": text})
        return data if isinstance(data, dict) else {"raw": data}


def normalize_chat_id(external_user_id: str) -> str:
    """"393331234567" -> "393331234567@c.us"; un JID resta com'e'."""
    value = (external_user_id or "").strip()
    if "@" in value:
        return value
    digits = "".join(ch for ch in value if ch.isdigit())
    return f"{digits}@c.us"
