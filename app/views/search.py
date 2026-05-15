import streamlit as st
import plotly.express as px
import pandas as pd
from utils.db_utils import fetch_listings, get_distinct_values, db_available


def render():
    st.title("🔍 Browse Japan Listings")
    st.markdown("Search and filter vehicles currently listed for export from Japan.")

    if not db_available():
        st.error("Database unavailable. Start Docker with `docker-compose up -d`.")
        return

    with st.sidebar:
        st.subheader("Filter Listings")

        makes = ["All"] + get_distinct_values("make")
        selected_make = st.selectbox("Make", makes)
        make_val = None if selected_make == "All" else selected_make

        models = ["All"]
        if make_val:
            models += get_distinct_values("model")
        selected_model = st.selectbox("Model", models)
        model_val = None if selected_model == "All" else selected_model

        year_range = st.slider("Year of Manufacture", 2018, 2026, (2018, 2026))

        price_range = st.slider("Price (USD)", 0, 50000, (0, 30000), step=500)

        fuels = ["All"] + get_distinct_values("fuel_type")
        selected_fuel = st.selectbox("Fuel Type", fuels)
        fuel_val = None if selected_fuel == "All" else selected_fuel

        transmissions = ["All", "Automatic", "Manual", "CVT"]
        selected_trans = st.selectbox("Transmission", transmissions)
        trans_val = None if selected_trans == "All" else selected_trans

        platforms = ["All"] + get_distinct_values("source_platform")
        selected_platform = st.selectbox("Source Platform", platforms)
        platform_val = None if selected_platform == "All" else selected_platform

        limit = st.slider("Max Results", 50, 1000, 200, 50)

    df = fetch_listings(
        make=make_val,
        model=model_val,
        min_year=year_range[0],
        max_year=year_range[1],
        min_price=price_range[0],
        max_price=price_range[1],
        fuel_type=fuel_val,
        transmission=trans_val,
        platform=platform_val,
        limit=limit,
    )

    st.markdown(f"**{len(df):,} listings** match your filters.")

    if df.empty:
        st.info("No listings found. Try adjusting filters or running the ETL pipeline.")
        return

    display_cols = ["make", "model", "year", "mileage_km", "engine_size_cc",
                    "fuel_type", "transmission", "body_type", "price_usd", "source_platform"]
    avail_cols = [c for c in display_cols if c in df.columns]

    df_display = df[avail_cols].rename(columns={
        "make": "Make", "model": "Model", "year": "Year",
        "mileage_km": "Mileage (km)", "engine_size_cc": "Engine (cc)",
        "fuel_type": "Fuel", "transmission": "Trans.", "body_type": "Body",
        "price_usd": "Price (USD)", "source_platform": "Platform",
    })

    st.dataframe(
        df_display.style.format({"Price (USD)": "${:,.0f}", "Mileage (km)": "{:,.0f}", "Engine (cc)": "{:,.0f}"}),
        use_container_width=True,
        height=400,
    )

    if "price_usd" in df.columns and "mileage_km" in df.columns:
        st.subheader("Price vs Mileage")
        fig = px.scatter(
            df.dropna(subset=["price_usd", "mileage_km"]),
            x="mileage_km",
            y="price_usd",
            color="make" if "make" in df.columns else None,
            hover_data=["make", "model", "year", "fuel_type"],
            labels={"mileage_km": "Mileage (km)", "price_usd": "Price (USD)"},
            title="Price vs Mileage Scatter Plot",
        )
        st.plotly_chart(fig, use_container_width=True)

    if "price_usd" in df.columns:
        st.subheader("Price Distribution")
        fig2 = px.histogram(
            df.dropna(subset=["price_usd"]),
            x="price_usd",
            nbins=40,
            title="Price Distribution (USD)",
            labels={"price_usd": "Price (USD)"},
        )
        st.plotly_chart(fig2, use_container_width=True)

    csv = df[avail_cols].to_csv(index=False)
    st.download_button("⬇ Download Results as CSV", csv, "japan_listings.csv", "text/csv")