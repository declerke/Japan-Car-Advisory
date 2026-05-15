import sys
import os
from datetime import datetime, timedelta
from airflow.decorators import dag, task
from airflow.utils.dates import days_ago

sys.path.insert(0, os.getenv("PYTHONPATH", "/opt/airflow/project"))

DEFAULT_ARGS = {
    "owner": "japan-car-advisory",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

MIN_YEAR = 2015
BF_MAX_PAGES = 15
SBT_MAX_PAGES = 5


def _run_scraper(scraper, platform: str, min_year: int, max_pages: int) -> dict:
    """Shared scrape-clean-upsert logic for any scraper instance."""
    from etl.cleaner import clean_dataframe
    from etl.loader import upsert_japan_listings, log_scrape_run
    import pandas as pd
    import time

    start = time.time()
    raw = scraper.scrape(make="", min_year=min_year, max_pages=max_pages)
    total_fetched = len(raw)
    total_inserted = total_updated = total_errors = 0

    if raw:
        df = pd.DataFrame(raw)
        clean_df = clean_dataframe(df)
        result = upsert_japan_listings(clean_df)
        total_inserted = result["inserted"]
        total_updated = result["updated"]
        total_errors = result["errors"]

    duration = time.time() - start
    log_scrape_run(
        platform=platform,
        run_type="scheduled_daily",
        status="success",
        records_fetched=total_fetched,
        records_inserted=total_inserted,
        records_updated=total_updated,
        errors=total_errors,
        duration_seconds=duration,
    )
    summary = {
        "platform": platform,
        "fetched": total_fetched,
        "inserted": total_inserted,
        "updated": total_updated,
        "errors": total_errors,
        "duration_s": round(duration, 1),
    }
    print(f"[{platform}] Scrape complete: {summary}")
    return summary


@dag(
    dag_id="japan_cars_pipeline",
    default_args=DEFAULT_ARGS,
    description="Scrape BE FORWARD + SBT Japan → clean → load → train price model",
    schedule_interval="0 6 * * *",
    start_date=days_ago(1),
    catchup=False,
    tags=["japan-car-advisory", "scraping", "ml"],
)
def japan_cars_pipeline():

    @task(task_id="scrape_beforward")
    def scrape_beforward() -> dict:
        from scrapers.beforward_scraper import BeForwardScraper
        from etl.loader import test_connection
        if not test_connection():
            raise RuntimeError("Cannot connect to car import database")
        return _run_scraper(BeForwardScraper(), "beforward", MIN_YEAR, BF_MAX_PAGES)

    @task(task_id="scrape_sbt")
    def scrape_sbt() -> dict:
        from scrapers.sbt_scraper import SBTJapanScraper
        return _run_scraper(SBTJapanScraper(), "sbt_japan", MIN_YEAR, SBT_MAX_PAGES)

    @task(task_id="validate_data")
    def validate_data(bf_summary: dict, sbt_summary: dict) -> int:
        from etl.loader import load_japan_listings
        df = load_japan_listings(limit=100000)
        total_rows = len(df)
        print(f"Database has {total_rows} active listings")
        if total_rows == 0:
            raise ValueError("No listings in database after scrape — check scraper output")
        return total_rows

    @task(task_id="train_price_model")
    def train_price_model(total_rows: int) -> dict:
        from models.price_predictor import train_and_select_best
        from etl.loader import load_japan_listings

        if total_rows < 50:
            print(f"Only {total_rows} rows — skipping model training (need ≥ 50)")
            return {"skipped": True, "reason": f"Only {total_rows} rows"}

        df = load_japan_listings(limit=100000)
        meta = train_and_select_best(df)
        best = meta.get("best_metrics", {})
        print(f"Model trained: {meta.get('model_name')} | MAE=${best.get('MAE', 0):,.0f} | R²={best.get('R2', 0):.3f}")
        return meta

    @task(task_id="log_pipeline_summary")
    def log_pipeline_summary(bf_summary: dict, sbt_summary: dict, model_meta: dict):
        total_fetched = bf_summary.get("fetched", 0) + sbt_summary.get("fetched", 0)
        total_inserted = bf_summary.get("inserted", 0) + sbt_summary.get("inserted", 0)
        print("=" * 60)
        print("JAPAN CAR ADVISORY PIPELINE — COMPLETE")
        print(f"  BE FORWARD fetched : {bf_summary.get('fetched', 0)}")
        print(f"  SBT Japan fetched  : {sbt_summary.get('fetched', 0)}")
        print(f"  Total fetched      : {total_fetched}")
        print(f"  Total inserted     : {total_inserted}")
        if not model_meta.get("skipped"):
            best = model_meta.get("best_metrics", {})
            print(f"  Model              : {model_meta.get('model_name', 'N/A')}")
            print(f"  MAE                : ${best.get('MAE', 0):,.0f}")
            print(f"  R²                 : {best.get('R2', 0):.3f}")
        print("=" * 60)

    bf_summary = scrape_beforward()
    sbt_summary = scrape_sbt()
    row_count = validate_data(bf_summary, sbt_summary)
    model_result = train_price_model(row_count)
    log_pipeline_summary(bf_summary, sbt_summary, model_result)


dag_instance = japan_cars_pipeline()
