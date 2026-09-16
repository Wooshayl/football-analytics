import json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from utils.supabase_client import get_client


# ============================================================
# 1. PAGE CONFIG, CONSTANTS, COLOR PALETTE
# ============================================================

st.set_page_config(layout="wide")
st.title("Player Dashboard")

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
ASPECT_RATIO = PITCH_WIDTH_M / PITCH_LENGTH_M

PITCH_FIG_WIDTH = 800
PITCH_MARGIN = dict(l=10, r=10, t=10, b=10)
_plot_area_width = PITCH_FIG_WIDTH - PITCH_MARGIN["l"] - PITCH_MARGIN["r"]
_plot_area_height = _plot_area_width * ASPECT_RATIO
PITCH_FIG_HEIGHT = round(_plot_area_height + PITCH_MARGIN["t"] + PITCH_MARGIN["b"])

BUTTON_GROUPS = {
    "Passes": ["Passes"],
    "Attacking actions": ["Shots", "Dribbles"],
    "Defensive actions": ["Tackles", "Interceptions", "Clearances", "Recoveries", "Aerial duels"],
    "Other": ["Fouls", "Cards"],
}

EVENT_CATEGORIES = {
    "Passes":        {"types": ["Pass"], "draw": "line"},
    "Shots":         {"types": ["Goal", "SavedShot", "MissedShots", "ShotOnPost"], "draw": "shot"},
    "Dribbles":      {"types": ["TakeOn"], "draw": "point"},
    "Tackles":       {"types": ["Tackle"], "draw": "point"},
    "Interceptions": {"types": ["Interception"], "draw": "point"},
    "Clearances":    {"types": ["Clearance"], "draw": "point"},
    "Recoveries":    {"types": ["BallRecovery"], "draw": "point"},
    "Aerial duels":  {"types": ["Aerial"], "draw": "point"},
    "Fouls":         {"types": ["Foul"], "draw": "point"},
    "Cards":         {"types": ["Card"], "draw": "point"},
}

CATEGORY_COLOR = {
    "Passes": "#00e5ff",
    "Shots": "#ff9800",
    "Dribbles": "#ff80ab",
    "Tackles": "#69f0ae",
    "Interceptions": "#ffd740",
    "Clearances": "#40c4ff",
    "Recoveries": "#8bc34a",
    "Aerial duels": "#b388ff",
    "Fouls": "#ff6e40",
    "Cards": "#d500f9",
}

CATEGORY_PRIORITY = [
    "Passes", "Shots", "Tackles", "Dribbles",
    "Interceptions", "Aerial duels", "Clearances", "Recoveries",
    "Fouls", "Cards",
]

CATEGORY_SPLIT_COLUMN = {
    "Passes": "pass_subtype",
    "Shots": "type",
    "Dribbles": "outcome_type",
    "Tackles": "outcome_type",
    "Aerial duels": "outcome_type",
    "Interceptions": None,
    "Clearances": None,
    "Recoveries": None,
    "Fouls": None,
    "Cards": "card_type",
}

