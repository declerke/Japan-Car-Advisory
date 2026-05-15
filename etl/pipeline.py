import time
import argparse
from typing import Optional
import pandas as pd
from loguru import logger
from scrapers import SCRAPER_REGISTRY
from etl.cleaner import clean_dataframe
from etl.loader import upsert_japan_listings, log_scrape_run, test_connection

DEFAULT_MAKES = ["Toyota", "Honda", "Nissan", "Mazda", "Subaru", "Mitsubishi", "Suzuki"]
DEFAULT_MIN_YEAR = 2018


def run_scraper(platform_key: str, make: str, model: str = "", min_year: int = DEFAULT_MIN_YEAR, max_pages: int = 5) -> list[dict]:
    scraper_cls = SCRAPER_REGISTRY.get(platform_key)
    if not scraper_cls:
        logger.error(f"Unknown platform: {platform_key}")
        return []

    scraper = scraper_cls()
    logger.info(f"Running {scraper.PLATFORM_NAME} | make={make} model={model} min_year={min_year}")
    return scraper.scrape(make=make, model=model, min_year=min_year, max_pages=max_pages)


def run_pipeline(
    platforms: Optional[list[str]] = None,
    makes: Optional[list[str]] = None,
    models: Optional[list[str]] = None,
    min_year: int = DEFAULT_MIN_YEAR,
    max_pages: int = 5,
):
    if not test_connection():
        logger.critical("Cannot connect to database. Aborting pipeline.")
        return

    platforms = platforms or list(SCRAPER_REGISTRY.keys())
    makes = makes or DEFAULT_MAKES
    models = models or [""]

    total_fetched = 0
    total_inserted = 0
    total_updated = 0
    total_errors = 0
    pipeline_start = time.time()

    for platform_key in platforms:
        for make in makes:
            for model in models:
                start = time.time()
                raw_records = []
                status = "success"

                try:
                    raw_records = run_scraper(platform_key, make, model, min_year, max_pages)
                    total_fetched += len(raw_records)

                    if raw_records:
                        df = pd.DataFrame(raw_records)
                        clean_df = clean_dataframe(df)
                        result = upsert_japan_listings(clean_df)
                        total_inserted += result["inserted"]
                        total_updated += result["updated"]
                        total_errors += result["errors"]
                    else:
                        logger.warning(f"No records from {platform_key} for {make} {model}")

                except Exception as e:
                    status = "error"
                    logger.error(f"Pipeline error [{platform_key}][{make}]: {e}")

                duration = time.time() - start
                scraper_name = SCRAPER_REGISTRY.get(platform_key, type("", (), {"PLATFORM_NAME": platform_key}))().PLATFORM_NAME if platform_key in SCRAPER_REGISTRY else platform_key
                log_scrape_run(
                    platform=platform_key,
                    run_type=f"make={make} model={model}",
                    status=status,
                    records_fetched=len(raw_records),
                    records_inserted=total_inserted,
                    records_updated=total_updated,
                    errors=total_errors,
                    duration_seconds=duration,
                )

    total_duration = time.time() - pipeline_start
    logger.info(
        f"Pipeline complete in {total_duration:.1f}s — "
        f"Fetched: {total_fetched} | Inserted: {total_inserted} | "
        f"Updated: {total_updated} | Errors: {total_errors}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Japan Car Advisory ETL Pipeline")
    parser.add_argument("--platforms", nargs="*", choices=list(SCRAPER_REGISTRY.keys()), help="Platforms to scrape")
    parser.add_argument("--makes", nargs="*", default=["Toyota"], help="Car makes to scrape")
    parser.add_argument("--models", nargs="*", default=[""], help="Car models to scrape")
    parser.add_argument("--min-year", type=int, default=DEFAULT_MIN_YEAR)
    parser.add_argument("--max-pages", type=int, default=5)
    args = parser.parse_args()

    run_pipeline(
        platforms=args.platforms,
        makes=args.makes,
        models=args.models,
        min_year=args.min_year,
        max_pages=args.max_pages,
    )