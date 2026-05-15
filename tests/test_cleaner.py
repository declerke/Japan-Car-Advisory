import pytest
import pandas as pd
from etl.cleaner import (
    normalize_make,
    normalize_body_type,
    clean_year,
    clean_mileage,
    clean_engine_size,
    clean_price_usd,
    clean_dataframe,
)


# ── normalize_make ────────────────────────────────────────────────────────────

def test_normalize_make_uppercase():
    assert normalize_make("TOYOTA") == "Toyota"
    assert normalize_make("HONDA") == "Honda"
    assert normalize_make("NISSAN") == "Nissan"


def test_normalize_make_alias():
    assert normalize_make("DATSUN") == "Nissan"
    assert normalize_make("VW") == "Volkswagen"


def test_normalize_make_none():
    assert normalize_make(None) is None
    assert normalize_make("") is None


# ── normalize_body_type ───────────────────────────────────────────────────────

def test_normalize_body_type():
    assert normalize_body_type("sedan") == "Sedan"
    assert normalize_body_type("SUV") == "SUV"
    assert normalize_body_type("saloon") == "Sedan"
    assert normalize_body_type("crossover") == "SUV"
    assert normalize_body_type(None) is None


# ── clean_year ────────────────────────────────────────────────────────────────

def test_clean_year_valid():
    assert clean_year("2021") == 2021
    assert clean_year(2020) == 2020
    assert clean_year("2021/03") == 2021


def test_clean_year_below_min_returns_none():
    assert clean_year("2013") is None
    assert clean_year("2014") is None


def test_clean_year_none():
    assert clean_year(None) is None


# ── clean_mileage ─────────────────────────────────────────────────────────────

def test_clean_mileage_formatted():
    assert clean_mileage("80,350 km") == 80350
    assert clean_mileage("80350") == 80350
    assert clean_mileage("80350KM") == 80350


def test_clean_mileage_none():
    assert clean_mileage(None) is None


def test_clean_mileage_exceeds_max():
    assert clean_mileage("999999") is None


# ── clean_engine_size ─────────────────────────────────────────────────────────

def test_clean_engine_size():
    assert clean_engine_size("1,800cc") == 1800
    assert clean_engine_size("2400CC") == 2400
    assert clean_engine_size("660") == 660


def test_clean_engine_size_out_of_range():
    assert clean_engine_size("300") is None   # below min
    assert clean_engine_size("9000") is None  # above max


# ── clean_price_usd ───────────────────────────────────────────────────────────

def test_clean_price_usd():
    assert clean_price_usd("$10,000") == 10000.0
    assert clean_price_usd("8500.00") == 8500.0
    assert clean_price_usd("8500 USD") == 8500.0


def test_clean_price_usd_out_of_range():
    assert clean_price_usd("100") is None       # below min $500
    assert clean_price_usd("999999") is None    # above max $200k


# ── clean_dataframe ───────────────────────────────────────────────────────────

@pytest.fixture
def sample_df():
    return pd.DataFrame([
        {
            "source_platform": "BE FORWARD",
            "url": "https://www.beforward.jp/toyota/corolla/abc/id/1/",
            "make": "TOYOTA",
            "model": "Corolla",
            "year": 2021,
            "price_usd": 8_000,
            "mileage_km": 50_000,
            "engine_size_cc": 1800,
        },
        {
            "source_platform": "BE FORWARD",
            "url": "https://www.beforward.jp/honda/fit/def/id/2/",
            "make": "HONDA",
            "model": "Fit",
            "year": 2015,         # below MIN_YEAR — should be dropped
            "price_usd": 5_000,
            "mileage_km": 80_000,
            "engine_size_cc": 1300,
        },
        {
            "source_platform": "BE FORWARD",
            "url": "https://www.beforward.jp/nissan/note/ghi/id/3/",
            "make": "NISSAN",
            "model": "Note",
            "year": 2020,
            "price_usd": None,    # no price — should be dropped
            "mileage_km": 30_000,
            "engine_size_cc": 1200,
        },
        {
            "source_platform": "BE FORWARD",
            "url": "https://www.beforward.jp/toyota/corolla/abc/id/1/",  # duplicate URL
            "make": "TOYOTA",
            "model": "Corolla",
            "year": 2021,
            "price_usd": 8_000,
            "mileage_km": 50_000,
            "engine_size_cc": 1800,
        },
    ])


def test_clean_dataframe_drops_invalid_year(sample_df):
    result = clean_dataframe(sample_df)
    assert all(result["year"].dropna() >= 2015)


def test_clean_dataframe_drops_missing_price(sample_df):
    result = clean_dataframe(sample_df)
    assert result["price_usd"].notna().all()


def test_clean_dataframe_deduplicates(sample_df):
    result = clean_dataframe(sample_df)
    assert result.duplicated(subset=["source_platform", "url"]).sum() == 0


def test_clean_dataframe_normalizes_make(sample_df):
    result = clean_dataframe(sample_df)
    assert "Toyota" in result["make"].values


def test_clean_dataframe_adds_price_kes(sample_df):
    result = clean_dataframe(sample_df)
    assert "price_kes" in result.columns
    assert result["price_kes"].notna().any()
