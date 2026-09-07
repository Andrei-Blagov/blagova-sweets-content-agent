"""Tests for URL validation and HTML extraction."""

from __future__ import annotations

import pytest

from app.errors import ContentExtractionError, ValidationError
from app.webpage_parser import extract_page_content, normalize_manual_text, validate_url


def test_validate_url_accepts_https() -> None:
    assert validate_url("https://example.com/path") == "https://example.com/path"


def test_validate_url_rejects_file_scheme() -> None:
    with pytest.raises(ValidationError):
        validate_url("file:///etc/passwd")


def test_validate_url_rejects_localhost() -> None:
    with pytest.raises(ValidationError):
        validate_url("http://localhost/admin")
    with pytest.raises(ValidationError):
        validate_url("http://127.0.0.1/")
    with pytest.raises(ValidationError):
        validate_url("http://0.0.0.0/")
    with pytest.raises(ValidationError):
        validate_url("http://[::1]/")


def test_validate_url_rejects_private_ip() -> None:
    with pytest.raises(ValidationError):
        validate_url("http://192.168.0.10/secret")
    with pytest.raises(ValidationError):
        validate_url("http://10.0.0.5/")


def test_resolve_blocks_private_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.webpage_parser import _resolve_and_check_host

    monkeypatch.setattr(
        "app.webpage_parser.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(0, 0, 0, 0, ("10.1.2.3", 0))],
    )
    with pytest.raises(ValidationError):
        _resolve_and_check_host("public-looking.example")


def test_resolve_allows_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.webpage_parser import _resolve_and_check_host

    monkeypatch.setattr(
        "app.webpage_parser.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(0, 0, 0, 0, ("93.184.216.34", 0))],
    )
    _resolve_and_check_host("example.com")


def test_extract_page_content_strips_noise() -> None:
    html = """
    <html>
      <head>
        <title>Булочки с корицей</title>
        <meta name="description" content="Свежая выпечка" />
        <script>alert(1)</script>
        <style>.x{color:red}</style>
      </head>
      <body>
        <nav>Menu Home Login</nav>
        <footer>Contacts</footer>
        <h1>Булочки с корицей</h1>
        <h2>Сегодня в пекарне</h2>
        <p>Мягкие булочки с корицей и сахарной глазурью.</p>
        <script>void(0)</script>
      </body>
    </html>
    """
    page = extract_page_content(html, url="https://example.com")
    assert page.title == "Булочки с корицей"
    assert "Свежая выпечка" in page.description
    assert "Булочки с корицей" in page.headings
    assert "Мягкие булочки" in page.text
    assert "alert" not in page.text
    assert "color:red" not in page.text


def test_extract_empty_html_raises() -> None:
    with pytest.raises(ContentExtractionError):
        extract_page_content("   ")


def test_normalize_manual_text_empty() -> None:
    with pytest.raises(ContentExtractionError):
        normalize_manual_text("   ")


def test_normalize_manual_text_ok() -> None:
    text = normalize_manual_text("Сегодня испекли свежие круассаны.")
    assert "круассаны" in text
