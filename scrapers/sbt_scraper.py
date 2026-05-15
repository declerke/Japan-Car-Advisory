import re
from typing import Optional
from loguru import logger
from scrapers.base_scraper import BaseScraper

# Title format: "2018 HONDA VEZEL HYBRID X" or "2020/2 HONDA N VAN"
_TITLE_RE = re.compile(r'^(\d{4})(?:/\d{1,2})?\s+(\S+)\s+(.+)$')
_MILEAGE_RE = re.compile(r'([\d,]+)\s*km', re.IGNORECASE)
_ENGINE_RE  = re.compile(r'([\d,]+)\s*cc', re.IGNORECASE)

FUEL_MAP = {
    "HYBRID(PETROL)": "Hybrid", "HYBRID(DIESEL)": "Hybrid",
    "HYBRID": "Hybrid", "PETROL": "Petrol", "GASOLINE": "Petrol",
    "DIESEL": "Diesel", "ELECTRIC": "Electric", "EV": "Electric",
    "LPG": "LPG", "CNG": "CNG", "PLUG-IN HYBRID": "Plug-in Hybrid",
}

TRANS_MAP = {
    "AT": "Automatic", "AUTO": "Automatic", "AUTOMATIC": "Automatic",
    "MT": "Manual", "MANUAL": "Manual",
    "CVT": "CVT", "AMT": "Semi-Automatic",
}

# Normalise transmission strings like "6MT" → Manual
_TRANS_RE = re.compile(r'\d*(AT|MT|CVT|AMT)', re.IGNORECASE)

MAKE_MAP = {
    "TOYOTA": "Toyota", "HONDA": "Honda", "NISSAN": "Nissan",
    "MAZDA": "Mazda", "SUBARU": "Subaru", "MITSUBISHI": "Mitsubishi",
    "SUZUKI": "Suzuki", "DAIHATSU": "Daihatsu", "ISUZU": "Isuzu",
    "LEXUS": "Lexus", "INFINITI": "Infiniti", "HINO": "Hino",
    "BMW": "BMW", "MERCEDES-BENZ": "Mercedes-Benz",
    "MERCEDES": "Mercedes-Benz", "VOLKSWAGEN": "Volkswagen",
    "LAND": "Land Rover",  # "LAND ROVER" splits as make=LAND
}


def _get_status(card, class_suffix: str) -> Optional[str]:
    """Return text of the first card-product__status element that also has class_suffix."""
    for el in card.find_all(class_="card-product__status"):
        if class_suffix in (el.get("class") or []):
            val = el.get_text(strip=True)
            return val if val and val != "-" else None
    return None