SUBTYPE_STYLES = {
    ("Passes", "Successful"):   {"label": "Successful passes", "color": "#00e5ff", "symbol": "circle"},
    ("Passes", "Unsuccessful"): {"label": "Unsuccessful passes", "color": "#ff5252", "symbol": "circle"},
    ("Passes", "Assist"):       {"label": "Assist", "color": "#ffd700", "symbol": "circle"},

    ("Shots", "Goal"):        {"label": "Goal", "color": "#ffd700", "symbol": "star"},
    ("Shots", "SavedShot"):   {"label": "Shot on target", "color": "#ff9800", "symbol": "diamond"},
    ("Shots", "MissedShots"): {"label": "Shot off target", "color": "#9e9e9e", "symbol": "circle-open"},
    ("Shots", "ShotOnPost"):  {"label": "Post", "color": "#795548", "symbol": "cross"},

    ("Dribbles", "Successful"):   {"label": "Successful dribbles", "color": "#ff80ab", "symbol": "circle"},
    ("Dribbles", "Unsuccessful"): {"label": "Unsuccessful dribbles", "color": "#880e4f", "symbol": "circle"},

    ("Tackles", "Successful"):   {"label": "Successful tackles", "color": "#69f0ae", "symbol": "circle"},
    ("Tackles", "Unsuccessful"): {"label": "Unsuccessful tackles", "color": "#1b5e20", "symbol": "circle"},

    ("Aerial duels", "Successful"):   {"label": "Aerial duels won", "color": "#b388ff", "symbol": "circle"},
    ("Aerial duels", "Unsuccessful"): {"label": "Aerial duels lost", "color": "#4a148c", "symbol": "circle"},

    ("Interceptions", "*"): {"label": "Interceptions", "color": "#ffd740", "symbol": "circle"},
    ("Clearances", "*"):    {"label": "Clearances", "color": "#40c4ff", "symbol": "circle"},
    ("Recoveries", "*"):    {"label": "Recoveries", "color": "#8bc34a", "symbol": "circle"},
    ("Fouls", "*"):         {"label": "Fouls committed", "color": "#ff6e40", "symbol": "circle"},

    ("Cards", "Yellow"):       {"label": "Yellow card", "color": "#ffeb3b", "symbol": "square"},
    ("Cards", "SecondYellow"): {"label": "Second yellow", "color": "#ff6f00", "symbol": "square"},
    ("Cards", "Red"):          {"label": "Red card", "color": "#f44336", "symbol": "square"},
}


# ============================================================
# 2. DATA CONNECTION AND FETCHING
# ============================================================

supabase = get_client()


@st.cache_data
def get_players() -> pd.DataFrame:
    resp = supabase.table("players").select("player_id, player_name, position").execute()
    return pd.DataFrame(resp.data)


@st.cache_data
def get_player_match_ids(player_id: int) -> list:
    resp = supabase.table("player_match_stats").select("match_id").eq("player_id", player_id).execute()
    return [row["match_id"] for row in resp.data]


@st.cache_data
def get_matches_info(match_ids: tuple) -> pd.DataFrame:
    resp = supabase.table("football_match").select(
        "game_id, home_team:home_team_id(team_name), away_team:away_team_id(team_name), matchday"
    ).in_("game_id", list(match_ids)).execute()
    return pd.DataFrame(resp.data)


@st.cache_data
def get_match_summary(player_id: int, match_id: int) -> dict:
    resp = supabase.table("player_match_stats").select(
        "minutes_played, goals, assists, yellow_cards, red_cards"
    ).eq("player_id", player_id).eq("match_id", match_id).execute()
    if not resp.data:
        return {}
    return resp.data[0]


@st.cache_data
def get_events(player_id: int, match_id: int, types: tuple) -> pd.DataFrame:
    if not types:
        return pd.DataFrame()
    resp = supabase.table("events").select(
        "event_pk, x, y, end_x, end_y, goal_mouth_y, outcome_type, type, minute, period, card_type, qualifiers"
    ).eq("player_id", player_id).eq("match_id", match_id).in_("type", list(types)).execute()
    return pd.DataFrame(resp.data)


# ============================================================
# 3. UTILITY FUNCTIONS
# ============================================================

def unwrap(df: pd.DataFrame, column: str, key: str) -> pd.Series:
    return df[column].apply(lambda x: x[key] if isinstance(x, dict) else None)


def is_assist(qualifiers_raw) -> bool:
    if not qualifiers_raw or pd.isna(qualifiers_raw):
        return False
    try:
        qualifiers = json.loads(qualifiers_raw) if isinstance(qualifiers_raw, str) else qualifiers_raw
    except (TypeError, ValueError):
        return False
    return any(q.get("type", {}).get("displayName") == "IntentionalGoalAssist" for q in qualifiers)


