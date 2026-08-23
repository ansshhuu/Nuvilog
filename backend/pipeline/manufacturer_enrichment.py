"""
Step 8: manufacturer-site enrichment — scoped to what's free and provable.

WHY THIS SCOPE (read before extending it)
Gemini's Google Search grounding needs a paid/billing-enabled tier; the key
this project runs on is free-tier. Rather than build against something
ambiguous and possibly-billed, this stage only proves the concept where a
manufacturer URL is already known for free: both worked-example ground
truth rows carry a real one in the delivery format's MFR URL column. Fetch
that directly with requests + BeautifulSoup (both already in the TRD's
free-tool list) — no search step, no new API key, no new cost.

This is real, not a claim believed on paper: PDSH4816AF's MFR URL
(frigidaire.com) times out under a plain GET — checked live, twice, at 10s
and 25s. WDTS7024RZ's MFR URL (learnwhirlpool.com) returns real, useful
content, including the literal opening sentence of that row's real
MARKETING_DESCRIPTION ("Load more and run less with our quietest and
largest capacity dishwasher"). Both outcomes are handled the same way by
this module: fetch failure is not a crash, it's a `None` that downstream
code has to treat exactly like "no manufacturer page available" — see
`extract_attributes_from_page`'s docstring.

SOURCING RULE (enforced in code, not just described)
Manufacturer's own site only — this is the brief's guideline, not this
module's opinion. `_DISALLOWED_MARKETPLACE_DOMAINS` refuses to fetch known
marketplace/distributor domains even if a caller passes one by mistake;
no code path in this module falls back to one. There is deliberately no
"try Amazon/Grainger if the manufacturer site fails" branch — a fetch
failure stays a fetch failure.

REUSE, NOT NEW LOGIC
The extraction pass below is the extractor.py / confidence_engine.py
pattern already built for stage 2/4 of the document-ingestion pipeline,
applied to a new source: a fetched web page standing in for
`RawDocument.raw_text`, and the confirmed 15-label dishwasher scaffold
(dishwasher_schema.DISHWASHER_ATTRIBUTE_SCAFFOLD) standing in for a
category schema. `extract_fields` and `score_fields` are called completely
unmodified — nothing here re-implements the found/snippet/verbatim-check
discipline, it just points that existing discipline at a new kind of
document. That is also what gives this stage its honesty guarantee for
free: `score_fields` only trusts a value if it (or the LLM's snippet for
it) is genuinely present in the fetched page text, which is exactly "no
inventing specs from general knowledge just because the model recognizes
the product."
"""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from pipeline.confidence_engine import ScoredField, score_fields
from pipeline.dishwasher_schema import DISHWASHER_ATTRIBUTE_SCAFFOLD
from pipeline.extractor import extract_fields
from pipeline.llm_client import LLMClient
from pipeline.schema_registry import CategorySchema, FieldDef
from pipeline.types import RawDocument

FETCH_TIMEOUT_SECONDS = 10
MAX_PAGE_TEXT_CHARS = 20_000
MAX_REDIRECTS = 5
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Sourcing rule from the brief: manufacturer's own site only. This is a
# denylist, not the enforcement mechanism itself — the real enforcement is
# that no code path in this module or its callers ever substitutes one of
# these in when the manufacturer URL fails. The list exists so an accidental
# marketplace URL (e.g. a bad MFR URL value) fails loudly-but-gracefully
# instead of silently scraping a page the sourcing rule excludes.
_DISALLOWED_MARKETPLACE_DOMAINS: frozenset[str] = frozenset(
    {
        "amazon.com", "grainger.com", "ebay.com", "walmart.com",
        "homedepot.com", "lowes.com", "wayfair.com", "target.com",
        "bestbuy.com", "ferguson.com",
    }
)


