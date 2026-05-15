import re
from typing import Optional
from loguru import logger
from scrapers.base_scraper import BaseScraper

# BE FORWARD car detail URL: /{make_slug}/{model_slug}/{stock_code}/id/{listing_id}/
_CAR_URL_RE = re.compile(r'^/([a-z][a-z0-9\-]*)/([a-z0-9][a-z0-9\-]*)/([a-z0-9]+)/id/(\d+)/$')

_MILEAGE_RE = re.compile(r'Mileage\s+([\d,]+)\s*km', re.IGNORECASE)
_YEAR_RE    = re.compile(r'Year\s+([\d/]+)', re.IGNORECASE)
_ENGINE_RE  = re.compile(r'Engine\s+([\d,]+)\s*cc', re.IGNORECASE)
_TRANS_RE   = re.compile(r'Trans\.\s+([A-Z]+)', re.IGNORECASE)
_FUEL_RE    = re.compile(r'Fuel\s+(Petrol|Diesel|Hybrid|Electric|LPG|CNG|Gasoline)', re.IGNORECASE)
_COLOR_RE   = re.compile(r'Color\s+(\w+)', re.IGNORECASE)
_REFNO_RE   = re.compile(r'Ref\s*No\.?\s+([A-Z0-9]+)', re.IGNORECASE)

MAKE_SLUG_MAP = {
    "toyota": "Toyota", "honda": "Honda", "nissan": "Nissan",
    "mazda": "Mazda", "subaru": "Subaru", "mitsubishi": "Mitsubishi",
    "suzuki": "Suzuki", "daihatsu": "Daihatsu", "isuzu": "Isuzu",
    "lexus": "Lexus", "infiniti": "Infiniti", "jeep": "Jeep",
    "mercedes-benz": "Mercedes-Benz", "bmw": "BMW", "volkswagen": "Volkswagen",
    "land-rover": "Land Rover", "mini": "MINI", "volvo": "Volvo",
}


class BeForwardScraper(BaseScraper):
    PLATFORM_NAME = "BE FORWARD"
    BASE_URL = "https://www.beforward.jp"

    def _build_url(self, min_year: int, page: int) -> str:
        return (
            f"{self.BASE_URL}/stocklist"
            f"?MINYEAR={min_year}&MAXYEAR=9999&STEERING=RHD&page={page}&ipp=30"
        )

    def _parse_card(self, card, make_slug: str = "") -> Optional[dict]:
        try:
            # Skip sold cards
            if card.find(class_="price-col-sold"):
                return None

            # Find the car detail link — look for vehicle-url-link first (more reliable),
            # then fall back to any href matching the car URL pattern
            link = card.find("a", class_="vehicle-url-link") or card.find("a", href=_CAR_URL_RE)
            if not link:
                return None

            href = link.get("href", "")
            m = _CAR_URL_RE.match(href)
            if not m:
                return None

            card_make_slug, model_slug, stock_code, listing_id = m.groups()

            if make_slug and card_make_slug != make_slug:
                return None

            data = {
                "source_platform": self.PLATFORM_NAME,
                "url": self.BASE_URL + href,
                "external_id": stock_code.upper(),
                "make": MAKE_SLUG_MAP.get(card_make_slug, card_make_slug.replace("-", " ").title()),
                "model": model_slug.replace("-", " ").title(),
            }

            text = card.get_text(" ", strip=True)

            ref_m = _REFNO_RE.search(text)
            if ref_m:
                data["external_id"] = ref_m.group(1)

            # Price: prefer the span.price element; fall back to text regex
            price_span = card.find("span", class_="price")
            if price_span:
                raw_price = price_span.get_text(strip=True).replace("$", "").replace(",", "")
                try:
                    data["price_usd"] = float(raw_price)
                except ValueError:
                    pass

            mileage_m = _MILEAGE_RE.search(text)
            if mileage_m:
                data["mileage_km"] = int(mileage_m.group(1).replace(",", ""))

            year_m = _YEAR_RE.search(text)
            if year_m:
                yr_str = year_m.group(1).split("/")[0]
                if yr_str.isdigit():
                    data["year"] = int(yr_str)

            engine_m = _ENGINE_RE.search(text)
            if engine_m:
                data["engine_size_cc"] = int(engine_m.group(1).replace(",", ""))

            trans_m = _TRANS_RE.search(text)
            if trans_m:
                data["transmission"] = self._normalize_transmission(trans_m.group(1))

            fuel_m = _FUEL_RE.search(text)
            if fuel_m:
                data["fuel_type"] = self._normalize_fuel(fuel_m.group(1).strip())

            color_m = _COLOR_RE.search(text)
            if color_m:
                data["color"] = color_m.group(1).strip().title()

            if not data.get("price_usd") or not data.get("make"):
                return None

            return data

        except Exception as e:
            logger.debug(f"[{self.PLATFORM_NAME}] Card parse error: {e}")
            return None

    def scrape(
        self,
        make: str = "",
        model: str = "",
        min_year: int = 2015,
        max_pages: Optional[int] = None,
    ) -> list[dict]:
        """
        Scrape BE FORWARD stocklist.
        Collects both div.stocklist-row (featured) and tr.stocklist-row (renewal section)
        cards. Pass make="" to collect all makes; make_slug filtering is done in Python
        from the href since BE FORWARD's MAKER URL filter is unreliable.
        """
        max_pages = max_pages or self.max_pages
        make_slug = make.lower().replace(" ", "-") if make else ""
        results = []
        seen_urls: set = set()

        logger.info(
            f"[{self.PLATFORM_NAME}] Scraping make={make or 'ALL'} min_year={min_year} "
            f"max_pages={max_pages}"
        )

        for page in range(1, max_pages + 1):
            url = self._build_url(min_year, page)
            logger.info(f"[{self.PLATFORM_NAME}] Page {page} → {url}")

            try:
                response = self._get(url)
                if response is None:
                    break

                soup = self._parse_html(response)
                # BE FORWARD uses div.stocklist-row for featured cards and
                # tr.stocklist-row for the larger renewal/inventory section
                cards = soup.find_all(["div", "tr"], class_="stocklist-row")

                if not cards:
                    logger.info(f"[{self.PLATFORM_NAME}] No cards on page {page}, stopping")
                    break

                page_results = []
                for card in cards:
                    parsed = self._parse_card(card, make_slug)
                    if parsed:
                        listing_url = parsed["url"]
                        if listing_url in seen_urls:
                            continue
                        seen_urls.add(listing_url)
                        if model and model.lower() not in parsed["model"].lower():
                            continue
                        page_results.append(parsed)

                logger.info(
                    f"[{self.PLATFORM_NAME}] Page {page}: {len(page_results)} listings "
                    f"(from {len(cards)} cards)"
                )
                results.extend(page_results)

                if len(cards) < 3:
                    break

            except Exception as e:
                logger.error(f"[{self.PLATFORM_NAME}] Error on page {page}: {e}")
                break

        logger.info(
            f"[{self.PLATFORM_NAME}] Done — {len(results)} total listings"
        )
        return results


if __name__ == "__main__":
    scraper = BeForwardScraper()
    data = scraper.scrape(make="", min_year=2015, max_pages=2)
    for car in data[:5]:
        print(car)
    print(f"\nTotal: {len(data)}")
