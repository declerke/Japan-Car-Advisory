from scrapers.beforward_scraper import BeForwardScraper
from scrapers.sbt_scraper import SBTJapanScraper
from scrapers.carfromjapan_scraper import CarFromJapanScraper
from scrapers.aaajapan_scraper import AAAJapanScraper
from scrapers.japanesecartrade_scraper import JapaneseCarTradeScraper

SCRAPER_REGISTRY = {
    "beforward": BeForwardScraper,
    "sbt": SBTJapanScraper,
    "carfromjapan": CarFromJapanScraper,
    "aaajapan": AAAJapanScraper,
    "japanesecartrade": JapaneseCarTradeScraper,
}

__all__ = [
    "BeForwardScraper",
    "SBTJapanScraper",
    "CarFromJapanScraper",
    "AAAJapanScraper",
    "JapaneseCarTradeScraper",
    "SCRAPER_REGISTRY",
]