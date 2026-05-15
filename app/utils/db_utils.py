import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


def _get_conn_str() -> str:
    return (
        f"postgresql+psycopg2://{os.getenv('DB_USER','caruser')}:"
        f"{os.getenv('DB_PASSWORD','carpassword')}@"
        f"{os.getenv('DB_HOST','localhost')}:"
        f"{os.getenv('DB_PORT','5432')}/"
        f"{os.getenv('DB_NAME','car_import_db')}"
    )


@st.cache_resource
def get_engine():
    return create_engine(_get_conn_str(), pool_pre_ping=True, pool_recycle=1800)


def db_available() -> bool:
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@st.cache_data(ttl=300)
def fetch_listings(
    make=None, model=None, min_year=None, max_year=None,
    min_price=None, max_price=None, fuel_type=None,
    transmission=None, platform=None, limit=500
) -> pd.DataFrame:
    filters = ["is_active = TRUE"]
    params = {"limit": limit}

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
    if min_price:
        filters.append("price_usd >= :min_price")
        params["min_price"] = min_price
    if max_price:
        filters.append("price_usd <= :max_price")
        params["max_price"] = max_price
    if fuel_type:
        filters.append("LOWER(fuel_type) = LOWER(:fuel)")
        params["fuel"] = fuel_type
    if transmission:
        filters.append("LOWER(transmission) = LOWER(:trans)")
        params["trans"] = transmission
    if platform:
        filters.append("LOWER(source_platform) = LOWER(:platform)")
        params["platform"] = platform

    sql = text(f"SELECT * FROM japan_listings WHERE {' AND '.join(filters)} ORDER BY scraped_at DESC LIMIT :limit")
    with get_engine().connect() as conn:
        return pd.read_sql(sql, conn, params=params)


@st.cache_data(ttl=600)
def get_distinct_values(column: str, table: str = "japan_listings") -> list:
    sql = text(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL ORDER BY {column}")
    with get_engine().connect() as conn:
        result = conn.execute(sql)
        return [r[0] for r in result]


@st.cache_data(ttl=600)
def get_models_for_make(make: str, table: str = "japan_listings") -> list:
    sql = text(f"SELECT DISTINCT model FROM {table} WHERE LOWER(make) = LOWER(:make) AND model IS NOT NULL ORDER BY model")
    with get_engine().connect() as conn:
        result = conn.execute(sql, {"make": make})
        return [r[0] for r in result]


@st.cache_data(ttl=600)
def get_years_for_make_model(make: str, model: str, table: str = "japan_listings") -> list:
    sql = text(f"SELECT DISTINCT year FROM {table} WHERE LOWER(make) = LOWER(:make) AND LOWER(model) LIKE LOWER(:model) AND year IS NOT NULL ORDER BY year DESC")
    with get_engine().connect() as conn:
        result = conn.execute(sql, {"make": make, "model": f"%{model}%"})
        return [r[0] for r in result]


@st.cache_data(ttl=600)
def get_summary_stats() -> dict:
    sql = text("""
        SELECT
            COUNT(*) as total_listings,
            COUNT(DISTINCT make) as distinct_makes,
            COUNT(DISTINCT model) as distinct_models,
            COUNT(DISTINCT source_platform) as platforms,
            MIN(price_usd) as min_price,
            MAX(price_usd) as max_price,
            AVG(price_usd) as avg_price,
            MIN(year) as min_year,
            MAX(year) as max_year,
            MAX(scraped_at) as last_updated
        FROM japan_listings
        WHERE is_active = TRUE AND price_usd IS NOT NULL
    """)
    with get_engine().connect() as conn:
        result = conn.execute(sql).fetchone()
        if result:
            return dict(result._mapping)
    return {}


@st.cache_data(ttl=600)
def get_price_distribution(make: str = None) -> pd.DataFrame:
    filters = "is_active = TRUE AND price_usd IS NOT NULL"
    params = {}
    if make:
        filters += " AND LOWER(make) = LOWER(:make)"
        params["make"] = make
    sql = text(f"SELECT make, model, year, price_usd, mileage_km, fuel_type, transmission, body_type, source_platform FROM japan_listings WHERE {filters} LIMIT 5000")
    with get_engine().connect() as conn:
        return pd.read_sql(sql, conn, params=params)