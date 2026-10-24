"""Warehouse & Cold Chain Facility Dashboard for Streamlit."""
import streamlit as st
from streamlit_app.api_client import api_client, ApiException


def render_warehouse_operator_dashboard():
    st.title("❄️ Cold Storage Facility & Environmental Monitoring")
    token = st.session_state.get("token")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Facility Zones", "Monitored")
    with col2:
        st.metric("Sensory Drift Protection", "Active")

    try:
        zones = api_client.get_warehouse_zones(token)
        st.subheader("Storage Zones & Temperature Readings")
        if zones:
            st.dataframe(zones, use_container_width=True)
        else:
            st.info("No cold storage zones currently registered.")
    except ApiException as e:
        st.error(f"Error fetching warehouse zones: {e.message}")
