import time
import random
import os
from abc import ABC, abstractmethod
from typing import Optional
from loguru import logger
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

try:
    import playwright_stealth as _stealth_mod
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False


class PlaywrightBaseScraper(ABC):
    """Base scraper for JavaScript-heavy sites that require a real browser."""
    PLATFORM_NAME: str = "base"

    def __init__(self):
        self.delay_min = float(os.getenv("SCRAPE_DELAY_MIN", 3))
        self.delay_max = float(os.getenv("SCRAPE_DELAY_MAX", 8))
        self.max_pages = int(os.getenv("SCRAPE_MAX_PAGES", 5))
        self.timeout = int(os.getenv("SCRAPE_TIMEOUT", 30)) * 1000  # ms

    def _random_delay(self):
        time.sleep(random.uniform(self.delay_min, self.delay_max))

    def _get_page_content(self, url: str, wait_selector: str = "body") -> Optional[str]:
        if not _PLAYWRIGHT_AVAILABLE:
            logger.error(f"[{self.PLATFORM_NAME}] Playwright not installed. Run: playwright install chromium")
            return None

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            if _STEALTH_AVAILABLE:
                try:
                    _stealth_mod.stealth_sync(page)
                except AttributeError:
                    try:
                        _stealth_mod.stealth(page)
                    except Exception:
                        pass

            try:
                self._random_delay()
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                try:
                    page.wait_for_selector(wait_selector, timeout=15000)
                except Exception:
                    pass
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)
                return page.content()
            except Exception as e:
                logger.error(f"[{self.PLATFORM_NAME}] Playwright error: {e}")
                try:
                    page.screenshot(path=f"error_{self.PLATFORM_NAME}.png", full_page=True)
                except Exception:
                    pass
                return None
            finally:
                browser.close()

    def _parse_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    def _safe_int(self, value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        cleaned = "".join(filter(str.isdigit, str(value)))
        return int(cleaned) if cleaned else None

    def _safe_float(self, value: Optional[str]) -> Optional[float]:
        if value is None:
            return None
        cleaned = str(value).replace(",", "").replace("$", "").replace("¥", "").strip()
        try:
            if " " in cleaned:
                cleaned = cleaned.split()[0]
            return float(cleaned)
        except ValueError:
            return None

    def _normalize_make(self, make: Optional[str]) -> Optional[str]:
        if not make:
            return None
        make_map = {
            "TOYOTA": "Toyota", "HONDA": "Honda", "NISSAN": "Nissan",
            "MAZDA": "Mazda", "SUBARU": "Subaru", "MITSUBISHI": "Mitsubishi",
            "SUZUKI": "Suzuki", "DAIHATSU": "Daihatsu", "ISUZU": "Isuzu",
            "LEXUS": "Lexus", "INFINITI": "Infiniti",
        }
        return make_map.get(make.upper().strip(), make.strip().title())

    def _normalize_fuel(self, fuel: Optional[str]) -> Optional[str]:
        if not fuel:
            return None
        fuel_map = {
            "PETROL": "Petrol", "GASOLINE": "Petrol", "GAS": "Petrol",
            "DIESEL": "Diesel", "HYBRID": "Hybrid", "ELECTRIC": "Electric",
            "LPG": "LPG", "PLUG-IN HYBRID": "Plug-in Hybrid",
        }
        return fuel_map.get(fuel.upper().strip(), fuel.strip().title())

    def _normalize_transmission(self, trans: Optional[str]) -> Optional[str]:
        if not trans:
            return None
        trans_map = {
            "AUTOMATIC": "Automatic", "AUTO": "Automatic", "AT": "Automatic",
            "MANUAL": "Manual", "MT": "Manual", "CVT": "CVT",
            "SEMI-AUTOMATIC": "Semi-Automatic",
        }
        return trans_map.get(trans.upper().strip(), trans.strip().title())

    @abstractmethod
    def scrape(
        self,
        make: str = "Toyota",
        model: str = "",
        min_year: int = 2018,
        max_pages: Optional[int] = None,
    ) -> list[dict]:
        raise NotImplementedError
