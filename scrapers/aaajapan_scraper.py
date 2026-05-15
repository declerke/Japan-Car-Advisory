from typing import Optional
from loguru import logger
from scrapers.base_scraper import BaseScraper


class AAAJapanScraper(BaseScraper):
    PLATFORM_NAME = "AAA Japan"
    BASE_URL = "https://www.aaajapan.com"
    SEARCH_URL = "https://www.aaajapan.com/en/used-cars"

    DISCLAIMER = (
        "Data scraped from AAA Japan for educational/portfolio purposes only. "
        "Not for commercial use. Respect aaajapan.com ToS."
    )

    def _build_search_params(self, make: str, model: str, min_year: int, page: int) -> dict:
        return {
            "maker": make,
            "model": model,
            "year_from": min_year,
            "steering": "right",
            "page": page,
        }

    def _parse_listing_card(self, card) -> Optional[dict]:
        try:
            data = {"source_platform": self.PLATFORM_NAME}

            anchor = card.select_one("a[href*='/en/used-cars/']")
            if anchor:
                href = anchor.get("href", "")
                data["url"] = href if href.startswith("http") else self.BASE_URL + href

            # Refined selectors for 2026 AAA Japan layout
            make_el = card.select_one("[class*='maker'], [class*='brand'], .car-maker, .v-brand")
            if make_el:
                data["make"] = self._normalize_make(make_el.get_text(strip=True))

            model_el = card.select_one("[class*='model'], .car-model, .v-name")
            if model_el:
                data["model"] = model_el.get_text(strip=True).title()

            year_el = card.select_one("[class*='year'], .manufacture-year, .v-year")
            if year_el:
                data["year"] = self._safe_int(year_el.get_text(strip=True))

            price_el = card.select_one("[class*='price'], .v-price, .total-price")
            if price_el:
                data["price_usd"] = self._safe_float(price_el.get_text(strip=True))

            mileage_el = card.select_one("[class*='mileage'], [class*='odometer'], .v-mileage")
            if mileage_el:
                data["mileage_km"] = self._safe_int(mileage_el.get_text(strip=True))

            engine_el = card.select_one("[class*='engine'], .v-engine")
            if engine_el:
                data["engine_size_cc"] = self._safe_int(engine_el.get_text(strip=True))

            fuel_el = card.select_one("[class*='fuel'], .v-fuel")
            if fuel_el:
                data["fuel_type"] = self._normalize_fuel(fuel_el.get_text(strip=True))

            trans_el = card.select_one("[class*='trans'], [class*='gearbox'], .v-transmission")
            if trans_el:
                data["transmission"] = self._normalize_transmission(trans_el.get_text(strip=True))

            img = card.select_one("img")
            if img:
                # Prioritizing data-src for lazy-loaded images common in 2026
                src = img.get("data-src") or img.get("src", "")
                data["images"] = [src] if src else []

            return data if data.get("make") else None

        except Exception as e:
            logger.debug(f"[{self.PLATFORM_NAME}] Parse error: {e}")
            return None

    def scrape(self, make: str = "Toyota", model: str = "", min_year: int = 2018, max_pages: Optional[int] = None) -> list[dict]:
        max_pages = max_pages or self.max_pages
        results = []
        logger.info(f"[{self.PLATFORM_NAME}] Starting scrape | make={make} model={model} min_year={min_year}")
        
        for page in range(1, max_pages + 1):
            params = self._build_search_params(make, model, min_year, page)
            try:
                response = self._get(self.SEARCH_URL, params=params)
                if not response:
                    break
                
                soup = self._parse_html(response)
                # Updated container selection for AAA Japan's modern layout
                cards = soup.select(".car-card, .vehicle-item, [class*='listing'], .car-item-box")
                
                if not cards:
                    logger.info(f"[{self.PLATFORM_NAME}] No listings found on page {page}")
                    break
                
                page_results = [r for r in (self._parse_listing_card(c) for c in cards) if r]
                results.extend(page_results)
                
                logger.info(f"[{self.PLATFORM_NAME}] Page {page}: {len(page_results)} items")
                
                # Check for pagination
                if not soup.select_one("a[rel='next'], .next, .pagination-next"):
                    break
            except Exception as e:
                logger.error(f"[{self.PLATFORM_NAME}] Page {page} error: {e}")
                break
                
        logger.info(f"[{self.PLATFORM_NAME}] Complete — {len(results)} listings total")
        return results

if __name__ == "__main__":
    scraper = AAAJapanScraper()
    # Test for 2018+ Toyota listings
    results = scraper.scrape(make="Toyota", min_year=2018, max_pages=1)
    for res in results[:2]:
        print(res)