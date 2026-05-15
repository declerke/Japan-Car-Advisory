import os
import json
import decimal
from typing import Optional
from contextlib import contextmanager
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


def get_connection_string() -> str:
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "car_import_db")
    user = os.getenv("DB_USER", "caruser")
    password = os.getenv("DB_PASSWORD", "carpassword")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        conn_str = get_connection_string()
        _engine = create_engine(
            conn_str,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        logger.info("Database engine created")
    return _engine


@contextmanager
def get_connection():
    engine = get_engine()
    with engine.connect() as conn:
        yield conn


def test_connection() -> bool:
    try:
        with get_connection() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


def upsert_japan_listings(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"inserted": 0, "updated": 0, "errors": 0}

    engine = get_engine()
    inserted = 0
    updated = 0
    errors = 0

    columns = [
        "source_platform", "url", "make", "model", "grade", "year",
        "mileage_km", "engine_size_cc", "fuel_type", "transmission",
        "body_type", "drive_type", "color", "doors", "seats",
        "price_usd", "price_kes", "fob_port", "specs", "images",
    ]
    available_cols = [c for c in columns if c in df.columns]

    upsert_sql = text(f"""
        INSERT INTO japan_listings ({', '.join(available_cols)})
        VALUES ({', '.join([':' + c for c in available_cols])})
        ON CONFLICT (source_platform, url)
        DO UPDATE SET
            {', '.join([f"{c} = EXCLUDED.{c}" for c in available_cols if c not in ('source_platform', 'url')])},
            updated_at = NOW()
        RETURNING (xmax = 0) AS is_insert
    """)

    with engine.begin() as conn:
        for _, row in df.iterrows():
            try:
                row_dict = row[available_cols].to_dict()
                for k, v in row_dict.items():
                    if isinstance(v, list):
                        row_dict[k] = json.dumps(v)
                    elif isinstance(v, dict):
                        row_dict[k] = json.dumps(v)
                    elif pd.isna(v):
                        row_dict[k] = None

                result = conn.execute(upsert_sql, row_dict)
                row_result = result.fetchone()
                if row_result and row_result[0]:
                    inserted += 1
                else:
                    updated += 1
            except Exception as e:
                errors += 1
                logger.debug(f"Row upsert error: {e}")

    logger.info(f"Upsert complete: {inserted} inserted, {updated} updated, {errors} errors")
    return {"inserted": inserted, "updated": updated, "errors": errors}


def load_japan_listings(
    make: Optional[str] = None,
    model: Optional[str] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
    min_price_usd: Optional[float] = None,
    max_price_usd: Optional[float] = None,
    fuel_type: Optional[str] = None,
    transmission: Optional[str] = None,
    source_platform: Optional[str] = None,
    limit: int = 500,
) -> pd.DataFrame:
    filters = ["is_active = TRUE"]
    params = {}

    if make:
        filters.append("LOWER(make) = LOWER(:make)")
        params["make"] = make
    if model:
        filters.append("LOWER(model) LIKE LOWER(:model)")
        params["model"] = f"%{model}%"
    if min_year:
        filters.append("year >= :min_year")
        params["min_year"] = min_year
    if max_year:
        filters.append("year <= :max_year")
        params["max_year"] = max_year
    if min_price_usd:
        filters.append("price_usd >= :min_price")
        params["min_price"] = min_price_usd
    if max_price_usd:
        filters.append("price_usd <= :max_price")
        params["max_price"] = max_price_usd
    if fuel_type:
        filters.append("LOWER(fuel_type) = LOWER(:fuel_type)")
        params["fuel_type"] = fuel_type
    if transmission:
        filters.append("LOWER(transmission) = LOWER(:transmission)")
        params["transmission"] = transmission
    if source_platform:
        filters.append("LOWER(source_platform) = LOWER(:platform)")
        params["platform"] = source_platform

    where_clause = " AND ".join(filters)
    sql = text(f"""
        SELECT * FROM japan_listings
        WHERE {where_clause}
        ORDER BY scraped_at DESC
        LIMIT :limit
    """)
    params["limit"] = limit

    # Use manual execute+DataFrame to be compatible with both SQLAlchemy 1.4 and 2.0
    with get_engine().connect() as conn:
        result = conn.execute(sql, params)
        rows = result.fetchall()
        df = pd.DataFrame(rows, columns=result.keys())
    # SQLAlchemy 1.4 + psycopg2 returns NUMERIC columns as decimal.Decimal; coerce to float
    for col in df.columns:
        if not df[col].empty and df[col].dropna().apply(lambda x: isinstance(x, decimal.Decimal)).any():
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_import_cost_params() -> dict:
    query = text("SELECT param_key, param_value FROM import_cost_params")
    with get_connection() as conn:
        result = conn.execute(query)
        return {row[0]: float(row[1]) for row in result if row[1] is not None}


def save_import_estimate(estimate: dict) -> bool:
    cols = list(estimate.keys())
    sql = text(f"""
        INSERT INTO import_cost_estimates ({', '.join(cols)})
        VALUES ({', '.join([':' + c for c in cols])})
    """)
    try:
        with get_engine().begin() as conn:
            conn.execute(sql, estimate)
        return True
    except Exception as e:
        logger.error(f"Failed to save estimate: {e}")
        return False


def log_scrape_run(platform: str, run_type: str, status: str,
                   records_fetched: int = 0, records_inserted: int = 0,
                   records_updated: int = 0, errors: int = 0,
                   duration_seconds: float = 0.0):
    sql = text("""
        INSERT INTO scrape_logs
        (platform, run_type, status, records_fetched, records_inserted,
         records_updated, errors, duration_seconds, finished_at)
        VALUES (:platform, :run_type, :status, :records_fetched, :records_inserted,
                :records_updated, :errors, :duration_seconds, NOW())
    """)
    try:
        with get_engine().begin() as conn:
            conn.execute(sql, {
                "platform": platform, "run_type": run_type, "status": status,
                "records_fetched": records_fetched, "records_inserted": records_inserted,
                "records_updated": records_updated, "errors": errors,
                "duration_seconds": duration_seconds,
            })
    except Exception as e:
        logger.warning(f"Failed to log scrape run: {e}")