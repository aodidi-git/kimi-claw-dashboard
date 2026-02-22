import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="Kimi Claw Dashboard",
    page_icon="🦞",
    layout="wide"
)

# Title
st.title("🦞 Kimi Claw Agent Dashboard")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# Sidebar
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Overview", "Analytics", "Tech Sector Swarm", "Ledger", "Settings"])

# Overview Page
if page == "Overview":
    st.header("System Overview")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Active Agents", "1")
    with col2:
        st.metric("Cron Jobs", "1")
    with col3:
        st.metric("Signals Today", "14")
    
    st.subheader("Recent Activity")
    st.info("Tech Sector Swarm test run completed - 14 signals found across 3 pillars")

# Analytics Page
elif page == "Analytics":
    st.header("📊 Analytics")
    st.subheader("Signals per Pillar")

    # Sample data for the bar chart
    chart_data = pd.DataFrame({
        "Pillar": ["Pillar 1", "Pillar 2", "Pillar 3"],
        "Signals": [5, 7, 2]  # Example data, summing to 14
    })

    st.bar_chart(chart_data.set_index("Pillar"))

# Tech Sector Swarm Page
elif page == "Tech Sector Swarm":
    st.header("📊 Tech Sector Swarm")
    
    st.subheader("Schedule")
    st.json({
        "Research Time": "4:00 AM EST daily",
        "Delivery Time": "7:00 AM EST daily",
        "Next Run": "Tomorrow, 7:00 AM EST",
        "Status": "Active"
    })
    
    st.subheader("Pillars")
    pillars = {
        "Pillar 1": "Core AI & Software - Hyperscalers, model releases",
        "Pillar 2": "Electro-Industrial Stack - Data centers, energy, semiconductors",
        "Pillar 3": "African AI Ecosystem - Infrastructure, partnerships, funding"
    }
    for name, desc in pillars.items():
        st.write(f"**{name}:** {desc}")

# Ledger Page
elif page == "Ledger":
    st.header("📚 AI Investment Ledger")
    
    try:
        with open("AI_Investment_Ledger_2026.md", "r") as f:
            content = f.read()
        st.text_area("Ledger Contents", content, height=400)
    except FileNotFoundError:
        st.warning("Ledger file not found. Run the Tech Sector Swarm to generate data.")
        st.info("Expected file: AI_Investment_Ledger_2026.md")

# Settings Page
elif page == "Settings":
    st.header("⚙️ Settings")
    st.write("Dashboard configuration")
    st.json({
        "Telegram Chat ID": "8487352155",
        "Cron Job": "Tech Sector Swarm - Daily",
        "Model": "kimi-coding/k2p5"
    })

st.sidebar.markdown("---")
st.sidebar.caption("Built with Streamlit")