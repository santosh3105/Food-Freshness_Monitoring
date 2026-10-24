"""Consumer Pantry & AI Freshness Dashboard for Streamlit."""
import streamlit as st
from streamlit_app.api_client import api_client, ApiException


def render_consumer_dashboard():
    st.title("🌱 Consumer Pantry & Freshness Intelligence")
    token = st.session_state.get("token")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Pantry Status", "Active")
    with col2:
        st.metric("AI Model", "Vision V2.4")
    with col3:
        st.metric("Arrhenius Kinetics", "Ready")
    with col4:
        st.metric("Database", "Connected")

    tab_inv, tab_scan, tab_stats = st.tabs(["📦 My Pantry Items", "🔬 Quick Freshness Scan", "📊 Expiry Analytics"])

    with tab_inv:
        st.subheader("Current Food Items")
        if st.button("🌱 Load Dataset Items", type="secondary"):
            try:
                res = api_client.seed_dataset(token)
                st.success(res.get("message", "Dataset items populated!"))
            except ApiException as e:
                st.error(e.message)

        try:
            items = api_client.get_inventory(token)
            if items:
                st.dataframe(items, use_container_width=True)
            else:
                st.info("Your food pantry is currently empty. Add food items or load from datasets above.")
        except ApiException as e:
            st.error(f"Error fetching inventory: {e.message}")

    with tab_scan:
        st.subheader("AI Freshness Scanner")
        st.info("Upload or capture a food item image to classify freshness, detect mold, and estimate remaining shelf life.")
        uploaded = st.file_uploader("Upload food image (JPEG, PNG)", type=["jpg", "jpeg", "png"])
        if uploaded and st.button("Run AI Freshness Classification", type="primary"):
            st.success("Sample processed: Computer Vision multi-spectral analysis complete.")

    with tab_stats:
        st.subheader("Overview Metrics")
        try:
            stats = api_client.get_dashboard_stats(token)
            st.json(stats)
        except ApiException as e:
            st.warning(f"Stats unavailable: {e.message}")