def build_match_label(df_matches: pd.DataFrame) -> pd.DataFrame:
    df_matches = df_matches.copy()
    df_matches["home_team"] = unwrap(df_matches, "home_team", "team_name")
    df_matches["away_team"] = unwrap(df_matches, "away_team", "team_name")
    df_matches["match_label"] = (
        df_matches["home_team"] + " - " + df_matches["away_team"]
        + " (MD" + df_matches["matchday"].astype(str) + ")"
    )
    return df_matches.sort_values("matchday")


def default_groups_for_position(position: str) -> list:
    if position in ("Defender", "Goalkeeper"):
        return ["Passes"]
    if position == "Forward":
        return ["Attacking actions"]
    return ["Passes", "Attacking actions"]


# ============================================================
# 4. PITCH CONSTRUCTION
# ============================================================

def build_pitch_base_figure() -> go.Figure:
    fig = go.Figure()

    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=100, line=dict(color="white", width=2))
    fig.add_shape(type="line", x0=50, y0=0, x1=50, y1=100, line=dict(color="white", width=1))
    fig.add_shape(type="circle", x0=41.3, y0=36.5, x1=58.7, y1=63.5, line=dict(color="white", width=1))
    fig.add_shape(type="rect", x0=0, y0=21.1, x1=17, y1=78.9, line=dict(color="white", width=1))
    fig.add_shape(type="rect", x0=83, y0=21.1, x1=100, y1=78.9, line=dict(color="white", width=1))
    fig.add_shape(type="rect", x0=0, y0=36.8, x1=5.8, y1=63.2, line=dict(color="white", width=1))
    fig.add_shape(type="rect", x0=94.2, y0=36.8, x1=100, y1=63.2, line=dict(color="white", width=1))

    fig.update_layout(
        autosize=False,
        width=PITCH_FIG_WIDTH,
        height=PITCH_FIG_HEIGHT,
        plot_bgcolor="#0d5c2e",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(range=[0, 100], showgrid=False, zeroline=False, visible=False, constrain="domain"),
        yaxis=dict(range=[0, 100], showgrid=False, zeroline=False, visible=False,
                    scaleanchor="x", scaleratio=ASPECT_RATIO, constrain="domain"),
        margin=PITCH_MARGIN,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


def _add_line_trace(fig: go.Figure, df: pd.DataFrame, style: dict) -> None:
    if df.empty:
        return
    x_coords, y_coords, sizes = [], [], []
    for _, row in df.iterrows():
        x_coords += [row["x"], row["end_x"], None]
        y_coords += [row["y"], row["end_y"], None]
        sizes += [0, 9, 0]

    fig.add_trace(go.Scatter(
        x=x_coords, y=y_coords,
        mode="lines+markers",
        line=dict(color=style["color"], width=2),
        marker=dict(size=sizes),
        name=style["label"],
    ))


def _add_point_trace(fig: go.Figure, df: pd.DataFrame, style: dict) -> None:
    if df.empty:
        return
    fig.add_trace(go.Scatter(
        x=df["x"], y=df["y"],
        mode="markers",
        marker=dict(size=11, color=style["color"], symbol=style["symbol"], line=dict(width=1, color="white")),
        name=style["label"],
    ))


def _add_shot_trace(fig: go.Figure, df: pd.DataFrame, style: dict) -> None:
    if df.empty:
        return

    x_line, y_line = [], []
    for _, row in df.iterrows():
        if pd.notna(row.get("goal_mouth_y")):
            x_line += [row["x"], 100, None]
            y_line += [row["y"], row["goal_mouth_y"], None]

    if x_line:
        fig.add_trace(go.Scatter(
            x=x_line, y=y_line,
            mode="lines",
            line=dict(color=style["color"], width=1.5, dash="dot"),
            legendgroup=style["label"],
            showlegend=False,
            hoverinfo="skip",
        ))

    fig.add_trace(go.Scatter(
        x=df["x"], y=df["y"],
        mode="markers",
        marker=dict(size=11, color=style["color"], symbol=style["symbol"], line=dict(width=1, color="white")),
        name=style["label"],
        legendgroup=style["label"],
    ))


_DRAW_FUNCTIONS = {
    "line": _add_line_trace,
    "point": _add_point_trace,
    "shot": _add_shot_trace,
}


def add_category_traces(fig: go.Figure, category: str, df_cat: pd.DataFrame) -> None:
    if df_cat.empty:
        return

    draw_mode = EVENT_CATEGORIES[category]["draw"]
    add_trace_fn = _DRAW_FUNCTIONS[draw_mode]
    split_col = CATEGORY_SPLIT_COLUMN.get(category)

    if split_col is None:
        style = SUBTYPE_STYLES[(category, "*")]
        add_trace_fn(fig, df_cat, style)
        return

    for value in df_cat[split_col].dropna().unique():
        style = SUBTYPE_STYLES.get((category, value))
        if style is None:
            continue
        subset = df_cat[df_cat[split_col] == value]
        add_trace_fn(fig, subset, style)


def build_full_pitch(events_by_category: dict) -> go.Figure:
    fig = build_pitch_base_figure()
    for category, df_cat in events_by_category.items():
        add_category_traces(fig, category, df_cat)
    return fig


# ============================================================
# 5. STATS CHARTS (FOR CAROUSEL SLIDES)
# ============================================================

def build_counts_bar_chart(events_by_category: dict) -> go.Figure:
    labels = [c for c in CATEGORY_PRIORITY if c in events_by_category]
    counts = [len(events_by_category[c]) for c in labels]
    colors = [CATEGORY_COLOR[c] for c in labels]

    fig = go.Figure(go.Bar(
        x=counts, y=labels, orientation="h",
        marker=dict(color=colors),
        text=counts, textposition="outside",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, visible=False),
        yaxis=dict(autorange="reversed"),
        height=max(300, 40 * len(labels)),
    )
    return fig


def build_per90_bar_chart(events_by_category: dict, minutes_played):
    if not minutes_played or minutes_played <= 0:
        return None

    labels = [c for c in CATEGORY_PRIORITY if c in events_by_category]
    counts = [len(events_by_category[c]) for c in labels]
    per90 = [count * 90 / minutes_played for count in counts]
    colors = [CATEGORY_COLOR[c] for c in labels]

    fig = go.Figure(go.Bar(
        x=per90, y=labels, orientation="h",
        marker=dict(color=colors),
        text=[f"{v:.1f}" for v in per90], textposition="outside",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, visible=False),
        yaxis=dict(autorange="reversed"),
        height=max(300, 40 * len(labels)),
    )
    return fig


def build_pass_donut(df_passes: pd.DataFrame):
    if df_passes.empty:
        return None
    counts = df_passes["outcome_type"].value_counts().reset_index()
    counts.columns = ["outcome_type", "count"]
    counts["label"] = counts["outcome_type"].map({"Successful": "Successful", "Unsuccessful": "Unsuccessful"})

    fig = px.pie(
        counts, names="label", values="count", hole=0.6,
        color="label", color_discrete_map={"Successful": "#00e5ff", "Unsuccessful": "#ff5252"},
    )
    fig.update_traces(textinfo="percent", textfont_size=14)
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
    )
    return fig


