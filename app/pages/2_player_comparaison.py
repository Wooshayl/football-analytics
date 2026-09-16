import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity
from utils.supabase_client import get_client


# ============================================================
# 1. PAGE CONFIG, CONSTANTS
# ============================================================

st.set_page_config(layout="wide")
st.title("Player Comparison")

POSITION_COLORS = {"Goalkeeper": "orange", "Defender": "blue", "Midfield": "green", "Attack": "red"}

STATS_TO_COMPARE = [
    ("Goals", "goals"),
    ("Assists", "assists"),
    ("Total xG", "total_xg"),
    ("Total xA", "total_xa"),
    ("Total shots", "total_shots"),
    ("Shots on target", "shots_on_target"),
    ("Key passes", "key_passes"),
    ("Successful passes", "successful_passes"),
    ("Crosses", "crosses"),
    ("Fouls committed", "fouls_committed"),
    ("Yellow cards", "yellow_cards"),
    ("Red cards", "red_cards"),
]

# For these specific stats, a LOWER value is the better one (fewer fouls/cards
# is good, not bad) -- everything else defaults to "higher is better".
LOWER_IS_BETTER = {"Fouls committed", "Yellow cards", "Red cards"}

WIN_COLOR = "#2ecc71"
LOSE_COLOR = "#e74c3c"
TIE_COLOR = "#95a5a6"

SIMILARITY_FEATURES = [
    "goals", "assists", "total_xg", "total_xa", "key_passes",
    "successful_passes", "total_shots", "shots_on_target", "crosses", "fouls_committed",
]


# ============================================================
# 2. DATA CONNECTION AND FETCHING
# ============================================================

supabase = get_client()


@st.cache_data
def get_players() -> pd.DataFrame:
    resp = supabase.table("players").select("player_id, player_name, position").execute()
    return pd.DataFrame(resp.data)


@st.cache_data
def get_season_stats(player_id: int) -> dict:
    resp = supabase.table("player_season_stats").select("*").eq("player_id", player_id).execute()
    if not resp.data:
        return {}
    return resp.data[0]


@st.cache_data
def get_all_season_stats() -> pd.DataFrame:
    resp = supabase.table("player_season_stats").select("*").execute()
    df = pd.DataFrame(resp.data)
    for stat in SIMILARITY_FEATURES:
        df[f"{stat}_p90"] = df[stat] * 90 / df["total_minutes"].replace(0, pd.NA)
    p90_cols = [f"{s}_p90" for s in SIMILARITY_FEATURES]
    df[p90_cols] = df[p90_cols].fillna(0)
    return df


def compute_similarity(player_id_a: int, player_id_b: int):
    df = get_all_season_stats()
    p90_cols = [f"{s}_p90" for s in SIMILARITY_FEATURES]

    if player_id_a not in df["player_id"].values or player_id_b not in df["player_id"].values:
        return None

    X = StandardScaler().fit_transform(df[p90_cols])
    idx_a = df.index[df["player_id"] == player_id_a][0]
    idx_b = df.index[df["player_id"] == player_id_b][0]

    cosine_sim = cosine_similarity([X[idx_a]], [X[idx_b]])[0][0]
    return (cosine_sim + 1) / 2 * 100


# ============================================================
# 3. PLAYER SELECTION
# ============================================================

df_players = get_players()
names = df_players["player_name"].sort_values().tolist()

col_select_left, col_select_right = st.columns(2)
with col_select_left:
    player_a_name = st.selectbox("Player A", names, index=0, key="player_a")
with col_select_right:
    default_b = 1 if len(names) > 1 else 0
    player_b_name = st.selectbox("Player B", names, index=default_b, key="player_b")

player_a_row = df_players[df_players["player_name"] == player_a_name].iloc[0]
player_b_row = df_players[df_players["player_name"] == player_b_name].iloc[0]

position_a = player_a_row["position"] if pd.notna(player_a_row["position"]) else "Unknown position"
position_b = player_b_row["position"] if pd.notna(player_b_row["position"]) else "Unknown position"

stats_a = get_season_stats(int(player_a_row["player_id"]))
stats_b = get_season_stats(int(player_b_row["player_id"]))

col_head_left, col_head_right = st.columns(2)
with col_head_left:
    st.subheader(player_a_name)
    st.badge(position_a, color=POSITION_COLORS.get(position_a, "gray"))
with col_head_right:
    st.subheader(player_b_name)
    st.badge(position_b, color=POSITION_COLORS.get(position_b, "gray"))

st.divider()

similarity_pct = compute_similarity(int(player_a_row["player_id"]), int(player_b_row["player_id"]))
if similarity_pct is not None:
    st.markdown(
        f"<p style='text-align:center; font-size:2rem; font-weight:700;'>"
        f"Playing style similarity: {similarity_pct:.0f}%</p>",
        unsafe_allow_html=True,
    )

