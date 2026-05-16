import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import os
from calculator.import_calculator import ImportCostCalculator
from utils.db_utils import get_distinct_values, get_models_for_make

USD_TO_KES = float(os.getenv("USD_TO_KES", 130.0))


def render():
    st.title("🧮 Import Cost Calculator")
    st.markdown(
        "Estimate the **full landed cost** of importing a vehicle from Japan to Kenya, "
        "including all 2026 KRA taxes, duties, port charges, and registration fees."
    )
    st.warning(
        "⚠ **Disclaimer**: Figures are estimates only. "
        "KRA uses CRSP values which may differ from purchase price. "
        "Always consult a licensed clearing agent or KRA before making decisions.",
        icon="⚠️",
    )

    calculator = ImportCostCalculator(usd_to_kes=USD_TO_KES)

    # Make and model are outside the form so the model list updates dynamically
    # when the make changes — st.form freezes widget state until submit.
    st.subheader("Vehicle Details")
    col_make, col_model = st.columns(2)
    with col_make:
        makes = get_distinct_values("make")
        default_make_idx = makes.index("Toyota") if "Toyota" in makes else 0
        make = st.selectbox("Make", makes, index=default_make_idx)
    with col_model:
        models = get_models_for_make(make)
        default_model_idx = models.index("Corolla") if "Corolla" in models else 0
        model = st.selectbox("Model", models, index=default_model_idx)

    with st.form("cost_calculator"):
        col1, col2, col3 = st.columns(3)

        with col1:
            year = st.number_input("Year", min_value=2018, max_value=2026, value=2021, step=1)

        with col2:
            purchase_price_usd = st.number_input("Purchase Price (USD)", min_value=500, max_value=200000, value=8000, step=100)
            engine_size_cc = st.number_input("Engine Size (cc)", min_value=600, max_value=8000, value=1800, step=100)
            shipping_cost_usd = st.number_input("Shipping Cost (USD)", min_value=800, max_value=5000, value=1500, step=100)

        with col3:
            use_crsp = st.checkbox("Use CRSP Valuation", value=False, help="KRA may use CRSP value instead of purchase price for duty calculation. Check this if you know the CRSP value.")
            crsp_value_usd = None
            if use_crsp:
                crsp_value_usd = st.number_input("CRSP Value (USD)", min_value=500, max_value=300000, value=12000, step=500)
            exchange_rate = st.number_input("USD → KES Rate", min_value=50.0, max_value=300.0, value=USD_TO_KES, step=0.5)

        local_price_kes = st.number_input(
            "Local Market Equivalent Price (KES) — for comparison (optional)",
            min_value=0,
            max_value=50_000_000,
            value=1_800_000,
            step=50_000,
        )

        submitted = st.form_submit_button("Calculate Total Import Cost", type="primary")

    if submitted:
        calc = ImportCostCalculator(usd_to_kes=exchange_rate)
        breakdown = calc.calculate(
            purchase_price_usd=purchase_price_usd,
            engine_size_cc=engine_size_cc,
            year=year,
            make=make,
            model=model,
            shipping_cost_usd=shipping_cost_usd,
            use_crsp=use_crsp,
            crsp_value_usd=crsp_value_usd,
        )

        st.divider()
        st.subheader(f"📊 Full Cost Breakdown — {make} {model} ({year})")

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Total Landed Cost", f"KES {breakdown.total_landed_kes:,.0f}")
        col_b.metric("Total Taxes & Duties", f"KES {breakdown.total_taxes_kes:,.0f}")
        col_c.metric("Total Landed (USD)", f"USD {breakdown.total_landed_usd:,.0f}")

        st.subheader("Detailed Breakdown")
        items = [
            ("Purchase Price", breakdown.purchase_price_usd * exchange_rate, f"USD {breakdown.purchase_price_usd:,.0f}"),
            ("Shipping (Japan → Mombasa)", breakdown.shipping_cost_usd * exchange_rate, f"USD {breakdown.shipping_cost_usd:,.0f}"),
            ("Import Duty (35%)", breakdown.import_duty_kes, f"35% of customs value"),
            (f"Excise Duty ({breakdown.excise_duty_rate*100:.0f}%)", breakdown.excise_duty_kes, f"Engine: {engine_size_cc:,}cc bracket"),
            ("VAT (16%)", breakdown.vat_kes, "On customs + import duty + excise"),
            ("IDF (3.5%)", breakdown.idf_kes, "Import Declaration Fee"),
            ("RDL (2%)", breakdown.rdl_kes, "Railway Development Levy"),
            ("Port Charges", breakdown.port_charges_kes, "Mombasa port handling"),
            ("Clearing Agent Fees", breakdown.clearing_fees_kes, "Clearing agent"),
            ("NTSA Registration", breakdown.ntsa_registration_kes, "Plates and registration"),
            ("Inspection Fees", breakdown.inspection_fees_kes, "Pre-shipment + KEBS"),
        ]

        table_data = {
            "Item": [i[0] for i in items],
            "Amount (KES)": [f"KES {i[1]:,.0f}" for i in items],
            "Notes": [i[2] for i in items],
        }
        st.table(table_data)

        st.subheader("Cost Composition")
        labels = [i[0] for i in items]
        values = [i[1] for i in items]
        fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.4)])
        fig.update_layout(title="Import Cost Composition")
        st.plotly_chart(fig, use_container_width=True)

        if local_price_kes > 0:
            st.divider()
            st.subheader("📈 Import vs Local Comparison")
            comparison = calc.compare_with_local(breakdown, local_price_kes)
            savings = comparison["savings_kes"]
            verdict_color = "🟢" if savings > 0 else "🔴"
            st.markdown(f"### {verdict_color} {comparison['verdict']}")
            st.markdown(f"**{comparison['recommendation']}**")

            col_x, col_y, col_z = st.columns(3)
            col_x.metric("Import Total", f"KES {breakdown.total_landed_kes:,.0f}")
            col_y.metric("Local Price", f"KES {local_price_kes:,.0f}")
            savings_delta = f"KES {abs(savings):,.0f} {'cheaper' if savings > 0 else 'more expensive'}"
            col_z.metric("Difference", savings_delta, delta=f"{comparison['savings_pct']:.1f}%", delta_color="normal" if savings > 0 else "inverse")

            bar_fig = go.Figure([
                go.Bar(name="Import Total (KES)", x=["Cost (KES)"], y=[breakdown.total_landed_kes], marker_color="#1f77b4"),
                go.Bar(name="Local Market (KES)", x=["Cost (KES)"], y=[local_price_kes], marker_color="#ff7f0e"),
            ])
            bar_fig.update_layout(barmode="group", title="Import vs Local Market Cost")
            st.plotly_chart(bar_fig, use_container_width=True)

        st.divider()
        st.subheader("ℹ Notes")
        for note in breakdown.notes:
            st.info(note)