def build_shot_outcome_donut(df_shots: pd.DataFrame):
    if df_shots.empty:
        return None
    label_map = {"Goal": "Goal", "SavedShot": "On target", "MissedShots": "Off target", "ShotOnPost": "Post"}
    counts = df_shots["type"].map(label_map).value_counts().reset_index()
    counts.columns = ["label", "count"]

    fig = px.pie(
        counts, names="label", values="count", hole=0.6,
        color="label",
        color_discrete_map={"Goal": "#ffd700", "On target": "#ff9800", "Off target": "#9e9e9e", "Post": "#795548"},
    )
    fig.update_traces(textinfo="percent", textfont_size=14)
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
    )
    return fig


def build_half_comparison_chart(events_by_category: dict):
    rows = []
    for category, df_cat in events_by_category.items():
        if df_cat.empty or "period" not in df_cat.columns:
            continue
        for half_label, half_value in [("1st half", "FirstHalf"), ("2nd half", "SecondHalf")]:
            rows.append({
                "Category": category,
                "Half": half_label,
                "count": (df_cat["period"] == half_value).sum(),
            })

    if not rows:
        return None

    df_plot = pd.DataFrame(rows)
    fig = px.bar(
        df_plot, x="count", y="Category", color="Half", orientation="h", barmode="group",
        color_discrete_map={"1st half": "#546e7a", "2nd half": "#eceff1"},
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, title=None),
        yaxis=dict(title=None),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


