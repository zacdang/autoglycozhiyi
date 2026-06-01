"""
Paper & SI PDF download utility.

Tries to automatically download the main paper PDF and SI PDF using:
  1. Unpaywall API  — checks if open-access and gets direct PDF URL
  2. Europe PMC     — alternative source for some papers
  3. Publisher patterns — known URL patterns for Wiley, ACS, RSC, Elsevier

For most chemistry journals (Wiley, ACS, Elsevier) automated downloads
are blocked by anti-bot measures even for open-access papers.  When that
happens, the utility prints the exact URL to click in your browser and
watches for the file to appear so it can update the paper config automatically.

Usage (CLI):
    python -m src.utils.download_papers --paper SIANTURI_2024
    python -m src.utils.download_papers --doi 10.1002/anie.202419516

Usage (from code):
    from src.utils.download_papers import ensure_pdfs
    ensure_pdfs(paper)   # updates paper.pdf_path / paper.si_path in place
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Optional

import requests

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_UNPAYWALL_EMAIL  = "zacfang20041102@gmail.com"   # required by Unpaywall ToS
_PAPER_DIR        = Path("data/raw/papers")
_METADATA_PATH    = Path("data/samples/sample_paper_metadata.json")
_DOWNLOAD_TIMEOUT = 30   # seconds per HTTP request


# ── Public API ────────────────────────────────────────────────────────────────

def ensure_pdfs(paper) -> None:
    """
    Try to auto-download any missing PDFs for *paper*.
    Updates paper.pdf_path and paper.si_path in place if new files are found.
    Also saves changes back to sample_paper_metadata.json.
    """
    doi = getattr(paper, "doi", None) or ""
    if not doi:
        logger.warning(f"[download_papers] No DOI for {paper.paper_id} — skipping auto-download")
        return

    paper_id = paper.paper_id
    _PAPER_DIR.mkdir(parents=True, exist_ok=True)

    info = _lookup_doi(doi)
    if not info:
        logger.warning(f"[download_papers] Could not resolve DOI {doi}")
        return

    logger.info(f"[download_papers] {paper_id}: is_oa={info['is_oa']}, publisher={info['publisher']}")

    # ── Main PDF ─────────────────────────────────────────────────────────────
    if not paper.pdf_path or not Path(paper.pdf_path).exists():
        dest = _PAPER_DIR / f"{paper_id.lower()}.pdf"
        ok = _try_download(info["main_pdf_url"], dest, label="main PDF")
        if ok:
            paper.pdf_path = str(dest)
            _save_metadata(paper)
            logger.info(f"[download_papers] Main PDF saved → {dest}")
        else:
            _print_manual_link("main PDF", info["main_pdf_url"], dest)

    # ── SI PDF ───────────────────────────────────────────────────────────────
    if not paper.si_path or not Path(paper.si_path).exists():
        si_url = _find_si_url(doi, info)
        if not si_url:
            logger.info(f"[download_papers] Could not find SI URL for {doi}")
            _print_no_si_found(doi, info)
            return

        dest = _PAPER_DIR / f"{paper_id.lower()}_SI.pdf"
        ok = _try_download(si_url, dest, label="SI PDF")
        if ok:
            paper.si_path = str(dest)
            _save_metadata(paper)
            logger.info(f"[download_papers] SI PDF saved → {dest}")
        else:
            _print_manual_link("SI PDF", si_url, dest)
            # Watch for the file (user may drop it in manually)
            _watch_for_file(dest, paper, field="si_path")


# ── DOI lookup ────────────────────────────────────────────────────────────────

def _lookup_doi(doi: str) -> Optional[dict]:
    """Query Unpaywall + CrossRef to get OA status, publisher, and PDF URL."""
    result = {
        "is_oa":        False,
        "publisher":    "unknown",
        "main_pdf_url": f"https://doi.org/{doi}",
        "landing_url":  f"https://doi.org/{doi}",
        "oa_license":   None,
    }

    # Unpaywall
    try:
        r = requests.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": _UNPAYWALL_EMAIL},
            timeout=_DOWNLOAD_TIMEOUT,
        )
        if r.status_code == 200:
            d = r.json()
            result["is_oa"]    = d.get("is_oa", False)
            result["publisher"] = d.get("publisher", "unknown")
            best = d.get("best_oa_location") or {}
            if best.get("url_for_pdf"):
                result["main_pdf_url"] = best["url_for_pdf"]
            if best.get("url_for_landing_page"):
                result["landing_url"] = best["url_for_landing_page"]
            result["oa_license"] = best.get("license")
    except Exception as exc:
        logger.debug(f"[download_papers] Unpaywall error: {exc}")

    # CrossRef for publisher confirmation
    try:
        r = requests.get(
            f"https://api.crossref.org/works/{doi}",
            timeout=_DOWNLOAD_TIMEOUT,
        )
        if r.status_code == 200:
            msg = r.json().get("message", {})
            if msg.get("publisher"):
                result["publisher"] = msg["publisher"]
    except Exception as exc:
        logger.debug(f"[download_papers] CrossRef error: {exc}")

    return result


# ── SI URL detection ──────────────────────────────────────────────────────────

def _find_si_url(doi: str, info: dict) -> Optional[str]:
    """
    Try to find the SI PDF URL using publisher-specific patterns.
    Returns a URL string or None.
    """
    publisher = (info.get("publisher") or "").lower()

    if "wiley" in publisher:
        return _si_url_wiley(doi)
    elif "american chemical" in publisher or "acs" in publisher:
        return _si_url_acs(doi)
    elif "royal society" in publisher or "rsc" in publisher:
        return _si_url_rsc(doi)
    elif "elsevier" in publisher:
        return _si_url_elsevier(doi)
    else:
        # Generic: try Wiley pattern as fallback, many publishers use similar URLs
        return _si_url_wiley(doi)


def _si_url_wiley(doi: str) -> Optional[str]:
    """
    Wiley SI URL pattern:
    https://onlinelibrary.wiley.com/action/downloadSupplement?doi={doi}&file={stem}-sup-0001-misc_information.pdf
    The file stem is derived from the DOI suffix: '10.1002/anie.202419516' → 'anie202419516'
    """
    # Extract just the article identifier from the DOI
    # e.g. 10.1002/anie.202419516 → anie202419516
    match = re.search(r'/([a-zA-Z]+)\.?(\d+)$', doi)
    if match:
        stem = match.group(1).lower() + match.group(2)
    else:
        stem = doi.replace("10.1002/", "").replace(".", "").replace("/", "")

    base = "https://onlinelibrary.wiley.com/action/downloadSupplement"
    # Try common SI filename patterns
    candidates = [
        f"{stem}-sup-0001-misc_information.pdf",
        f"{stem}-sup-0001-suppinfo.pdf",
        f"{stem}-sup-0001-supporting_information.pdf",
        f"{stem}-sup-0001.pdf",
    ]
    for filename in candidates:
        url = f"{base}?doi={doi}&file={filename}"
        try:
            r = requests.head(url, timeout=_DOWNLOAD_TIMEOUT,
                              headers={"User-Agent": _browser_ua()},
                              allow_redirects=True)
            if r.status_code == 200:
                return url
        except Exception:
            pass

    # Return the best guess anyway (user can click it)
    return f"{base}?doi={doi}&file={candidates[0]}"


def _si_url_acs(doi: str) -> Optional[str]:
    """
    ACS SI URL pattern: https://pubs.acs.org/doi/suppl/{doi}/suppl_file/...
    ACS landing page lists SI files — try to parse it.
    """
    landing = f"https://pubs.acs.org/doi/{doi}"
    try:
        r = requests.get(landing, timeout=_DOWNLOAD_TIMEOUT,
                         headers={"User-Agent": _browser_ua()})
        if r.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "suppl_file" in href and href.endswith(".pdf"):
                    return ("https://pubs.acs.org" + href
                            if href.startswith("/") else href)
    except Exception as exc:
        logger.debug(f"[download_papers] ACS SI scrape failed: {exc}")

    # Fallback: known pattern
    suffix = doi.replace("10.1021/", "").replace("/", "")
    return f"https://pubs.acs.org/doi/suppl/{doi}/suppl_file/{suffix}_si_001.pdf"


def _si_url_rsc(doi: str) -> Optional[str]:
    """RSC SI — usually linked from the article page."""
    landing = f"https://doi.org/{doi}"
    try:
        r = requests.get(landing, timeout=_DOWNLOAD_TIMEOUT,
                         headers={"User-Agent": _browser_ua()},
                         allow_redirects=True)
        if r.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True).lower()
                if ("supplement" in text or "supporting" in text) and ".pdf" in href:
                    return href if href.startswith("http") else "https://pubs.rsc.org" + href
    except Exception as exc:
        logger.debug(f"[download_papers] RSC SI scrape failed: {exc}")
    return None


def _si_url_elsevier(doi: str) -> Optional[str]:
    """Elsevier SI — mmc1.pdf pattern."""
    suffix = doi.replace("10.1016/", "").replace("/", "").replace(".", "")
    return f"https://www.sciencedirect.com/science/article/pii/{suffix}/mmc1.pdf"


# ── Download helper ───────────────────────────────────────────────────────────

def _try_download(url: str, dest: Path, label: str) -> bool:
    """
    Try to download *url* to *dest*.
    Returns True on success, False if blocked or failed.
    """
    if not url:
        return False
    try:
        r = requests.get(
            url,
            timeout=_DOWNLOAD_TIMEOUT,
            headers={"User-Agent": _browser_ua()},
            allow_redirects=True,
        )
        if r.status_code == 200 and b"%PDF" in r.content[:8]:
            dest.write_bytes(r.content)
            logger.info(f"[download_papers] Downloaded {label} ({len(r.content)//1024} KB) → {dest}")
            return True
        else:
            logger.debug(
                f"[download_papers] {label} blocked: HTTP {r.status_code} from {url}"
            )
            return False
    except Exception as exc:
        logger.debug(f"[download_papers] {label} download error: {exc}")
        return False


def _watch_for_file(dest: Path, paper, field: str, max_wait: int = 0) -> None:
    """
    If max_wait > 0, poll for the file to appear (for scripted workflows).
    When found, update paper and save metadata. Default is no-wait (just log).
    """
    if dest.exists():
        setattr(paper, field, str(dest))
        _save_metadata(paper)
        logger.info(f"[download_papers] Detected {dest.name} — updated {field}")
        return

    if max_wait > 0:
        print(f"\n⏳  Waiting for you to save the file to:\n    {dest.resolve()}\n")
        deadline = time.time() + max_wait
        while time.time() < deadline:
            time.sleep(2)
            if dest.exists():
                setattr(paper, field, str(dest))
                _save_metadata(paper)
                print(f"✅  Found {dest.name} — pipeline config updated automatically.\n")
                return
        print(f"⚠️   Timed out waiting for {dest.name}.")


# ── Metadata persistence ──────────────────────────────────────────────────────

def _save_metadata(paper) -> None:
    """Write updated pdf_path / si_path back to sample_paper_metadata.json."""
    try:
        metadata = json.loads(_METADATA_PATH.read_text(encoding="utf-8"))
        for entry in metadata:
            if entry.get("paper_id") == paper.paper_id:
                if paper.pdf_path:
                    entry["pdf_path"] = paper.pdf_path
                if paper.si_path:
                    entry["si_path"] = paper.si_path
                break
        _METADATA_PATH.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"[download_papers] Updated metadata for {paper.paper_id}")
    except Exception as exc:
        logger.warning(f"[download_papers] Could not update metadata: {exc}")


# ── User-facing messages ──────────────────────────────────────────────────────

def _print_manual_link(label: str, url: str, dest: Path) -> None:
    print(f"""
