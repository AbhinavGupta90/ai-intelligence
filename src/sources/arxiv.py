"""
Arxiv source — fetches recent AI/ML papers that have code/demos.
Uses the Arxiv API (no auth required).
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from src.sources.base import BaseSource, SourceItem
from src.config import SOURCES_CFG
from src.utils.http_client import fetch_text
from src.utils.logger import get_logger

log = get_logger("source.arxiv")


class ArxivSource(BaseSource):
    name = "arxiv"

    def __init__(self):
        self.cfg = SOURCES_CFG.get("arxiv", {})
        self.categories = self.cfg.get("categories", ["cs.AI", "cs.CL", "cs.CV"])
        self.must_have_code = self.cfg.get("must_have_code", True)

    async def fetch(self) -> list[SourceItem]:
        if not self.is_enabled(SOURCES_CFG):
            return []

        log.info("fetching", categories=self.categories)

        # Build Arxiv API query
        cat_query = " OR ".join(f"cat:{cat}" for cat in self.categories)
        url = "http://export.arxiv.org/api/query"
        params = {
            "search_query": cat_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": 100,
        }

        # Arxiv API returns Atom XML
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{url}?{param_str}"
        xml_text = await fetch_text(full_url)

        if not xml_text:
            log.warning("empty_response")
            return []

        items = self._parse_xml(xml_text)
        log.info("fetched", total_items=len(items))
        return items

    def _parse_xml(self, xml_text: str) -> list[SourceItem]:
        """Parse Arxiv Atom XML into SourceItems."""
        items = []
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            log.warning("xml_parse_error", error=str(e))
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=72)  # last 3 days

        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
            summary = (entry.findtext("atom:summary", "", ns) or "").strip()[:500]
            published = entry.findtext("atom:published", "", ns)

            # Parse date
            posted_at = None
            if published:
                try:
                    posted_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            # Skip old papers
            if posted_at and posted_at < cutoff:
                continue

            # Get links
            arxiv_url = ""
            pdf_url = ""
            for link in entry.findall("atom:link", ns):
                href = link.get("href", "")
                if link.get("title") == "pdf":
                    pdf_url = href
                elif "abs" in href:
                    arxiv_url = href

            if not arxiv_url:
                # Fallback: use ID
                arxiv_id = entry.findtext("atom:id", "", ns)
                arxiv_url = arxiv_id or ""

            # Check for code/demo links in summary
            has_code = bool(re.search(r"github\.com|gitlab\.com|huggingface\.co|demo", summary.lower()))

            if self.must_have_code and not has_code:
                # Also check comments field for code links
                comment = entry.findtext("arxiv:comment", "", ns) or ""
                has_code = bool(re.search(r"github\.com|code|implementation", comment.lower()))
                if not has_code:
                    continue

            # Extract authors
            authors = []
            for author in entry.findall("atom:author", ns):
                name = author.findtext("atom:name", "", ns)
                if name:
                    authors.append(name)

            # Extract categories
            categories = []
            for cat in entry.findall("atom:category", ns):
                term = cat.get("term", "")
                if term:
                    categories.append(term)

            item = SourceItem(
                title=title,
                url=arxiv_url,
                source="arxiv",
                engagement=0,  # Arxiv doesn't have upvotes — will be scored by content
                posted_at=posted_at,
                author=", ".join(authors[:3]),
                description=summary,
                tags=categories[:5],
                has_demo=has_code,
                is_open_source=has_code,
                external_url=pdf_url,
            )
            items.append(item)

        return items
