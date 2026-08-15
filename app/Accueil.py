import streamlit as st

st.set_page_config(page_title="Ligue 1 Analytics", layout="wide")

st.markdown(
    """
    <style>
    .hero-title { font-size: 3.2rem; font-weight: 800; margin-bottom: 0.2rem; }
    .hero-accent { height: 4px; width: 90px; background: linear-gradient(90deg, #00e5ff, #ff6b6b);
                   border: none; margin: 0.6rem 0 1.6rem 0; border-radius: 2px; }
    .hero-text { font-size: 1.3rem; line-height: 1.7; max-width: 900px; }
    .section-title { font-size: 1.9rem; font-weight: 700; margin-top: 2.2rem; margin-bottom: 0.3rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="hero-title">Ligue 1 Analytics</div>', unsafe_allow_html=True)
st.markdown('<hr class="hero-accent">', unsafe_allow_html=True)

st.markdown(
    """
    <p class="hero-text">
    This is a personal project built to practice data analysis on a real dataset.
    I scraped data from multiple websites, went through a full data engineering
    pipeline (including plenty of error handling along the way), and built machine
    learning models to power parts of it. The site lets you visualize every Ligue 1
    match event by event and compare players against each other.
    </p>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="section-title">Player Dashboard</div>', unsafe_allow_html=True)
st.page_link("pages/1_Visualisations.py", label="Open Player Dashboard", use_container_width=True)

st.markdown('<div class="section-title">Player Comparison</div>', unsafe_allow_html=True)
st.page_link("pages/2_Comparatif_Joueurs.py", label="Open Player Comparison", use_container_width=True)

st.divider()
st.caption("Built with Python, pandas, scikit-learn, XGBoost, Supabase (PostgreSQL) and Streamlit.")