"""
Seed the japan_listings table with Japan auction data from Kaggle.

Dataset: digillex/japanese-used-car-auction-dataset
  kaggle datasets download -d digillex/japanese-used-car-auction-dataset

Usage:
  # Auto-download (requires ~/.kaggle/kaggle.json credentials)
  python scripts/seed_from_kaggle.py --auto-download

  # Manual CSV path (download ZIP from Kaggle, unzip, then point here)
  python scripts/seed_from_kaggle.py --csv path/to/data.csv

  # Dry run (no DB writes)
  python scripts/seed_from_kaggle.py --csv path/to/data.csv --dry-run
"""

import argparse
import os
import sys
import zipfile
import re
import pandas as pd
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

DATASET_SLUG = "digillex/japanese-used-car-auction-dataset"
DOWNLOAD_DIR = Path("data/kaggle_seed")

# Approximate JPY→USD at time of dataset creation; override with --jpy-rate
DEFAULT_JPY_TO_USD = 0.0067   # 1 JPY ≈ 0.0067 USD (≈ 150 JPY/USD)

MAKE_ALIASES = {
    "TOYOT": "Toyota", "TOY": "Toyota",
    "NISSAN": "Nissan", "NISS": "Nissan",
    "HONDA": "Honda",
    "MAZDA": "Mazda",
    "SUBARU": "Subaru",
    "MITSUBISHI": "Mitsubishi", "MITSU": "Mitsubishi",
    "SUZUKI": "Suzuki",
    "DAIHATSU": "Daihatsu",
    "ISUZU": "Isuzu",
    "LEXUS": "Lexus",
    "INFINITI": "Infiniti",
    "HINO": "Hino",
    "BMW": "BMW",
    "MERCEDES-BENZ": "Mercedes-Benz", "MERCEDES": "Mercedes-Benz",
    "VOLKSWAGEN": "Volkswagen", "VW": "Volkswagen",
    "LAND ROVER": "Land Rover", "LANDROVER": "Land Rover",
}

# Column name mapping: known Kaggle column names → our schema column names
COLUMN_MAP = {
    # Price columns (may be JPY or USD)
    "price": "price_raw",
    "auction_price": "price_raw",
    "sold_price": "price_raw",
    "final_price": "price_raw",
    "sale_price": "price_raw",
    "estimated_price": "price_raw",
    "bid_price": "price_raw",

    # Make/manufacturer
    "maker": "make",
    "manufacturer": "make",
    "brand": "make",
    "make": "make",

    # Model
    "model": "model",
    "car_model": "model",
    "vehicle_model": "model",

    # Year
    "year": "year",
    "model_year": "year",
    "manufacture_year": "year",
    "reg_year": "year",
    "registration_year": "year",

    # Mileage (expect km)
    "mileage": "mileage_km",
    "mileage_km": "mileage_km",
    "odometer": "mileage_km",
    "km": "mileage_km",
    "kilometer": "mileage_km",

    # Engine
    "engine": "engine_size_cc",
    "engine_cc": "engine_size_cc",
    "displacement": "engine_size_cc",
    "engine_displacement": "engine_size_cc",
    "engine_size": "engine_size_cc",

    # Fuel
    "fuel": "fuel_type",
    "fuel_type": "fuel_type",
    "fuel_kind": "fuel_type",

    # Transmission
    "transmission": "transmission",
    "gearbox": "transmission",
    "trans": "transmission",

    # Body type
    "body": "body_type",
    "body_type": "body_type",
    "body_style": "body_type",

    # Color
    "color": "color",
    "colour": "color",

    # Grade
    "grade": "grade",
    "auction_grade": "grade",
    "score": "grade",
}

ALLOWED_MAKES = set(MAKE_ALIASES.values()) | {
    "Toyota", "Honda", "Nissan", "Mazda", "Subaru", "Mitsubishi",
    "Suzuki", "Daihatsu", "Isuzu", "Lexus", "Infiniti",
    "BMW", "Mercedes-Benz", "Volkswagen", "Land Rover",
}

FUEL_MAP = {
    "ガソリン": "Petrol", "petrol": "Petrol", "gasoline": "Petrol", "gas": "Petrol",
    "diesel": "Diesel", "ディーゼル": "Diesel",
    "hybrid": "Hybrid", "ハイブリッド": "Hybrid", "hv": "Hybrid",
    "electric": "Electric", "ev": "Electric",
    "lpg": "LPG", "cng": "CNG",
}

TRANS_MAP = {
    "at": "Automatic", "auto": "Automatic", "automatic": "Automatic", "自動": "Automatic",
    "mt": "Manual", "manual": "Manual", "手動": "Manual",
    "cvt": "CVT",
    "semi-auto": "Semi-Automatic",
}


def _normalize_make(raw: str) -> str:
    if not raw:
        return raw
    upper = str(raw).strip().upper()
    for alias, canonical in MAKE_ALIASES.items():
        if upper.startswith(alias):
            return canonical
    return str(raw).strip().title()