# ============================================================
# 6. HOME-MADE CAROUSEL (buttons + dots, via session_state)
# ============================================================

def render_carousel(slides: list) -> None:
    state_key = "carousel_index"
    if state_key not in st.session_state:
        st.session_state[state_key] = 0

    st.session_state[state_key] %= len(slides)

    nav_prev, nav_title, nav_next = st.columns([1, 6, 1])
    with nav_prev:
        if st.button("◀", use_container_width=True, key="carousel_prev"):
            st.session_state[state_key] = (st.session_state[state_key] - 1) % len(slides)
    with nav_next:
        if st.button("▶", use_container_width=True, key="carousel_next"):
            st.session_state[state_key] = (st.session_state[state_key] + 1) % len(slides)

    current_index = st.session_state[state_key]
    title, render_fn = slides[current_index]

    with nav_title:
        st.markdown(f"<h4 style='text-align:center;'>{title}</h4>", unsafe_allow_html=True)

    dots = "".join("●" if i == current_index else "○" for i in range(len(slides)))
    st.markdown(f"<p style='text-align:center; letter-spacing:6px;'>{dots}</p>", unsafe_allow_html=True)

    render_fn()


# ============================================================
# 7. PLAYER AND MATCH SELECTION
# ============================================================

col_select1, col_select2 = st.columns(2)

with col_select1:
    df_players = get_players()
    player_choice = st.selectbox("Select a player", df_players["player_name"].sort_values())
    player_row = df_players[df_players["player_name"] == player_choice].iloc[0]
    player_id = int(player_row["player_id"])
    player_position = player_row["position"] if pd.notna(player_row["position"]) else "Unknown position"

match_ids = get_player_match_ids(player_id)
df_matches_info = build_match_label(get_matches_info(tuple(match_ids)))

with col_select2:
    match_choice_label = st.selectbox("Select a match", df_matches_info["match_label"])
match_choice = int(df_matches_info[df_matches_info["match_label"] == match_choice_label]["game_id"].iloc[0])

POSITION_COLORS = {"Goalkeeper": "orange", "Defender": "blue", "Midfielder": "green", "Forward": "red"}

header_left, header_right = st.columns([2, 3])
with header_left:
    st.subheader(player_choice)
    st.badge(player_position, color=POSITION_COLORS.get(player_position, "gray"))

match_summary = get_match_summary(player_id, match_choice)
with header_right:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Minutes played", match_summary.get("minutes_played", "-"))
    m2.metric("Goals", match_summary.get("goals", 0))
    m3.metric("Assists", match_summary.get("assists", 0))
    total_cards = (match_summary.get("yellow_cards") or 0) + (match_summary.get("red_cards") or 0)
    m4.metric("Cards", total_cards)

st.divider()


# ============================================================
# 8. EVENT FILTERS (4 GROUPED BUTTONS) — ABOVE THE PITCH
# ============================================================

