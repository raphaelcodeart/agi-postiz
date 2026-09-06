import base64
import ipaddress
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import httpx
from app.integrations.wordpress.exceptions import WordpressApiError, WordpressAuthError, WordpressUnsafeUrlError

REQUEST_TIMEOUT_SECONDS = 15.0


def validate_public_url(url: str) -> None:
    """
    SSRF guard: rejects non-HTTPS URLs and URLs whose resolved IP is loopback,
    private, link-local, reserved, or multicast. Called before every outbound
    request this client makes, not just on save, since DNS can change after a
    site is configured (DNS rebinding).
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise WordpressUnsafeUrlError("L'URL del sito WordPress deve usare HTTPS.")
    if not parsed.hostname:
        raise WordpressUnsafeUrlError("URL del sito WordPress non valido.")

    try:
        addrinfo = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise WordpressUnsafeUrlError(f"Impossibile risolvere l'host {parsed.hostname}.")

    for family, _, _, _, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise WordpressUnsafeUrlError(
                f"L'host {parsed.hostname} risolve a un indirizzo IP non pubblico ({ip}) - bloccato per sicurezza."
            )


def _auth_header(username: str, application_password: str) -> Dict[str, str]:
    # WordPress Application Passwords use plain HTTP Basic Auth over HTTPS
    # (developer.wordpress.org/rest-api/using-the-rest-api/authentication/#application-passwords).
    token = base64.b64encode(f"{username}:{application_password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _request(method: str, api_url: str, path: str, username: str, application_password: str, **kwargs) -> httpx.Response:
    base = api_url.rstrip("/")
    url = f"{base}{path}"
    validate_public_url(url)
    try:
        response = httpx.request(
            method,
            url,
            headers=_auth_header(username, application_password),
            timeout=REQUEST_TIMEOUT_SECONDS,
            **kwargs,
        )
    except httpx.RequestError as e:
        raise WordpressApiError(f"Errore di rete verso WordPress: {str(e)}", category="network_error")

    if response.status_code == 401:
        raise WordpressAuthError()
    if response.status_code == 404:
        raise WordpressApiError("Endpoint WordPress non trovato: verifica l'URL API.", status_code=404, category="not_found")
    if response.status_code >= 500:
        raise WordpressApiError(f"WordPress ha risposto con errore server ({response.status_code}).", status_code=response.status_code, category="server_error")
    if response.status_code >= 400:
        detail = response.text[:300]
        raise WordpressApiError(f"WordPress ha rifiutato la richiesta ({response.status_code}): {detail}", status_code=response.status_code, category="unknown")

    return response


def test_connection(api_url: str, username: str, application_password: str) -> Dict[str, Any]:
    """Verifies reachability + credentials via GET /wp/v2/users/me (requires auth, read-only)."""
    response = _request("GET", api_url, "/wp/v2/users/me?context=edit", username, application_password)
    data = response.json()
    return {"id": data.get("id"), "name": data.get("name"), "capabilities": data.get("capabilities", {})}


def get_categories(api_url: str, username: str, application_password: str) -> List[Dict[str, Any]]:
    response = _request("GET", api_url, "/wp/v2/categories?per_page=100&context=edit", username, application_password)
    return [{"id": c["id"], "name": c["name"]} for c in response.json()]


def get_authors(api_url: str, username: str, application_password: str) -> List[Dict[str, Any]]:
    response = _request("GET", api_url, "/wp/v2/users?per_page=100&context=edit", username, application_password)
    return [{"id": u["id"], "name": u["name"]} for u in response.json()]


def get_tags(api_url: str, username: str, application_password: str) -> List[Dict[str, Any]]:
    response = _request("GET", api_url, "/wp/v2/tags?per_page=100&context=edit", username, application_password)
    return [{"id": t["id"], "name": t["name"]} for t in response.json()]


def create_post(
    api_url: str,
    username: str,
    application_password: str,
    title: str,
    content: str,
    excerpt: Optional[str],
    status: str,
    author: Optional[int],
    category: Optional[int],
    tag_ids: Optional[List[int]],
    slug: Optional[str],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"title": title, "content": content, "status": status}
    if excerpt:
        payload["excerpt"] = excerpt
    if author:
        payload["author"] = author
    if category:
        payload["categories"] = [category]
    if tag_ids:
        payload["tags"] = tag_ids
    if slug:
        payload["slug"] = slug

    response = _request("POST", api_url, "/wp/v2/posts", username, application_password, json=payload)
    data = response.json()
    return {
        "id": data.get("id"),
        "link": data.get("link"),
        "status": data.get("status"),
    }


def update_post(
    api_url: str,
    username: str,
    application_password: str,
    wordpress_post_id: int,
    title: Optional[str] = None,
    content: Optional[str] = None,
    excerpt: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if title is not None:
        payload["title"] = title
    if content is not None:
        payload["content"] = content
    if excerpt is not None:
        payload["excerpt"] = excerpt
    if status is not None:
        payload["status"] = status

    response = _request("POST", api_url, f"/wp/v2/posts/{wordpress_post_id}", username, application_password, json=payload)
    data = response.json()
    return {"id": data.get("id"), "link": data.get("link"), "status": data.get("status")}
