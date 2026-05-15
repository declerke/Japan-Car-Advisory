import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import os
from utils.db_utils import fetch_listings, get_distinct_values, get_models_for_make, db_available
from calculator.import_calculator import ImportCostCalculator

USD_TO_KES = float(os.getenv("USD_TO_KES", 130.0))

SAMPLE_LOCAL_PRICES = {
    ("Toyota", "Corolla"): {"2018": 1_650_000, "2019": 1_800_000, "2020": 2_000_000, "2021": 2_200_000, "2022": 2_450_000},
    ("Toyota", "Vitz"): {"2018": 950_000, "2019": 1_050_000, "2020": 1_150_000, "2021": 1_250_000},
    ("Toyota", "Harrier"): {"2018": 2_800_000, "2019": 3_100_000, "2020": 3_500_000, "2021": 3_900_000},
    ("Toyota", "Prado"): {"2018": 5_000_000, "2019": 5_800_000, "2020": 6_500_000},
    ("Honda", "Fit"): {"2018": 850_000, "2019": 950_000, "2020": 1_050_000, "2021": 1_150_000},
    ("Honda", "CRV"): {"2018": 2_600_000, "2019": 2_900_000, "2020": 3_200_000},
    ("Mazda", "Demio"): {"2018": 850_000, "2019": 950_000, "2020": 1_050_000},
    ("Nissan", "Note"): {"2018": 900_000, "2019": 1_000_000, "2020": 1_100_000},
    ("Subaru", "Forester"): {"2018": 2_200_000, "2019": 2_500_000, "2020": 2_800_000},
    ("Suzuki", "Swift"): {"2018": 750_000, "2019": 850_000, "2020": 950_000},
}


def get_sample_local_price(make: str, model: str, year: int) -> int:
    key = (make, model)
    if key in SAMPLE_LOCAL_PRICES:
        prices = SAMPLE_LOCAL_PRICES[key]
        if str(year) in prices:
            return prices[str(year)]
        closest = min(prices.keys(), key=lambda y: abs(int(y) - year))
        return prices[closest]
    return 0


