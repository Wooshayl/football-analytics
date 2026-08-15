import streamlit as st
from pathlib import Path
import base64

st.set_page_config(page_title="Ligue 1 Analytics", layout="wide")

st.markdown(
    """
    <style>
    .hero-title {
        font-size: 3.6rem !important;
        font-weight: 800;
        margin: 0;
    }

    .hero-accent {
        height: 4px;
        width: 90px;
        background: linear-gradient(90deg, #00e5ff, #ff6b6b);
        border: none;
        margin: 0.6rem 0 1.8rem 0;
        border-radius: 2px;
    }

    .hero-text {
        font-size: 2rem !important;
        line-height: 1.6 !important;
    }

    .section-title {
        font-size: 2.2rem !important;
        font-weight: 700;
        margin-top: 2.4rem;
        margin-bottom: 0.3rem;
    }

    div.stButton > button {
        width: 100%;
        font-size: 1.3rem !important;
        font-weight: 700 !important;
        padding: 1.5rem 1rem !important;
        border-radius: 12px !important;
        background: #00e5ff !important;
        color: #0a0a0a !important;
        border: none !important;
    }

    div.stButton > button p {
        font-size: 1.3rem !important;
        font-weight: 700 !important;
        color: #0a0a0a !important;
    }

    div.stButton > button:hover {
        filter: brightness(1.1);
        transform: scale(1.01);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

col_text, col_img = st.columns([3, 1])

with col_text:

    logo_path = Path(__file__).parent / "assets" / "logo.png"

    with open(logo_path, "rb") as f:
        logo_base64 = base64.b64encode(f.read()).decode()

    st.markdown(
        f"""
        <div style="
            display:flex;
            justify-content:center;
            align-items:center;
            gap:15px;
            margin-bottom:5px;
        ">
            <div class="hero-title">Ligue 1 Analytics</div>
            <img src="data:image/png;base64,{logo_base64}" width="55">
        </div>
        """,
        unsafe_allow_html=True,
    )

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

with col_img:
    png_path = Path(__file__).parent / "assets" / "silhouette.png"
    st.image(str(png_path), width=240)

st.divider()

col_left, col_right = st.columns(2)

with col_left:
    if st.button(
        "Player Dashboard",
        use_container_width=True,
        key="btn_dashboard",
    ):
        st.switch_page("pages/1_Visualisations.py")

with col_right:
    if st.button(
        "Player Comparison",
        use_container_width=True,
        key="btn_comparison",
    ):
        st.switch_page("pages/2_Comparatif_Joueurs.py")

st.divider()

st.caption(
    "Built with Python, Supabase (PostgreSQL) and Streamlit."
)