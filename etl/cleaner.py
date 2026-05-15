import re
from datetime import datetime
from typing import Optional
import pandas as pd
from loguru import logger
from dotenv import load_dotenv
import os

load_dotenv()

CURRENT_YEAR = datetime.now().year
MIN_YEAR = 2015
MAX_YEAR = CURRENT_YEAR
MAX_MILEAGE = 500_000
MIN_PRICE_USD = 500
MAX_PRICE_USD = 200_000
MIN_ENGINE_CC = 600
MAX_ENGINE_CC = 8000
USD_TO_KES = float(os.getenv("USD_TO_KES", 130.0))


MAKE_ALIASES = {
    "TOYOT": "Toyota", "TOY": "Toyota",
    "NISSN": "Nissan", "DATSUN": "Nissan",
    "MITSUB": "Mitsubishi", "MITSU": "Mitsubishi",
    "VOLKSW": "Volkswagen", "VW": "Volkswagen",
    "MERCED": "Mercedes-Benz", "BENZ": "Mercedes-Benz", "MB": "Mercedes-Benz",
    "BMW": "BMW", "BEEMER": "BMW",
    "LAND ROVER": "Land Rover", "LANDROVER": "Land Rover",
    "ALFA ROMEO": "Alfa Romeo",
    "ASTON MARTIN": "Aston Martin",
}

BODY_TYPE_MAP = {
    "sedan": "Sedan", "saloon": "Sedan",
    "suv": "SUV", "4x4": "SUV", "crossover": "SUV",
    "hatchback": "Hatchback", "hatch": "Hatchback",
    "wagon": "Wagon", "estate": "Wagon",
    "van": "Van", "minivan": "Van", "minibus": "Van",
    "pickup": "Pickup", "truck": "Pickup",
    "coupe": "Coupe",
    "convertible": "Convertible", "cabriolet": "Convertible",
    "bus": "Bus",
}


def normalize_make(make: Optional[str]) -> Optional[str]:
    if not make:
        return None
    cleaned = str(make).strip().upper()
    for alias, canonical in MAKE_ALIASES.items():
        if cleaned.startswith(alias):
            return canonical
    return str(make).strip().title()


def normalize_model(model: Optional[str], make: Optional[str] = None) -> Optional[str]:
    if not model:
        return None
    cleaned = str(model).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.title()


def normalize_body_type(body: Optional[str]) -> Optional[str]:
    if not body:
        return None
    lower = str(body).lower().strip()
    for key, val in BODY_TYPE_MAP.items():
        if key in lower:
            return val
    return str(body).strip().title()


def clean_mileage(value) -> Optional[int]:
    if pd.isna(value) or value is None:
        return None
    raw = str(value).replace(",", "").replace("km", "").replace("KM", "").strip()
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    km = int(digits)
    if km < 0 or km > MAX_MILEAGE:
        return None
    return km


def clean_engine_size(value) -> Optional[int]:
    if pd.isna(value) or value is None:
        return None
    raw = str(value).replace("cc", "").replace("CC", "").replace(",", "").strip()
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    cc = int(digits)
    if cc < MIN_ENGINE_CC or cc > MAX_ENGINE_CC:
        return None
    return cc


def clean_price_usd(value) -> Optional[float]:
    if pd.isna(value) or value is None:
        return None
    raw = str(value).replace(",", "").replace("$", "").replace("USD", "").strip()
    try:
        price = float(raw)
    except ValueError:
        return None
    if price < MIN_PRICE_USD or price > MAX_PRICE_USD:
        return None
    return price


def clean_year(value) -> Optional[int]:
    if pd.isna(value) or value is None:
        return None
    # Handle "2021/03" or "2021-06" (year/month) — take the first 4-digit run
    year_match = re.search(r'\b(20\d{2})\b', str(value))
    if year_match:
        year = int(year_match.group(1))
        if MIN_YEAR <= year <= MAX_YEAR:
            return year
        return None
    digits = re.sub(r"[^\d]", "", str(value))
    if len(digits) == 2:
        year = 2000 + int(digits)
        if MIN_YEAR <= year <= MAX_YEAR:
            return year
    return None


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    now = datetime.now().year
    df["age_years"] = df["year"].apply(lambda y: now - y if pd.notna(y) else None)
    df["price_kes"] = df["price_usd"].apply(
        lambda p: round(p * USD_TO_KES, 2) if pd.notna(p) else None
    )
    df["mileage_band"] = pd.cut(
        df["mileage_km"].fillna(-1),
        bins=[-1, 30_000, 60_000, 90_000, 120_000, 150_000, 500_000],
        labels=["0-30k", "30-60k", "60-90k", "90-120k", "120-150k", "150k+"],
        right=True,
    )
    df["engine_band"] = pd.cut(
        df["engine_size_cc"].fillna(-1),
        bins=[-1, 1000, 1500, 2000, 2500, 3000, 8000],
        labels=["≤1000cc", "1001-1500cc", "1501-2000cc", "2001-2500cc", "2501-3000cc", ">3000cc"],
        right=True,
    )
    return df


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    logger.info(f"Cleaning dataframe with {len(df)} rows")

    df = df.copy()

    df["make"] = df["make"].apply(normalize_make)
    df["model"] = df.apply(lambda r: normalize_model(r.get("model"), r.get("make")), axis=1)
    df["body_type"] = df["body_type"].apply(normalize_body_type) if "body_type" in df.columns else None
    df["year"] = df["year"].apply(clean_year)
    df["mileage_km"] = df["mileage_km"].apply(clean_mileage)
    df["engine_size_cc"] = df["engine_size_cc"].apply(clean_engine_size)
    df["price_usd"] = df["price_usd"].apply(clean_price_usd)

    if "fuel_type" in df.columns:
        df["fuel_type"] = df["fuel_type"].str.strip().str.title()
    if "transmission" in df.columns:
        df["transmission"] = df["transmission"].str.strip().str.title()
    if "color" in df.columns:
        df["color"] = df["color"].str.strip().str.title()

    before = len(df)
    df = df.dropna(subset=["make", "price_usd"])
    df = df[df["year"].between(MIN_YEAR, MAX_YEAR, inclusive="both") | df["year"].isna()]
    df = df.drop_duplicates(subset=["source_platform", "url"], keep="first")
    after = len(df)
    logger.info(f"Dropped {before - after} invalid/duplicate rows → {after} clean rows")

    df = add_derived_columns(df)
    df["scraped_at"] = pd.Timestamp.utcnow()
    df["updated_at"] = pd.Timestamp.utcnow()

    logger.info(f"Cleaning complete — {len(df)} rows ready")
    return df