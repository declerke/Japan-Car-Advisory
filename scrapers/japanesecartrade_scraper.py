from typing import Optional
from loguru import logger
from scrapers.base_scraper import BaseScraper


class JapaneseCarTradeScraper(BaseScraper):
    PLATFORM_NAME = "JapaneseCarTrade"
    BASE_URL = "https://www.japanesecartrade.com"
    SEARCH_URL = "https://www.japanesecartrade.com/cars"

    DISCLAIMER = (
        "Data scraped from JapaneseCarTrade for educational/portfolio purposes only. "
        "Not for commercial use. Respect japanesecartrade.com ToS."
    )

    def _build_search_params(self, make: str, model: str, min_year: int, page: int) -> dict:
        return {
            "make": make,
            "model": model,
            "year_min": min_year,
            "steering": "RHD",
            "p": page,
        }

    def _parse_listing_card(self, card) -> Optional[dict]:
        try:
            data = {"source_platform": self.PLATFORM_NAME}

            anchor = card.select_one("a")
            if anchor:
                href = anchor.get("href", "")
                data["url"] = href if href.startswith("http") else self.BASE_URL + href

            # Updated title selector for current site structure
            title = card.select_one(".title, h2, h3, .car-title, .listing-title")
            if title:
                title_text = title.get_text(strip=True)
                tokens = title_text.split()
                if tokens:
                    data["make"] = self._normalize_make(tokens[0])
                if len(tokens) > 1:
                    data["model"] = tokens[1]
                
                # Extract year from title if not found in specific element
                for token in tokens:
                    year_candidate = self._safe_int(token)
                    if year_candidate and 2000 < year_candidate < 2030:
                        data["year"] = year_candidate
                        break

            # Handle price extraction for multiple currencies often found on JCT
            price_el = card.select_one(".price, .cost, [class*='price'], .fob-price")
            if price_el:
                data["price_usd"] = self._safe_float(price_el.get_text(strip=True))

            # Parse specifications list
            for li in card.select("li, .detail, .car-info li"):
                text = li.get_text(" ", strip=True).lower()
                if "km" in text and "mileage_km" not in data:
                    data["mileage_km"] = self._safe_int(text)
                elif "cc" in text:
                    data["engine_size_cc"] = self._safe_int(text)
                elif any(f in text for f in ["petrol", "diesel", "hybrid", "gasoline"]):
                    data["fuel_type"] = self._normalize_fuel(text)
                elif any(t in text for t in ["automatic", "manual", "cvt", " at", " mt"]):
                    data["transmission"] = self._normalize_transmission(text)
                elif any(b in text for b in ["sedan", "suv", "hatchback", "wagon", "van", "pickup", "coupe"]):
                    data["body_type"] = text.strip().title()

            img = card.select_one("img")
            if img:
                # Use data-src for lazy-loading support
                src = img.get("data-src") or img.get("src", "")
                data["images"] = [src] if src else []

            return data if data.get("make") else None

        except Exception as e:
            logger.debug(f"[{self.PLATFORM_NAME}] Parse error: {e}")
            return None

    def scrape(self, make: str = "Toyota", model: str = "", min_year: int = 2018, max_pages: Optional[int] = None) -> list[dict]:
        max_pages = max_pages or self.max_pages
        results = []
        logger.info(f"[{self.PLATFORM_NAME}] Starting scrape | make={make} min_year={min_year}")

        for page in range(1, max_pages + 1):
            params = self._build_search_params(make, model, min_year, page)
            try:
                response = self._get(self.SEARCH_URL, params=params)
                if not response:
                    break
                
                soup = self._parse_html(response)
                # Broader card selection for aggregator layouts
                cards = soup.select(".car-listing, .car-item, [class*='vehicle'], .stock-listing-box")
                
                if not cards:
                    logger.warning(f"[{self.PLATFORM_NAME}] No listings found on page {page}")
                    break
                    
                page_results = [r for r in (self._parse_listing_card(c) for c in cards) if r]
                logger.info(f"[{self.PLATFORM_NAME}] Page {page}: {len(page_results)} items")
                results.extend(page_results)
                
                if not soup.select_one("a.next, a[rel='next'], .pagination .next"):
                    break
            except Exception as e:
                logger.error(f"[{self.PLATFORM_NAME}] Page {page} error: {e}")
                break
                
        logger.info(f"[{self.PLATFORM_NAME}] Complete — {len(results)} listings")
        return results

if __name__ == "__main__":
    scraper = JapaneseCarTradeScraper()
    # Test for 2018+ Toyota listings
    results = scraper.scrape(make="Toyota", min_year=2018, max_pages=1)
    for res in results[:2]:
        print(res)