def _is_disallowed_marketplace(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return any(host == d or host.endswith(f".{d}") for d in _DISALLOWED_MARKETPLACE_DOMAINS)


def _is_unsafe_target(url: str) -> bool:
    """SSRF guard: refuse anything that isn't a plain http(s) request to a
    public internet host.

    Not currently reachable by user input — both call sites pass a
    hardcoded MFR URL from the 2 known ground-truth rows — but
    fetch_manufacturer_page() takes a bare `url: str` with no caller-side
    restriction, so the moment this becomes an API parameter (a search
    step, a "try another URL" feature) this function is the only thing
    standing between that param and a GET against the cloud metadata
    endpoint (169.254.169.254), localhost, or an internal 10.x/172.16.x/
    192.168.x service. Cheap insurance now beats an incident later.

    Checks the scheme, then every IP the hostname actually resolves to
    (not just a literal-IP string check) — a hostname that resolves to a
    private/loopback/link-local/reserved address is rejected the same as
    a literal one, which is what stops "internal-service.local" or a
    DNS-rebinding attempt from sailing through a hostname-only check.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return True

    host = parsed.hostname
    if not host:
        return True

    try:
        addrs = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Can't resolve it, so it can't be fetched either — not a
        # security failure, but not a "safe" target either.
        return True

    for family, _, _, _, sockaddr in addrs:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return True
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True

    return False


def fetch_manufacturer_page(url: str) -> Optional[str]:
    """Plain GET on `url`, return the page's visible text — or None.

    None covers every failure mode on purpose (bad URL, timeout, 4xx/5xx,
    blocked, empty body, a disallowed marketplace domain, or a non-public
    target per `_is_unsafe_target`): this function never raises for a
    fetch problem, because a single dead manufacturer link must not crash
    a pipeline run. It's still a fetch problem worth knowing about, so
    callers should log/print `None` rather than silently treat it as
    "field genuinely absent" — those are different facts (see
    manufacturer_enrichment's script-level self-test for exactly that
    distinction).
    """
    if not url or not url.strip():
        return None
    if _is_disallowed_marketplace(url):
        return None
    if _is_unsafe_target(url):
        return None

    # Redirects are followed manually, one hop at a time, re-running both
    # safety checks on every hop's target before following it — a plain
    # `allow_redirects=True` would let a first hop that passes the checks
    # 302 straight into a private address, which is a well-known way to
    # bypass exactly this kind of guard. `allow_redirects=False` outright
    # was considered and rejected: this fetch already has documented live
    # flakiness (see module docstring — a real target has failed with a
    # timeout in one run and succeeded in another), and disabling
    # redirects entirely risks breaking a legitimate manufacturer-site
    # redirect (www normalization, http->https) that isn't a security
    # problem at all.
    current_url = url
    try:
        for _ in range(MAX_REDIRECTS):
            response = requests.get(
                current_url,
                timeout=FETCH_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=False,
            )
            if response.is_redirect:
                next_url = response.headers.get("Location")
                if not next_url:
                    return None
                current_url = urljoin(current_url, next_url)
                if _is_disallowed_marketplace(current_url) or _is_unsafe_target(current_url):
                    return None
                continue
            response.raise_for_status()
            break
        else:
            # Exhausted MAX_REDIRECTS without landing on a final response.
            return None
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True)).strip()
    if not text:
        return None
    return text[:MAX_PAGE_TEXT_CHARS]


def _dishwasher_extraction_schema() -> CategorySchema:
    """The confirmed 15-label scaffold, reused as extraction field specs.

    Pulls straight from DISHWASHER_ATTRIBUTE_SCAFFOLD — label names, the
    typical UOM, and the evidence text as the field description — rather
    than re-typing the label list a third time in this codebase.
    """
    return CategorySchema(
        category="dishwasher",
        display_name="Dishwasher",
        description=(
            "The 15-label scaffold confirmed in dishwasher_schema.py, reused here "
            "as the field set for manufacturer-page extraction."
        ),
        fields=[
            FieldDef(
                name=attr.label,
                type="string",
                unit=attr.typical_uom,
                description=attr.evidence,
            )
            for attr in DISHWASHER_ATTRIBUTE_SCAFFOLD
        ],
    )


@dataclass(frozen=True)
class PageExtractionResult:
    """One row's manufacturer-page extraction outcome."""

    mfg_part_num: str
    source_url: str
    page_fetched: bool
    scored_fields: tuple[ScoredField, ...]

    def verified_values(self, trusted_confidence: tuple[str, ...] = ("high", "medium")) -> dict[str, str]:
        """{label: value} for fields whose confidence is trustworthy.

        Same trust bar enrichment.py uses (TRUSTED_CONFIDENCE) — reused by
        value here rather than imported, so this module has no import-time
        dependency on the document-ingestion enrichment stage; the bar
        itself ("high" or "medium", never "unverified") is the thing being
        kept consistent, not the specific Python name.
        """
        return {
            f.field_name: str(f.value).strip()
            for f in self.scored_fields
            if f.confidence_level in trusted_confidence and f.value and str(f.value).strip()
        }


def extract_attributes_from_page(
    mfg_part_num: str,
    source_url: str,
    page_text: Optional[str],
    llm: Optional[LLMClient] = None,
) -> PageExtractionResult:
    """Run the extractor.py/confidence_engine.py pattern against a fetched
    manufacturer page for the 15 confirmed dishwasher attribute labels.

    `page_text` is what fetch_manufacturer_page() returned — None means the
    fetch failed, and this function reflects that honestly: every field
    comes back unresolved (confidence "unverified"), the same outcome as
    genuinely searching a real page and finding nothing, because from this
    function's point of view those two situations are indistinguishable
    and neither should be presented as a positive finding of absence. It
    does NOT skip the LLM call in that case either — it skips it, because
    calling the extractor with an empty document would only ever produce
    "not found" for every field at the cost of a wasted API call.
    """
    schema = _dishwasher_extraction_schema()

    if not page_text:
        unresolved = tuple(
            ScoredField(
                field_name=f.name,
                value=None,
                confidence_level="unverified",
                evidence_type="none",
                source_snippet=None,
                is_ai_generated=True,
            )
            for f in schema.fields
        )
        return PageExtractionResult(
            mfg_part_num=mfg_part_num, source_url=source_url, page_fetched=False, scored_fields=unresolved
        )

    llm = llm or LLMClient()
    raw_doc = RawDocument(source_type="url", source_ref=source_url, raw_text=page_text)
    extraction = extract_fields(raw_doc, schema, llm)
    scored = score_fields(extraction, raw_doc)

    return PageExtractionResult(
        mfg_part_num=mfg_part_num, source_url=source_url, page_fetched=True, scored_fields=tuple(scored)
    )