def _normalize_fuel(raw) -> str:
    if pd.isna(raw) or not raw:
        return None
    lower = str(raw).strip().lower()
    for k, v in FUEL_MAP.items():
        if k in lower:
            return v
    return str(raw).strip().title()


def _normalize_transmission(raw) -> str:
    if pd.isna(raw) or not raw:
        return None
    lower = str(raw).strip().lower()
    for k, v in TRANS_MAP.items():
        if k == lower or lower.startswith(k):
            return v
    return str(raw).strip().title()


def _clean_numeric(val) -> float:
    if pd.isna(val):
        return None
    cleaned = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _detect_price_currency(series: pd.Series) -> str:
    """Return 'jpy' if median value suggests JPY (>100,000), else 'usd'."""
    median = series.dropna().median()
    return "jpy" if median > 50_000 else "usd"


def _remap_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for col in df.columns:
        mapped = COLUMN_MAP.get(col.lower().strip().replace(" ", "_"))
        if mapped:
            rename[col] = mapped
    df = df.rename(columns=rename)
    logger.info(f"Column remapping: {rename}")
    return df


def download_dataset(download_dir: Path) -> Path:
    try:
        import kaggle
    except ImportError:
        logger.error("kaggle package not installed. Run: pip install kaggle")
        sys.exit(1)

    download_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading {DATASET_SLUG} → {download_dir}")
    kaggle.api.authenticate()
    kaggle.api.dataset_download_files(DATASET_SLUG, path=str(download_dir), unzip=True)
    logger.info("Download complete")

    csvs = list(download_dir.glob("*.csv"))
    if not csvs:
        raise FileNotFoundError(f"No CSV found in {download_dir} after download")
    return csvs[0]


def find_csv(download_dir: Path) -> Path:
    for pattern in ["*.csv", "**/*.csv"]:
        hits = list(download_dir.glob(pattern))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"No CSV found under {download_dir}")


def load_csv(csv_path: Path) -> pd.DataFrame:
    logger.info(f"Reading CSV: {csv_path}")
    for enc in ["utf-8", "utf-8-sig", "latin-1", "cp932"]:
        try:
            df = pd.read_csv(csv_path, encoding=enc, low_memory=False)
            logger.info(f"Loaded {len(df):,} rows with encoding={enc}")
            logger.info(f"Columns: {list(df.columns)}")
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {csv_path}")


def transform(df: pd.DataFrame, jpy_to_usd: float) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df = _remap_columns(df)

    # ── Price ──────────────────────────────────────────────────────────────────
    if "price_raw" not in df.columns:
        price_candidates = [c for c in df.columns if "price" in c or "amount" in c or "value" in c]
        if price_candidates:
            df["price_raw"] = df[price_candidates[0]]
            logger.info(f"Using '{price_candidates[0]}' as price column")
        else:
            logger.warning("No price column found — price_usd will be null")
            df["price_raw"] = None

    df["price_raw"] = df["price_raw"].apply(_clean_numeric)
    currency = _detect_price_currency(df["price_raw"])
    logger.info(f"Detected price currency: {currency.upper()}")

    if currency == "jpy":
        df["price_usd"] = df["price_raw"] * jpy_to_usd
        df["price_jpy"] = df["price_raw"]
    else:
        df["price_usd"] = df["price_raw"]
        df["price_jpy"] = None

    # ── Make ───────────────────────────────────────────────────────────────────
    if "make" not in df.columns:
        logger.warning("No make column found")
        df["make"] = None
    else:
        df["make"] = df["make"].apply(lambda x: _normalize_make(str(x)) if pd.notna(x) else None)

    # ── Model ──────────────────────────────────────────────────────────────────
    if "model" not in df.columns:
        df["model"] = None
    else:
        df["model"] = df["model"].apply(lambda x: str(x).strip().title() if pd.notna(x) else None)

    # ── Year ───────────────────────────────────────────────────────────────────
    if "year" not in df.columns:
        df["year"] = None
    else:
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        # Handle 2-digit years (Japanese era remnants)
        df["year"] = df["year"].apply(lambda y: 2000 + int(y) if pd.notna(y) and 0 < y < 100 else y)

    # ── Mileage ────────────────────────────────────────────────────────────────
    if "mileage_km" not in df.columns:
        mileage_candidates = [c for c in df.columns if "mile" in c or "km" in c or "odometer" in c]
        if mileage_candidates:
            df["mileage_km"] = df[mileage_candidates[0]].apply(_clean_numeric)
    else:
        df["mileage_km"] = df["mileage_km"].apply(_clean_numeric)

    # ── Engine ─────────────────────────────────────────────────────────────────
    if "engine_size_cc" not in df.columns:
        engine_candidates = [c for c in df.columns if "engine" in c or "cc" in c or "displacement" in c]
        if engine_candidates:
            df["engine_size_cc"] = df[engine_candidates[0]].apply(_clean_numeric)
    else:
        df["engine_size_cc"] = df["engine_size_cc"].apply(_clean_numeric)

    # ── Fuel / Transmission ────────────────────────────────────────────────────
    if "fuel_type" in df.columns:
        df["fuel_type"] = df["fuel_type"].apply(_normalize_fuel)
    if "transmission" in df.columns:
        df["transmission"] = df["transmission"].apply(_normalize_transmission)
    if "color" in df.columns:
        df["color"] = df["color"].apply(lambda x: str(x).strip().title() if pd.notna(x) else None)
    if "grade" in df.columns:
        df["grade"] = df["grade"].apply(lambda x: str(x).strip() if pd.notna(x) else None)

    df["source_platform"] = "Japan Auction"
    df["url"] = df.apply(
        lambda r: f"https://auction.seed/{r.get('make','unknown')}/{r.get('model','unknown')}/{r.name}",
        axis=1,
    )

    return df


