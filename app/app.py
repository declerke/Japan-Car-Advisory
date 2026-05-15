import sys
import os

# Add project root so ETL/model modules resolve correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Ensure app/ is in path so views/ resolves as a local package
_app_dir = os.path.dirname(os.path.abspath(__file__))
if _app_dir not in sys.path:
    sys.path.insert(1, _app_dir)

import streamlit as st

st.set_page_config(
    page_title="Japan Car Import Advisory",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Import as local packages (app/ is in sys.path, so views/ resolves without 'app.' prefix)
from views import home, search, calculator, comparisons, predictions

PAGES = {
    "🏠 Overview": home,
    "🔍 Browse Listings": search,
    "🧮 Import Calculator": calculator,
    "📊 Import vs Local": comparisons,
    "🤖 ML Predictions": predictions,
}

with st.sidebar:
    st.markdown("### Navigation")
    selection = st.radio("", list(PAGES.keys()), label_visibility="collapsed")

    st.divider()
    st.markdown(
        """
        **Japan Car Import Advisory**

        An educational data engineering and ML platform for Kenyan car buyers.

        *Compares Japan import costs vs local prices using real data and 2026 KRA rules.*
        """
    )
    st.caption("⚠ For educational purposes only. Not financial advice.")

page = PAGES[selection]
page.render()