col_pitch, col_stats = st.columns([2, 1])

with col_pitch:
    selected_groups = st.pills(
        "Stats to display on the pitch",
        options=list(BUTTON_GROUPS.keys()),
        selection_mode="multi",
        default=default_groups_for_position(player_position),
        key=f"group_pills_{player_id}",
    )

selected_categories = []
for group in selected_groups:
    selected_categories.extend(BUTTON_GROUPS[group])


# ============================================================
# 9. FETCHING EVENTS FOR EACH ACTIVE CATEGORY
# ============================================================

events_by_category = {}
for category in selected_categories:
    config = EVENT_CATEGORIES[category]
    df_cat = get_events(player_id, match_choice, tuple(config["types"]))

    if category == "Passes" and not df_cat.empty:
        df_cat["pass_subtype"] = df_cat.apply(
            lambda row: "Assist" if is_assist(row["qualifiers"]) else row["outcome_type"],
            axis=1,
        )

    if category == "Fouls" and not df_cat.empty:
        df_cat = df_cat[df_cat["outcome_type"] == "Unsuccessful"]

    events_by_category[category] = df_cat

all_events_by_category = {}
for category in CATEGORY_PRIORITY:
    config = EVENT_CATEGORIES[category]
    if category in events_by_category:
        df_all_cat = events_by_category[category]
    else:
        df_all_cat = get_events(player_id, match_choice, tuple(config["types"]))
        if category == "Fouls" and not df_all_cat.empty:
            df_all_cat = df_all_cat[df_all_cat["outcome_type"] == "Unsuccessful"]
    all_events_by_category[category] = df_all_cat


# ============================================================
# 10. DISPLAY: PITCH (ALWAYS VISIBLE) + STATS CAROUSEL
# ============================================================

with col_pitch:
    fig_pitch = build_full_pitch(events_by_category)
    st.plotly_chart(
        fig_pitch,
        width=PITCH_FIG_WIDTH,
        height=PITCH_FIG_HEIGHT,
        config={"responsive": False, "displayModeBar": False},
        key=f"pitch_{player_id}_{match_choice}_{'-'.join(selected_groups)}",
    )

with col_stats:
    if not selected_categories:
        st.info("Select at least one stat above to see the details.")
    else:
        total_events = sum(len(df) for df in events_by_category.values())
        st.metric("Events displayed", total_events)

        def render_overview():
            st.plotly_chart(
                build_counts_bar_chart(all_events_by_category),
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"bar_overview_{player_id}_{match_choice}",
            )

        def render_per90():
            minutes = match_summary.get("minutes_played")
            chart = build_per90_bar_chart(all_events_by_category, minutes)
            if chart is not None:
                st.plotly_chart(
                    chart,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"bar_per90_{player_id}_{match_choice}",
                )
            else:
                st.info("Minutes played not available for this match.")

        def render_halves():
            chart = build_half_comparison_chart(events_by_category)
            if chart is not None:
                st.plotly_chart(
                    chart,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"bar_halves_{player_id}_{match_choice}",
                )
            else:
                st.info("Not enough data to compare the two halves.")

        slides = [
            ("Overview", render_overview),
            ("Per 90 minutes", render_per90),
            ("By half", render_halves),
        ]

        if "Passes" in events_by_category and not events_by_category["Passes"].empty:
            def render_pass_donut():
                st.plotly_chart(
                    build_pass_donut(events_by_category["Passes"]),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"donut_pass_{player_id}_{match_choice}",
                )
            slides.append(("Pass accuracy", render_pass_donut))

        if "Shots" in events_by_category and not events_by_category["Shots"].empty:
            def render_shot_donut():
                st.plotly_chart(
                    build_shot_outcome_donut(events_by_category["Shots"]),
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"donut_shots_{player_id}_{match_choice}",
                )
            slides.append(("Shot outcome", render_shot_donut))

        render_carousel(slides)