class SBTJapanScraper(BaseScraper):
    PLATFORM_NAME = "SBT Japan"
    BASE_URL = "https://www.sbtjapan.com"

    def _build_url(self, page: int) -> str:
        return f"{self.BASE_URL}/used-cars/search?steering=RHD&page={page}"

    def _parse_title(self, raw: str) -> tuple:
        """Returns (year, make, model) from titles like '2018 HONDA VEZEL HYBRID X'."""
        m = _TITLE_RE.match(raw.strip())
        if not m:
            return None, None, None
        year = int(m.group(1))
        make_raw = m.group(2).upper()
        model_raw = m.group(3).strip()

        # "LAND ROVER ..." → make=LAND splits weirdly; check if model starts with ROVER
        if make_raw == "LAND" and model_raw.upper().startswith("ROVER"):
            make = "Land Rover"
            model_raw = model_raw[5:].strip()
        else:
            make = MAKE_MAP.get(make_raw, make_raw.title())

        model = model_raw.title()
        return year, make, model

    def _parse_card(self, card) -> Optional[dict]:
        try:
            link = card.select_one(".card-product__wrap")
            if not link:
                return None
            href = link.get("href", "")
            if not href:
                return None
            url = self.BASE_URL + href
            stock_id = href.rstrip("/").split("/")[-1].upper()

            title_el = card.select_one(".card-product__product")
            if not title_el:
                return None
            year, make, model = self._parse_title(title_el.get_text(strip=True))
            if not make or not year:
                return None

            # Vehicle price (first .card-product__price = FOB price in USD)
            price_el = card.select_one(".card-product__price")
            if not price_el:
                return None
            price_usd = self._safe_float(price_el.get_text(strip=True))
            if not price_usd:
                return None

            data = {
                "source_platform": self.PLATFORM_NAME,
                "url": url,
                "external_id": stock_id,
                "make": make,
                "model": model,
                "year": year,
                "price_usd": price_usd,
            }

            # Mileage
            mileage_raw = _get_status(card, "-mileage")
            if mileage_raw:
                m2 = _MILEAGE_RE.search(mileage_raw)
                if m2:
                    data["mileage_km"] = int(m2.group(1).replace(",", ""))

            # Engine cc — take first non-dash value
            for el in card.find_all(class_="card-product__status"):
                if "-engine-capacity" not in (el.get("class") or []):
                    continue
                raw = el.get_text(strip=True)
                if raw and raw != "-":
                    m3 = _ENGINE_RE.search(raw)
                    if m3:
                        data["engine_size_cc"] = int(m3.group(1).replace(",", ""))
                        break

            # Transmission
            trans_raw = _get_status(card, "-transmission")
            if trans_raw:
                m4 = _TRANS_RE.search(trans_raw.upper())
                suffix = m4.group(1) if m4 else trans_raw.upper()
                data["transmission"] = TRANS_MAP.get(suffix, trans_raw.title())

            # Fuel type
            fuel_raw = _get_status(card, "-fuel-type")
            if fuel_raw:
                data["fuel_type"] = FUEL_MAP.get(fuel_raw.upper(), fuel_raw.title())

            # Drive type
            drive_raw = _get_status(card, "-drive-type")
            if drive_raw:
                data["drive_type"] = drive_raw

            # Color
            color_raw = _get_status(card, "-body-color")
            if color_raw:
                data["color"] = color_raw.title()

            # Doors / seats
            doors_raw = _get_status(card, "-door")
            if doors_raw and doors_raw.isdigit():
                data["doors"] = int(doors_raw)

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
        max_pages = max_pages or self.max_pages
        results = []
        seen_urls: set = set()

        logger.info(
            f"[{self.PLATFORM_NAME}] Scraping min_year={min_year} max_pages={max_pages}"
        )

        for page in range(1, max_pages + 1):
            url = self._build_url(page)
            logger.info(f"[{self.PLATFORM_NAME}] Page {page} → {url}")

            try:
                response = self._get(url)
                if response is None:
                    break

                soup = self._parse_html(response)
                cards = soup.select(".card-product")

                if not cards:
                    logger.info(f"[{self.PLATFORM_NAME}] No cards on page {page}, stopping")
                    break

                page_results = []
                for card in cards:
                    parsed = self._parse_card(card)
                    if not parsed:
                        continue
                    if parsed["url"] in seen_urls:
                        continue
                    if parsed.get("year") and parsed["year"] < min_year:
                        continue
                    if make and make.lower() not in parsed["make"].lower():
                        continue
                    if model and model.lower() not in parsed["model"].lower():
                        continue
                    seen_urls.add(parsed["url"])
                    page_results.append(parsed)

                logger.info(
                    f"[{self.PLATFORM_NAME}] Page {page}: {len(page_results)} valid "
                    f"(from {len(cards)} cards)"
                )
                results.extend(page_results)

            except Exception as e:
                logger.error(f"[{self.PLATFORM_NAME}] Error on page {page}: {e}")
                break

        logger.info(f"[{self.PLATFORM_NAME}] Done — {len(results)} total listings")
        return results


if __name__ == "__main__":
    scraper = SBTJapanScraper()
    data = scraper.scrape(min_year=2015, max_pages=1)
    for car in data[:5]:
        print(car)
    print(f"\nTotal: {len(data)}")