def render():
    st.title("📊 Import vs Local Comparison")
    st.markdown(
        "Compare the full landed cost of importing from Japan against equivalent vehicles "
        "in the Kenyan local market and identify potential savings."
    )
    st.warning(
        "⚠ Local market prices shown are sample/indicative figures for illustration. "
        "Always verify current prices with local dealers and consult KRA/clearing agents.",
        icon="⚠️",
    )

    if not db_available():
        st.error("Database unavailable. Run `docker-compose up -d` to start.")
        return

    calc = ImportCostCalculator(usd_to_kes=USD_TO_KES)

    with st.sidebar:
        st.subheader("Search Parameters")
        makes = get_distinct_values("make") or ["Toyota", "Honda", "Nissan", "Mazda"]
        make = st.selectbox("Make", makes, index=0)
        model_options = get_models_for_make(make) or ["Corolla", "Vitz", "Harrier"]
        model = st.selectbox("Model", model_options, index=0)
        year = st.slider("Year (±2 window)", 2015, 2026, 2021)
        max_results = st.slider("Max Listings", 10, 200, 50)

    # ±2 year window so minor year gaps in the DB don't return empty
    df = fetch_listings(make=make, model=model, min_year=year - 2, max_year=year + 2, limit=max_results)

    if df.empty:
        st.info(f"No listings found for {make} {model} ({year}). Try a different year or make.")
        return

    df = df.dropna(subset=["price_usd"])
    local_price = get_sample_local_price(make, model, year)

    import_costs = []
    for _, row in df.iterrows():
        try:
            breakdown = calc.calculate(
                purchase_price_usd=float(row["price_usd"]),
                engine_size_cc=int(row.get("engine_size_cc", 1800) or 1800),
                year=int(row.get("year", year) or year),
                make=str(row.get("make", make)),
                model=str(row.get("model", model)),
            )
            comparison = calc.compare_with_local(breakdown, local_price) if local_price else {}
            import_costs.append({
                "source_platform": row.get("source_platform", "Unknown"),
                "mileage_km": row.get("mileage_km"),
                "engine_size_cc": row.get("engine_size_cc"),
                "fuel_type": row.get("fuel_type"),
                "transmission": row.get("transmission"),
                "purchase_price_usd": breakdown.purchase_price_usd,
                "total_landed_kes": breakdown.total_landed_kes,
                "import_duty_kes": breakdown.import_duty_kes,
                "excise_duty_kes": breakdown.excise_duty_kes,
                "vat_kes": breakdown.vat_kes,
                "other_charges_kes": breakdown.port_charges_kes + breakdown.clearing_fees_kes + breakdown.ntsa_registration_kes + breakdown.inspection_fees_kes,
                "savings_kes": comparison.get("savings_kes", 0),
                "savings_pct": comparison.get("savings_pct", 0),
            })
        except Exception:
            continue

    if not import_costs:
        st.warning("Could not calculate import costs for these listings.")
        return

    result_df = pd.DataFrame(import_costs)

    st.subheader(f"Summary — {make} {model} ({year - 2}–{year + 2})")
    avg_landed = result_df["total_landed_kes"].mean()
    min_landed = result_df["total_landed_kes"].min()
    max_landed = result_df["total_landed_kes"].max()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Avg Import Cost", f"KES {avg_landed:,.0f}")
    col2.metric("Min Import Cost", f"KES {min_landed:,.0f}")
    col3.metric("Max Import Cost", f"KES {max_landed:,.0f}")
    if local_price > 0:
        avg_savings = local_price - avg_landed
        col4.metric("Avg Savings vs Local", f"KES {avg_savings:,.0f}", delta=f"{(avg_savings/local_price)*100:.1f}%")
    else:
        col4.metric("Local Price", "Not Available")

    if local_price > 0:
        cheaper_count = (result_df["total_landed_kes"] < local_price).sum()
        total = len(result_df)
        st.success(f"**{cheaper_count} of {total} listings ({cheaper_count/total*100:.0f}%)** are cheaper to import than the local equivalent (KES {local_price:,.0f})")

    st.subheader("Cost Breakdown Distribution")
    fig = go.Figure()
    fig.add_trace(go.Box(y=result_df["total_landed_kes"], name="Total Landed", marker_color="#1f77b4"))
    if local_price > 0:
        fig.add_hline(y=local_price, line_dash="dash", line_color="red", annotation_text=f"Local Price: KES {local_price:,.0f}")
    fig.update_layout(title=f"Import Cost Distribution — {make} {model} {year-2}–{year+2}", yaxis_title="KES")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Price vs Mileage with Import Cost")
    fig2 = px.scatter(
        result_df.dropna(subset=["mileage_km"]),
        x="mileage_km",
        y="total_landed_kes",
        color="source_platform",
        size="purchase_price_usd",
        hover_data=["fuel_type", "transmission", "engine_size_cc"],
        title=f"Landed Cost vs Mileage — {make} {model} {year-2}–{year+2}",
        labels={"mileage_km": "Mileage (km)", "total_landed_kes": "Total Landed (KES)"},
    )
    if local_price > 0:
        fig2.add_hline(y=local_price, line_dash="dash", line_color="red", annotation_text="Local Market Price")
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Average Cost Component Breakdown")
    avg_components = {
        "Purchase": result_df["purchase_price_usd"].mean() * USD_TO_KES,
        "Shipping": 1500 * USD_TO_KES,
        "Import Duty": result_df["import_duty_kes"].mean(),
        "Excise Duty": result_df["excise_duty_kes"].mean(),
        "VAT": result_df["vat_kes"].mean(),
        "Other Charges": result_df["other_charges_kes"].mean(),
    }
    fig3 = px.bar(
        x=list(avg_components.keys()),
        y=list(avg_components.values()),
        title="Average Cost Composition (KES)",
        labels={"x": "Component", "y": "KES"},
        color=list(avg_components.keys()),
    )
    st.plotly_chart(fig3, use_container_width=True)

    st.subheader("All Listings with Import Costs")
    display = result_df.rename(columns={
        "source_platform": "Platform", "mileage_km": "Mileage (km)",
        "fuel_type": "Fuel", "transmission": "Trans.",
        "purchase_price_usd": "Price (USD)", "total_landed_kes": "Landed (KES)",
        "savings_kes": "Savings vs Local (KES)", "savings_pct": "Savings (%)",
    })
    st.dataframe(
        display.style.format({
            "Price (USD)": "${:,.0f}", "Landed (KES)": "KES {:,.0f}",
            "Savings vs Local (KES)": "KES {:,.0f}", "Savings (%)": "{:.1f}%",
            "Mileage (km)": "{:,.0f}",
        }),
        use_container_width=True,
    )