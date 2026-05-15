from loguru import logger
from scrapers.beforward_scraper import BeForwardScraper
from scrapers.sbt_scraper import SBTJapanScraper
from scrapers.aaajapan_scraper import AAAJapanScraper
from scrapers.carfromjapan_scraper import CarFromJapanScraper
from scrapers.japanesecartrade_scraper import JapaneseCarTradeScraper

def main():
    enabled_scrapers = [
        BeForwardScraper(),
        SBTJapanScraper(),
        AAAJapanScraper(),
        CarFromJapanScraper(),
        JapaneseCarTradeScraper()
    ]
    
    all_data = []
    
    logger.info(f"Starting orchestration for {len(enabled_scrapers)} platforms...")
    
    for scraper in enabled_scrapers:
        try:
            data = scraper.scrape(make="Toyota", min_year=2018, max_pages=2)
            
            if data:
                all_data.extend(data)
                logger.success(f"Collected {len(data)} items from {scraper.PLATFORM_NAME}")
            else:
                logger.warning(f"No data returned from {scraper.PLATFORM_NAME}")
                
        except Exception as e:
            logger.error(f"Failed to run {scraper.PLATFORM_NAME}: {e}")

    logger.info("--- Scrape Summary ---")
    logger.info(f"Total dataset size: {len(all_data)}")
    
    if all_data:
        logger.info("Ready for ETL loading.")
    else:
        logger.error("Dataset is empty. Check connection or platform selectors.")

if __name__ == "__main__":
    main()