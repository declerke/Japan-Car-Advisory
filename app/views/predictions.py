import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import os
from models.price_predictor import PricePredictor, train_and_select_best
from utils.db_utils import get_distinct_values

USD_TO_KES = float(os.getenv("USD_TO_KES", 130.0))


@st.cache_resource
def load_predictor():
    return PricePredictor()


def render():
    st.title("🤖 ML Price Prediction")
    st.markdown(
        "Use our trained machine learning model to predict a fair Japan export price "
        "for any vehicle based on its key features."
    )

    predictor = load_predictor()

    if not predictor.is_ready():
        st.warning("No trained model found.")
        st.info("Train the model by running: `python -m models.price_predictor`")
        if st.button("Train Model Now (requires database data)"):
            with st.spinner("Training model — this may take a few minutes..."):
                try:
                    meta = train_and_select_best()
                    st.success(f"Model trained! Best: {meta['model_name']} | MAE: ${meta['best_metrics']['MAE']:,.0f}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Training failed: {e}")
        return

    meta = predictor.meta
    st.success(
        f"Model ready: **{meta.get('model_name', 'Unknown')}** | "
        f"MAE: **${meta.get('best_metrics', {}).get('MAE', 0):,.0f}** | "
        f"R²: **{meta.get('best_metrics', {}).get('R2', 0):.3f}** | "
        f"Trained: {meta.get('trained_at', '')[:10]}"
    )

    with st.form("predict_form"):
        st.subheader("Vehicle Features")
        col1, col2, col3 = st.columns(3)

        with col1:
            makes = get_distinct_values("make") or ["Toyota", "Honda", "Nissan", "Mazda", "Subaru"]
            make = st.selectbox("Make", makes)
            models = get_distinct_values("model") or ["Corolla", "Vitz", "Harrier", "Fit"]
            model = st.selectbox("Model", models)
            year = st.number_input("Year", min_value=2018, max_value=2026, value=2020)

        with col2:
            mileage = st.number_input("Mileage (km)", min_value=0, max_value=500000, value=50000, step=5000)
            engine_cc = st.number_input("Engine Size (cc)", min_value=600, max_value=8000, value=1800, step=100)
            fuel = st.selectbox("Fuel Type", ["Petrol", "Diesel", "Hybrid", "Electric", "Plug-in Hybrid"])

        with col3:
            trans = st.selectbox("Transmission", ["Automatic", "Manual", "CVT"])
            body = st.selectbox("Body Type", ["Sedan", "SUV", "Hatchback", "Wagon", "Van", "Pickup", "Coupe"])
            platform = st.selectbox("Source Platform", ["BE FORWARD", "SBT Japan", "Car From Japan", "AAA Japan", "JapaneseCarTrade"])

        predict_btn = st.form_submit_button("Predict Price", type="primary")

    if predict_btn:
        with st.spinner("Running prediction..."):
            result = predictor.predict(
                make=make, model=str(model), year=year, mileage_km=mileage,
                engine_size_cc=engine_cc, fuel_type=fuel, transmission=trans,
                body_type=body, source_platform=platform,
            )

        if "error" in result:
            st.error(result["error"])
            return

        pred = result["predicted_price_usd"]
        lower = result["lower_bound_usd"]
        upper = result["upper_bound_usd"]

        st.divider()
        st.subheader("Prediction Results")

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Predicted Price (USD)", f"${pred:,.0f}")
        col_b.metric("Lower Bound (USD)", f"${lower:,.0f}")
        col_c.metric("Upper Bound (USD)", f"${upper:,.0f}")

        col_d, col_e, col_f = st.columns(3)
        col_d.metric("Predicted Price (KES)", f"KES {pred * USD_TO_KES:,.0f}")
        col_e.metric("Lower Bound (KES)", f"KES {lower * USD_TO_KES:,.0f}")
        col_f.metric("Upper Bound (KES)", f"KES {upper * USD_TO_KES:,.0f}")

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=["Lower Estimate", "Predicted Price", "Upper Estimate"],
            y=[lower, pred, upper],
            marker_color=["#aec6cf", "#1f77b4", "#aec6cf"],
            text=[f"${v:,.0f}" for v in [lower, pred, upper]],
            textposition="outside",
        ))
        fig.update_layout(
            title=f"Price Prediction Range — {make} {model} ({year})",
            yaxis_title="USD",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.caption(f"Model: {result['model_used']} | {result['confidence_note']}")

        st.divider()
        st.subheader("Model Performance Summary")
        if meta.get("metrics"):
            perf_rows = []
            for model_name, m in meta["metrics"].items():
                perf_rows.append({
                    "Model": model_name,
                    "MAE (USD)": f"${m['MAE']:,.0f}",
                    "RMSE (USD)": f"${m['RMSE']:,.0f}",
                    "R²": f"{m['R2']:.4f}",
                    "MAPE (%)": f"{m['MAPE']:.2f}%",
                    "Selected": "✅" if model_name == meta.get("model_name") else "",
                })
            st.table(pd.DataFrame(perf_rows))

        st.info(
            "**How it works**: The model uses XGBoost/LightGBM trained on real Japan export listings. "
            "Features include make, model, year, mileage, engine size, fuel type, transmission, and body type. "
            "Log transformation of price improves accuracy on skewed distributions."
        )