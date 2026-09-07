"""Safe URL fetching and HTML text extraction."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Comment

from app.errors import ContentExtractionError, NetworkFetchError, ValidationError
from app.models import PageContent

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; BlagovaSweetsContentAgent/1.0; +https://blagova-sweets.local)"
)
MAX_HTML_BYTES = 2_000_000

REMOVE_TAGS = ("script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "iframe")
NOISE_SELECTORS = (
    "[role='navigation']",
    "[role='banner']",
    "[role='contentinfo']",
    ".cookie",
    ".cookies",
    "#cookie",
    ".menu",
    ".sidebar",
    ".breadcrumb",
    ".breadcrumbs",
    ".social",
    ".share",
    ".advertisement",
    ".ads",
)

BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
}


def validate_url(url: str) -> str:
    """Validate URL scheme and reject obvious SSRF targets before fetch."""
    cleaned = (url or "").strip()
    if not cleaned:
        raise ValidationError("Некорректный URL")

    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        raise ValidationError("Некорректный URL: разрешены только http и https")
    if not parsed.netloc or not parsed.hostname:
        raise ValidationError("Некорректный URL")

    host = parsed.hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host.endswith(".localhost"):
        raise ValidationError("Некорректный URL: локальные адреса запрещены")

    if _is_literal_private_ip(host):
        raise ValidationError("Некорректный URL: приватные адреса запрещены")

    return cleaned


def _is_literal_private_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_and_check_host(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise NetworkFetchError("Не удалось загрузить страницу") from exc

    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        if _is_literal_private_ip(ip_str):
            raise ValidationError("Некорректный URL: приватные адреса запрещены")


def fetch_html(url: str, *, timeout: float = 30.0) -> str:
    """Download HTML with timeout, redirects, and basic SSRF checks."""
    safe_url = validate_url(url)
    hostname = urlparse(safe_url).hostname
    assert hostname is not None
    _resolve_and_check_host(hostname)

    logger.info("Fetching page host=%s", hostname)
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            max_redirects=5,
        ) as client:
            response = client.get(safe_url)
            final_host = urlparse(str(response.url)).hostname
            if final_host:
                if final_host.lower() in BLOCKED_HOSTS or _is_literal_private_ip(final_host.lower()):
                    raise ValidationError("Некорректный URL: приватные адреса запрещены")
                _resolve_and_check_host(final_host)

            if response.status_code >= 500:
                raise NetworkFetchError("Не удалось загрузить страницу: ошибка сервера")
            if response.status_code >= 400:
                raise NetworkFetchError(f"Не удалось загрузить страницу: HTTP {response.status_code}")

            content_type = response.headers.get("content-type", "")
            if content_type and "html" not in content_type.lower() and "text/" not in content_type.lower():
                raise ContentExtractionError("На странице не найден текст")

            content_length = response.headers.get("content-length")
            if content_length and content_length.isdigit() and int(content_length) > MAX_HTML_BYTES:
                raise NetworkFetchError("Не удалось загрузить страницу: слишком большой ответ")

            raw = response.content or b""
            if len(raw) > MAX_HTML_BYTES:
                raise NetworkFetchError("Не удалось загрузить страницу: слишком большой ответ")

            html = raw.decode(response.encoding or "utf-8", errors="replace")
            if not html.strip():
                raise ContentExtractionError("На странице не найден текст")
            return html
    except (ValidationError, NetworkFetchError, ContentExtractionError):
        raise
    except httpx.TimeoutException as exc:
        logger.warning("Page fetch timeout")
        raise NetworkFetchError("Не удалось загрузить страницу: превышено время ожидания") from exc
    except httpx.RequestError as exc:
        logger.warning("Page fetch network error: %s", type(exc).__name__)
        raise NetworkFetchError("Не удалось загрузить страницу") from exc


def extract_page_content(html: str, url: str = "") -> PageContent:
    """Extract title, description, headings and main text from HTML."""
    if not (html or "").strip():
        raise ContentExtractionError("На странице не найден текст")

    soup = BeautifulSoup(html, "html.parser")

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    for tag in soup(REMOVE_TAGS):
        tag.decompose()
    for selector in NOISE_SELECTORS:
        for node in soup.select(selector):
            node.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = _normalize_space(soup.title.string)

    description = ""
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if meta and meta.get("content"):
        description = _normalize_space(str(meta["content"]))

    headings: list[str] = []
    for tag_name in ("h1", "h2"):
        for node in soup.find_all(tag_name):
            text = _normalize_space(node.get_text(" ", strip=True))
            if text and text not in headings:
                headings.append(text)

    main = soup.find("main") or soup.find("article") or soup.body or soup
    raw_text = main.get_text("\n", strip=True) if main else ""
    text = _clean_text_block(raw_text)

    if not any([title, description, headings, text]):
        raise ContentExtractionError("На странице не найден текст")

    if len(text) < 40 and not headings and not description:
        # Too little signal — still allow title-only pages with warning path
        if not title:
            raise ContentExtractionError("На странице не найден текст")

    return PageContent(
        url=url,
        title=title,
        description=description,
        headings=headings,
        text=text,
    )


def load_page(url: str, *, timeout: float = 30.0, max_chars: int = 6000) -> str:
    """Fetch URL and return compact normalized content for the LLM."""
    html = fetch_html(url, timeout=timeout)
    page = extract_page_content(html, url=url)
    compact = page.to_compact_text(max_chars=max_chars)
    if not compact.strip():
        raise ContentExtractionError("На странице не найден текст")
    logger.info("Page content extracted chars=%s", len(compact))
    return compact


def normalize_manual_text(text: str, *, max_chars: int = 6000) -> str:
    cleaned = _clean_text_block(text or "")
    if not cleaned:
        raise ContentExtractionError("Текст пустой или не содержит полезного содержания")
    if len(cleaned) > max_chars:
        cleaned = PageContent(url="", text=cleaned).to_compact_text(max_chars)
    return cleaned


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _clean_text_block(value: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in (value or "").splitlines():
        line = _normalize_space(raw_line)
        if not line:
            continue
        if len(line) < 2:
            continue
        key = line.lower()
        if key in seen:
            continue
        # Drop ultra-repetitive chrome
        if key in {"menu", "search", "home", "login", "sign in", "cookie settings"}:
            continue
        seen.add(key)
        lines.append(line)
    return "\n".join(lines).strip()
