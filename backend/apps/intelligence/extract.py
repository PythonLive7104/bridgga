"""HTML extraction.

Turns fetched markup into the structured fields the company-understanding agent
reads. Two things matter here beyond parsing:

* **Sanitisation.** Scripts, styles and comments are dropped before any text is
  kept. Page content reaches an LLM prompt later, which makes a crawled page an
  untrusted input and a prompt-injection vector (PRD section 108). Stripping
  markup is not sufficient on its own -- the agent layer must also treat this
  text as data, never as instructions -- but it removes the obvious payloads.
* **Bounding.** Text is capped. An unbounded page would blow a model's context
  window and the per-request cost along with it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Comment

MAX_TEXT_CHARS = 40_000
MAX_LINKS = 200

_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")

# Paths worth visiting next when building a company profile (PRD section 26).
INTERESTING_PATH_HINTS = (
    "about",
    "pricing",
    "product",
    "products",
    "solutions",
    "features",
    "customers",
    "case-stud",
    "careers",
    "jobs",
    "contact",
    "blog",
    "docs",
    "integrations",
    "security",
)


@dataclass(slots=True)
class ExtractedPage:
    title: str = ""
    description: str = ""
    language: str = ""
    canonical_url: str = ""
    headings: list[str] = field(default_factory=list)
    text: str = ""
    internal_links: list[str] = field(default_factory=list)
    social_links: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    truncated: bool = False


_SOCIAL_HOSTS = (
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "github.com",
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def extract_page(html: str, *, base_url: str) -> ExtractedPage:
    soup = BeautifulSoup(html, "html.parser")

    # Order matters: remove executable and presentational nodes before reading
    # any text, so their contents never reach the output.
    for tag in soup(["script", "style", "noscript", "template", "iframe", "svg"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        comment.extract()

    page = ExtractedPage()

    if soup.title and soup.title.string:
        page.title = _clean(soup.title.string)[:300]

    description = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    if description:
        page.description = _clean(description.get("content", ""))[:600]

    html_tag = soup.find("html")
    if html_tag:
        page.language = _clean(html_tag.get("lang", ""))[:10]

    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical and canonical.get("href"):
        page.canonical_url = urljoin(base_url, canonical["href"])[:2048]

    page.headings = [
        _clean(heading.get_text(" "))[:200]
        for heading in soup.find_all(["h1", "h2", "h3"], limit=40)
        if heading.get_text(strip=True)
    ]

    raw_text = soup.get_text("\n")
    cleaned = _BLANK_LINES.sub("\n\n", _clean_multiline(raw_text))
    page.truncated = len(cleaned) > MAX_TEXT_CHARS
    page.text = cleaned[:MAX_TEXT_CHARS]

    page.internal_links, page.social_links = _collect_links(soup, base_url)
    page.emails = _collect_emails(cleaned)

    return page


def _clean(value: str) -> str:
    return _WHITESPACE.sub(" ", (value or "").replace("\xa0", " ")).strip()


def _clean_multiline(value: str) -> str:
    lines = (_clean(line) for line in (value or "").splitlines())
    return "\n".join(line for line in lines if line)


def _collect_links(soup: BeautifulSoup, base_url: str) -> tuple[list[str], list[str]]:
    base_host = (urlsplit(base_url).hostname or "").lower().removeprefix("www.")

    internal: list[str] = []
    social: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        # mailto:, tel: and javascript: are not pages to crawl.
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue

        absolute = urljoin(base_url, href)
        if urlsplit(absolute).scheme not in {"http", "https"}:
            continue

        absolute = absolute.split("#")[0]
        if absolute in seen:
            continue
        seen.add(absolute)

        host = (urlsplit(absolute).hostname or "").lower().removeprefix("www.")
        if any(host.endswith(social_host) for social_host in _SOCIAL_HOSTS):
            if len(social) < 20:
                social.append(absolute[:2048])
        elif host == base_host and len(internal) < MAX_LINKS:
            internal.append(absolute[:2048])

    # Rank the pages that actually describe a business first, so a shallow
    # crawl budget is spent on /pricing rather than /blog/page/47.
    internal.sort(key=_link_priority)
    return internal, social


def _link_priority(url: str) -> tuple[int, int]:
    path = urlsplit(url).path.lower()
    for index, hint in enumerate(INTERESTING_PATH_HINTS):
        if hint in path:
            return (0, index)
    return (1, len(path))


def _collect_emails(text: str) -> list[str]:
    found: list[str] = []
    for match in _EMAIL_RE.findall(text):
        candidate = match.lower().strip(".")
        # Image filenames and tracking pixels match the pattern often enough to
        # be worth excluding explicitly.
        if candidate.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
            continue
        if candidate not in found:
            found.append(candidate)
        if len(found) >= 20:
            break
    return found