st.divider()


def render_minutes_block(minutes: float) -> None:
    matches_equivalent = minutes / 90
    st.markdown(
        f"<div style='text-align:center;'>"
        f"<span style='font-size:2.6rem; font-weight:700;'>{minutes:.0f}′</span><br>"
        f"<span style='color:gray;'>≈ {matches_equivalent:.1f} matches (90′ each)</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


minutes_left, minutes_right = st.columns(2)
minutes_a = (stats_a.get("total_minutes", 0) or 0) if stats_a else 0
minutes_b = (stats_b.get("total_minutes", 0) or 0) if stats_b else 0
with minutes_left:
    render_minutes_block(minutes_a)
with minutes_right:
    render_minutes_block(minutes_b)

st.divider()


# ============================================================
# 4. MAIN COMPARISON
# ============================================================

if not stats_a or not stats_b:
    st.warning("Season stats are not available for one of these players.")
else:
    # --- Over / underperformance vs xG and xA ---
    st.subheader("Goals vs xG, Assists vs xA")

    perf_left, perf_right = st.columns(2)
    for col, name, stats in [(perf_left, player_a_name, stats_a), (perf_right, player_b_name, stats_b)]:
        with col:
            st.markdown(f"**{name}**")
            goals, xg = stats.get("goals", 0) or 0, stats.get("total_xg", 0) or 0
            assists, xa = stats.get("assists", 0) or 0, stats.get("total_xa", 0) or 0
            st.metric("Goals vs xG", f"{goals} / {xg:.1f}", delta=f"{goals - xg:+.1f}")
            st.metric("Assists vs xA", f"{assists} / {xa:.1f}", delta=f"{assists - xa:+.1f}")

    st.caption(
        "Positive delta = scoring/assisting more than the underlying chance quality would predict "
        "(overperforming). Negative = underperforming relative to xG/xA."
    )

    st.divider()

    # --- Diverging bar chart: one row per stat, per 90 minutes, bar toward whoever leads ---
    st.subheader("Head-to-head (per 90 minutes)")
    st.caption("Green = leads on this stat · Red = trails · Bar length shows the gap")

    def per90(value, minutes):
        value = value or 0
        if not minutes:
            return 0.0
        return value * 90 / minutes

    def stat_winner(va, vb, label):
        """Returns 'a', 'b', or None (tie), accounting for lower-is-better stats."""
        if va == vb:
            return None
        higher_wins = va > vb
        if label in LOWER_IS_BETTER:
            higher_wins = not higher_wins
        return "a" if higher_wins else "b"

    labels, norm_a, norm_b, raw_a, raw_b = [], [], [], [], []
    colors_a, colors_b, winners = [], [], []

    for label, key in STATS_TO_COMPARE:
        va = per90(stats_a.get(key, 0), minutes_a)
        vb = per90(stats_b.get(key, 0), minutes_b)
        max_val = max(va, vb, 0.01)
        labels.append(label)
        norm_a.append(-va / max_val)
        norm_b.append(vb / max_val)
        raw_a.append(va)
        raw_b.append(vb)

        winner = stat_winner(va, vb, label)
        winners.append(winner)
        if winner is None:
            colors_a.append(TIE_COLOR)
            colors_b.append(TIE_COLOR)
        elif winner == "a":
            colors_a.append(WIN_COLOR)
            colors_b.append(LOSE_COLOR)
        else:
            colors_a.append(LOSE_COLOR)
            colors_b.append(WIN_COLOR)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=norm_a, orientation="h",
        marker=dict(color=colors_a),
        text=[f"{v:.2f}" for v in raw_a], textposition="outside",
        showlegend=False,
        hovertemplate=f"{player_a_name}: %{{text}}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=labels, x=norm_b, orientation="h",
        marker=dict(color=colors_b),
        text=[f"{v:.2f}" for v in raw_b], textposition="outside",
        showlegend=False,
        hovertemplate=f"{player_b_name}: %{{text}}<extra></extra>",
    ))
    fig.update_layout(
        barmode="overlay",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False, range=[-1.5, 1.5]),
        yaxis=dict(autorange="reversed"),
        height=42 * len(labels) + 60,
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    a_wins = winners.count("a")
    b_wins = winners.count("b")
    ties = winners.count(None)

    st.markdown(
        f"<p style='text-align:center; font-size:1.4rem; font-weight:700;'>"
        f"{player_a_name} leads on {a_wins} stats &nbsp;·&nbsp; "
        f"{player_b_name} leads on {b_wins} stats"
        f"{f' &nbsp;·&nbsp; {ties} tied' if ties else ''}"
        f"</p>",
        unsafe_allow_html=True,
    )