def filter_and_validate(df: pd.DataFrame, min_year: int, max_price_usd: float) -> pd.DataFrame:
    before = len(df)

    df = df.dropna(subset=["make", "price_usd"])
    df = df[df["price_usd"].between(500, max_price_usd)]
    if "year" in df.columns:
        df = df[df["year"].isna() | df["year"].between(min_year, 2026)]
    if "mileage_km" in df.columns:
        df = df[df["mileage_km"].isna() | df["mileage_km"].between(0, 500_000)]
    if "engine_size_cc" in df.columns:
        df = df[df["engine_size_cc"].isna() | df["engine_size_cc"].between(600, 8_000)]

    # Keep only known Japanese/common makes (drop garbage rows)
    if df["make"].notna().any():
        df = df[df["make"].isin(ALLOWED_MAKES)]

    after = len(df)
    logger.info(f"Validation: {before:,} → {after:,} rows ({before - after:,} dropped)")
    return df.reset_index(drop=True)


def seed_to_db(df: pd.DataFrame, dry_run: bool) -> dict:
    from etl.loader import upsert_japan_listings
    from etl.cleaner import add_derived_columns
    import pandas as _pd

    schema_cols = [
        "source_platform", "url", "make", "model", "grade", "year",
        "mileage_km", "engine_size_cc", "fuel_type", "transmission",
        "body_type", "color", "price_usd", "price_jpy",
    ]
    available = [c for c in schema_cols if c in df.columns]
    out = df[available].copy()

    for col in ["price_usd", "mileage_km", "engine_size_cc", "price_jpy"]:
        if col in out.columns:
            out[col] = _pd.to_numeric(out[col], errors="coerce")
    for col in ["year"]:
        if col in out.columns:
            out[col] = _pd.to_numeric(out[col], errors="coerce").astype("Int64").where(out[col].notna(), None)

    out = add_derived_columns(out)

    if dry_run:
        logger.info(f"[DRY RUN] Would upsert {len(out):,} rows")
        logger.info(f"\nSample:\n{out.head(3).to_string()}")
        return {"inserted": 0, "updated": 0, "errors": 0, "dry_run": True}

    logger.info(f"Upserting {len(out):,} rows to japan_listings...")
    result = upsert_japan_listings(out)
    logger.info(f"Done: {result}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Seed japan_listings from Kaggle Japan auction dataset")
    parser.add_argument("--auto-download", action="store_true", help="Download via Kaggle API (requires ~/.kaggle/kaggle.json)")
    parser.add_argument("--csv", type=str, help="Path to already-downloaded CSV file")
    parser.add_argument("--jpy-rate", type=float, default=DEFAULT_JPY_TO_USD, help=f"JPY→USD rate (default {DEFAULT_JPY_TO_USD})")
    parser.add_argument("--min-year", type=int, default=2015, help="Minimum year to keep (default 2015)")
    parser.add_argument("--max-price-usd", type=float, default=200_000, help="Max price in USD to keep")
    parser.add_argument("--limit", type=int, default=10_000, help="Max rows to load (default 10,000)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate but don't write to DB")
    args = parser.parse_args()

    if not args.auto_download and not args.csv:
        print(__doc__)
        parser.error("Provide --auto-download or --csv <path>")

    if args.auto_download:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        csv_path = download_dataset(DOWNLOAD_DIR)
    else:
        csv_path = Path(args.csv)
        if not csv_path.exists():
            logger.error(f"CSV not found: {csv_path}")
            sys.exit(1)

    raw = load_csv(csv_path)
    df = transform(raw, jpy_to_usd=args.jpy_rate)
    df = filter_and_validate(df, min_year=args.min_year, max_price_usd=args.max_price_usd)

    if args.limit and len(df) > args.limit:
        df = df.sample(n=args.limit, random_state=42)
        logger.info(f"Sampled to {args.limit:,} rows")

    logger.info(f"\nMake distribution:\n{df['make'].value_counts().head(15).to_string()}")
    logger.info(f"Price range: ${df['price_usd'].min():,.0f} – ${df['price_usd'].max():,.0f} | Median: ${df['price_usd'].median():,.0f}")
    if "year" in df.columns:
        logger.info(f"Year range: {df['year'].min()} – {df['year'].max()}")

    result = seed_to_db(df, dry_run=args.dry_run)
    logger.success(f"Seed complete: {result}")


if __name__ == "__main__":
    main()