⚠️  Could not auto-download {label} (publisher blocks automated access).

   Click this link in your browser to download it:
   👉  {url}

   Then save the file here:
   📁  {dest.resolve()}

   The pipeline will detect it automatically on the next run.
""")


def _print_no_si_found(doi: str, info: dict) -> None:
    landing = info.get("landing_url") or f"https://doi.org/{doi}"
    print(f"""
ℹ️  Could not find SI PDF URL automatically.

   Go to the article page and look for 'Supporting Information':
   👉  {landing}

   Save the SI PDF as:
   📁  {(_PAPER_DIR / 'si.pdf').resolve()}

   Then add the path to data/samples/sample_paper_metadata.json:
       "si_path": "data/raw/papers/PAPER_ID_SI.pdf"
""")


def _browser_ua() -> str:
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )


# ── CLI entry point ───────────────────────────────────────────────────────────

def _load_paper(paper_id: str = None, doi: str = None):
    """Load a Paper from metadata by paper_id or DOI."""
    from src.models.paper import Paper
    metadata = json.loads(_METADATA_PATH.read_text(encoding="utf-8"))
    for entry in metadata:
        if paper_id and entry.get("paper_id") == paper_id:
            return Paper.from_dict(entry)
        if doi and entry.get("doi") == doi:
            return Paper.from_dict(entry)
    # If DOI given but not in metadata, create a temporary Paper
    if doi:
        pid = doi.replace("10.", "").replace("/", "_").replace(".", "_").upper()
        return Paper(paper_id=pid, doi=doi, title="", year=0,
                     pdf_path="", si_path=None)
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download paper and SI PDFs")
    parser.add_argument("--paper", help="Paper ID (e.g. SIANTURI_2024)")
    parser.add_argument("--doi",   help="DOI (e.g. 10.1002/anie.202419516)")
    parser.add_argument("--wait",  type=int, default=0,
                        help="Seconds to wait for manual download (0 = no wait)")
    args = parser.parse_args()

    paper = _load_paper(args.paper, args.doi)
    if not paper:
        print("Paper not found. Check --paper / --doi argument.")
        raise SystemExit(1)

    print(f"\n🔍  Looking up {paper.paper_id} (DOI: {paper.doi}) …\n")
    ensure_pdfs(paper)
