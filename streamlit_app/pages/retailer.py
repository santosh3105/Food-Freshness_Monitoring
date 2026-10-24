"""Retailer Store Operations & Waste Minimization Dashboard for Streamlit."""
import streamlit as st
from streamlit_app.api_client import api_client, ApiException


def render_retailer_dashboard():
    st.title("🏪 Retailer Produce & Inventory Management")
    token = st.session_state.get("token")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Store Mode", "Supermarket")
    with col2:
        st.metric("FEFO Engine", "Active")
    with col3:
        st.metric("Waste Minimization", "Enabled")

    try:
        items = api_client.get_retailer_inventory(token)
        st.subheader(f"Active Retail Stock ({len(items) if items else 0} items)")
        if items:
            st.dataframe(items, use_container_width=True)
        else:
            st.info("No active retailer stock found. Run `seed_retailer_data.py` to populate store inventory.")
    except ApiException as e:
        st.error(f"Error loading retailer inventory: {e.message}")
