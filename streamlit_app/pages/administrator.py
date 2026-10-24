"""Platform Administration Dashboard for Streamlit."""
import streamlit as st
from streamlit_app.api_client import api_client, ApiException


def render_administrator_dashboard():
    st.title("🛡️ Platform Administration & Infrastructure")
    token = st.session_state.get("token")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("System Authority", "Superuser")
    with col2:
        st.metric("Database Health", "Connected")
    with col3:
        st.metric("RBAC Matrix", "Enforced")

    try:
        kpis = api_client.get_admin_kpis(token)
        st.subheader("System Performance KPIs")
        st.json(kpis)

        st.subheader("Registered User Accounts")
        users = api_client.get_admin_users(token)
        if users:
            st.dataframe(users, use_container_width=True)
    except ApiException as e:
        st.error(f"Error loading admin statistics: {e.message}")
