import time
import random
import os
from abc import ABC, abstractmethod
from typing import Optional
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from dotenv import load_dotenv

load_dotenv()

class BaseScraper(ABC):
    PLATFORM_NAME: str = "base"

    def __init__(self):
        self.session = requests.Session()
        self.ua = UserAgent()
        # Environment variables with fallback defaults
        self.delay_min = float(os.getenv("SCRAPE_DELAY_MIN", 3))
        self.delay_max = float(os.getenv("SCRAPE_DELAY_MAX", 8))
        self.timeout = int(os.getenv("SCRAPE_TIMEOUT", 30))
        self.max_pages = int(os.getenv("SCRAPE_MAX_PAGES", 5))
        self._configure_session()

    def _configure_session(self):
        """Initializes the session with high-reputation browser headers."""
        self.session.headers.update({
            "User-Agent": os.getenv("USER_AGENT", self.ua.random),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })
        self.session.max_redirects = 5

    def _random_delay(self):
        """Implements a variable sleep to mimic human browsing behavior."""
        delay = random.uniform(self.delay_min, self.delay_max)
        logger.debug(f"[{self.PLATFORM_NAME}] Sleeping {delay:.1f}s")
        time.sleep(delay)

    def _rotate_user_agent(self):
        """Updates the session with a new identity when detection is suspected."""
        new_ua = self.ua.random
        self.session.headers["User-Agent"] = new_ua
        logger.debug(f"[{self.PLATFORM_NAME}] Identity rotated: {new_ua[:50]}...")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=20),
        retry=retry_if_exception_type((requests.RequestException, ConnectionError)),
        reraise=True,
    )
    def _get(self, url: str, params: Optional[dict] = None) -> Optional[requests.Response]:
        """Performs a GET request with automatic retry logic and bot detection handling."""
        self._random_delay()
        
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            
            # Catch hard blocks — 403 or a true challenge page (short body with no real content)
            is_blocked = (
                response.status_code == 403
                or (response.status_code == 200 and len(response.text) < 5000
                    and "captcha" in response.text.lower())
            )
            if is_blocked:
                logger.error(f"[{self.PLATFORM_NAME}] Bot detection triggered. Rotating identity...")
                self._rotate_user_agent()
                response.raise_for_status()
                
            response.raise_for_status()
            return response

        except requests.HTTPError as e:
            logger.warning(f"[{self.PLATFORM_NAME}] HTTP {e.response.status_code} for {url}")
            # If we hit a 404, we don't want to retry usually, but we raise it for the scraper to handle
            raise
        except requests.RequestException as e:
            logger.error(f"[{self.PLATFORM_NAME}] Request failed: {e}")
            raise

    def _parse_html(self, response: requests.Response) -> BeautifulSoup:
        """Parses HTML using the native parser to handle malformed markup without warnings."""
        return BeautifulSoup(response.text, "html.parser")

    def _safe_int(self, value: Optional[str]) -> Optional[int]:
        """Extracts integers from strings, handling commas and units."""
        if value is None:
            return None
        cleaned = "".join(filter(str.isdigit, str(value)))
        return int(cleaned) if cleaned else None

    def _safe_float(self, value: Optional[str]) -> Optional[float]:
        """Extracts floats from currency and formatted strings."""
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
        """Maps varying manufacturer names to a standard format."""
        if not make:
            return None
        make_map = {
            "TOYOTA": "Toyota", "HONDA": "Honda", "NISSAN": "Nissan",
            "MAZDA": "Mazda", "SUBARU": "Subaru", "MITSUBISHI": "Mitsubishi",
            "SUZUKI": "Suzuki", "DAIHATSU": "Daihatsu", "ISUZU": "Isuzu",
            "LEXUS": "Lexus", "INFINITI": "Infiniti", "ACURA": "Acura",
        }
        upper = make.upper().strip()
        return make_map.get(upper, make.strip().title())

    def _normalize_fuel(self, fuel: Optional[str]) -> Optional[str]:
        """Standardizes fuel type terminology."""
        if not fuel:
            return None
        fuel_map = {
            "PETROL": "Petrol", "GASOLINE": "Petrol", "GAS": "Petrol",
            "DIESEL": "Diesel", "HYBRID": "Hybrid", "ELECTRIC": "Electric",
            "LPG": "LPG", "CNG": "CNG", "PLUG-IN HYBRID": "Plug-in Hybrid",
        }
        return fuel_map.get(fuel.upper().strip(), fuel.strip().title())

    def _normalize_transmission(self, trans: Optional[str]) -> Optional[str]:
        """Standardizes transmission type terminology."""
        if not trans:
            return None
        trans_map = {
            "AUTOMATIC": "Automatic", "AUTO": "Automatic", "AT": "Automatic",
            "MANUAL": "Manual", "MT": "Manual", "CVT": "CVT",
            "SEMI-AUTOMATIC": "Semi-Automatic",
        }
        return trans_map.get(trans.upper().strip(), trans.strip().title())

    @abstractmethod
    def scrape(self, make: str = "Toyota", model: str = "", min_year: int = 2018, max_pages: Optional[int] = None) -> list[dict]:
        """Abstract method for individual platform implementation."""
        raise NotImplementedError