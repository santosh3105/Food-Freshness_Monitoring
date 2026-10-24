"""Food Quality Inspector Dashboard for Streamlit."""
import streamlit as st
from streamlit_app.api_client import api_client, ApiException


def render_food_quality_inspector_dashboard():
    st.title("🔬 Food Safety & Quality Inspection Lab")
    token = st.session_state.get("token")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("QA Certification", "Accredited")
    with col2:
        st.metric("Surface Inspection", "Multi-Spectral")
    with col3:
        st.metric("Microbial Risk", "Active")

    try:
        dash = api_client.get_inspector_dashboard(token)
        st.subheader("Inspection Laboratory Overview")
        st.json(dash)
    except ApiException as e:
        st.error(f"Error loading inspector dashboard: {e.message}")
