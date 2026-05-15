import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from utils.db_utils import get_summary_stats, get_price_distribution, db_available


def render():
    st.title("🚗 Japan Car Import Advisory")
    st.markdown(
        """
        **Compare the true cost of importing used vehicles from Japan against buying locally in Kenya.**
        Built using real listings data, 2026 KRA tax rules, and ML price prediction.
        """
    )

    st.warning(
        "⚠ **Disclaimer**: All cost estimates are indicative only. "
        "Consult KRA, a licensed clearing agent, or KEBS for official valuations before making any purchase decision.",
        icon="⚠️",
    )

    if not db_available():
        st.error("Database not available. Start PostgreSQL with `docker-compose up -d` and run the ETL pipeline.")
        _render_demo_banner()
        return

    stats = get_summary_stats()
    if not stats or stats.get("total_listings", 0) == 0:
        st.info("No data yet. Run the ETL pipeline: `python -m etl.pipeline --makes Toyota Honda --max-pages 3`")
        _render_demo_banner()
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Listings", f"{stats.get('total_listings', 0):,}")
    col2.metric("Makes", f"{stats.get('distinct_makes', 0)}")
    col3.metric("Models", f"{stats.get('distinct_models', 0)}")
    col4.metric("Platforms", f"{stats.get('platforms', 0)}")

    col5, col6, col7 = st.columns(3)
    col5.metric("Avg Price (USD)", f"${stats.get('avg_price', 0):,.0f}")
    col6.metric("Price Range", f"${stats.get('min_price', 0):,.0f} – ${stats.get('max_price', 0):,.0f}")
    last_updated = stats.get("last_updated")
    col7.metric("Last Updated", str(last_updated)[:16] if last_updated else "N/A")

    st.divider()
    st.subheader("Price Distribution by Make")
    df = get_price_distribution()
    if not df.empty:
        top_makes = df["make"].value_counts().head(8).index.tolist()
        df_filtered = df[df["make"].isin(top_makes)]
        fig = px.box(
            df_filtered,
            x="make",
            y="price_usd",
            color="make",
            title="Japan Export Price Distribution by Make (USD)",
            labels={"price_usd": "Price (USD)", "make": "Make"},
        )
        fig.update_layout(showlegend=False, plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            fuel_counts = df["fuel_type"].dropna().value_counts().reset_index()
            fuel_counts.columns = ["Fuel Type", "Count"]
            fig2 = px.pie(fuel_counts, values="Count", names="Fuel Type", title="Fuel Type Breakdown")
            st.plotly_chart(fig2, use_container_width=True)

        with col_b:
            year_counts = df["year"].dropna().astype(int).value_counts().sort_index().reset_index()
            year_counts.columns = ["Year", "Count"]
            fig3 = px.bar(year_counts, x="Year", y="Count", title="Listings by Manufacture Year", color="Count", color_continuous_scale="Blues")
            st.plotly_chart(fig3, use_container_width=True)


def _render_demo_banner():
    st.subheader("How It Works")
    steps = [
        ("🕷 Scrape", "Extract car listings from BE FORWARD, SBT Japan, Car From Japan, AAA Japan, JCT"),
        ("🧹 Clean", "Standardise makes, models, prices, engine sizes and remove duplicates"),
        ("💾 Store", "Load into PostgreSQL with full schema for querying and analysis"),
        ("🧮 Calculate", "Apply 2026 KRA rules: import duty (35%), excise, VAT, IDF, RDL, port & clearing"),
        ("📊 Compare", "Side-by-side import cost vs local market price with savings analysis"),
        ("🤖 Predict", "XGBoost/LightGBM model predicts fair Japan market prices from features"),
    ]
    for icon_title, desc in steps:
        st.markdown(f"**{icon_title}** — {desc}")