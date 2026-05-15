from typing import Optional
from loguru import logger
from scrapers.base_scraper import BaseScraper


class CarFromJapanScraper(BaseScraper):
    PLATFORM_NAME = "Car From Japan"
    BASE_URL = "https://carfromjapan.com"
    SEARCH_URL = "https://carfromjapan.com/cheap-used-cars"

    DISCLAIMER = (
        "Data scraped from Car From Japan for educational/portfolio purposes only. "
        "Not for commercial use. Respect carfromjapan.com ToS."
    )

    def _build_search_url(self, make: str, model: str, min_year: int, page: int) -> str:
        params = f"?maker={make.lower()}&model={model.lower()}&year_from={min_year}&steering_type=right&page={page}"
        return self.SEARCH_URL + params

    def _parse_listing_card(self, card) -> Optional[dict]:
        try:
            data = {"source_platform": self.PLATFORM_NAME}

            link = card.select_one("a[href*='/cheap-used-'], a[class*='car-link']")
            if link:
                href = link.get("href", "")
                data["url"] = href if href.startswith("http") else self.BASE_URL + href

            # Updated title and model extraction
            name_el = card.select_one(".car-name, .vehicle-name, h2, h3, [class*='title']")
            if name_el:
                text = name_el.get_text(strip=True)
                tokens = text.split()
                if tokens:
                    data["make"] = self._normalize_make(tokens[0])
                if len(tokens) > 1:
                    data["model"] = " ".join(tokens[1:3])

            year_el = card.select_one("[class*='year'], .manufacture-year")
            if year_el:
                data["year"] = self._safe_int(year_el.get_text(strip=True))

            # Selector for amount specifically to bypass currency symbols
            price_el = card.select_one("[class*='price'] .amount, .car-price strong, [class*='fob-price']")
            if price_el:
                data["price_usd"] = self._safe_float(price_el.get_text(strip=True))

            # Iterate through spec labels
            for detail in card.select(".detail-item, .spec-item, li.item, .car-info-item"):
                text = detail.get_text(" ", strip=True).lower()
                if "km" in text:
                    data["mileage_km"] = self._safe_int(text)
                elif "cc" in text:
                    data["engine_size_cc"] = self._safe_int(text)
                elif any(f in text for f in ["petrol", "diesel", "hybrid", "gasoline"]):
                    data["fuel_type"] = self._normalize_fuel(text)
                elif any(t in text for t in ["automatic", "manual", "cvt"]):
                    data["transmission"] = self._normalize_transmission(text)

            img = card.select_one("img")
            if img:
                # Modern sites in 2026 almost always use data-src or srcset for lazy loading
                src = img.get("data-src") or img.get("src", "")
                data["images"] = [src] if src else []

            return data if data.get("make") else None

        except Exception as e:
            logger.debug(f"[{self.PLATFORM_NAME}] Card parse error: {e}")
            return None

    def scrape(self, make: str = "Toyota", model: str = "", min_year: int = 2018, max_pages: Optional[int] = None) -> list[dict]:
        max_pages = max_pages or self.max_pages
        results = []
        logger.info(f"[{self.PLATFORM_NAME}] Starting | make={make} min_year={min_year}")

        for page in range(1, max_pages + 1):
            url = self._build_search_url(make, model, min_year, page)
            try:
                response = self._get(url)
                if not response:
                    break
                soup = self._parse_html(response)
                
                # Updated container selection for current site structure
                cards = soup.select(".car-item, .vehicle-card, .listing-card, [class*='car-list'] li, .stock-item")
                
                if not cards:
                    logger.warning(f"[{self.PLATFORM_NAME}] No listings found on page {page}")
                    break
                    
                page_results = [r for r in (self._parse_listing_card(c) for c in cards) if r]
                logger.info(f"[{self.PLATFORM_NAME}] Page {page}: {len(page_results)} listings found")
                results.extend(page_results)
                
                # Pagination check
                if not soup.select_one("a[rel='next'], .next-page:not(.disabled), [class*='pagination-next']"):
                    break
            except Exception as e:
                logger.error(f"[{self.PLATFORM_NAME}] Page {page} error: {e}")
                break

        logger.info(f"[{self.PLATFORM_NAME}] Complete — {len(results)} listings")
        return results

if __name__ == "__main__":
    scraper = CarFromJapanScraper()
    # Test for 2018+ Toyota listings
    results = scraper.scrape(make="Toyota", min_year=2018, max_pages=1)
    for res in results[:2]:
        print(res)