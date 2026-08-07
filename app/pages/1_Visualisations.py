import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.supabase_client import get_client

st.title("📊 Visualisations - Pass Map")

# ----------------------------------------------------------------------
# Le "plein écran" qui casse tout n'est pas celui de Plotly (la petite
# barre d'icônes camera/zoom/pan) : c'est le bouton natif que Streamlit
# rajoute lui-même au survol de CHAQUE graphique (icône "agrandir" en
# haut à droite). C'est un bug Streamlit connu et non résolu depuis des
# années (cf. issues GitHub #1154 et #5644) : au retour du plein écran,
# le conteneur du graphique reste coincé à une taille minuscule.
# Comme tu t'en fiches de pouvoir zoomer/agrandir, la solution la plus
# fiable est de supprimer ce bouton pour qu'il ne puisse plus jamais
# être déclenché. Ce CSS masque le "toolbar" qui apparaît au survol de
# tous les éléments de la page (graphiques, images, dataframes...).
st.markdown(
    """
    <style>
    [data-testid="stElementToolbar"] { display: none !important; }
    [data-testid="StyledFullScreenButton"] { display: none !important; }
    button[title="View fullscreen"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

supabase = get_client()

# --- Sélection du joueur ---
players_resp = supabase.table("players").select("player_id, player_name").execute()
df_players = pd.DataFrame(players_resp.data)

player_choice = st.selectbox("Choisis un joueur", df_players["player_name"].sort_values())
player_id = df_players[df_players["player_name"] == player_choice]["player_id"].iloc[0]

# --- Récupération des matchs de ce joueur ---
matches_resp = supabase.table("player_match_stats").select("match_id").eq("player_id", int(player_id)).execute()
match_ids = [row["match_id"] for row in matches_resp.data]

# --- Récupération des infos (équipes + journée) pour ces matchs précis ---
match_info_resp = supabase.table("football_match").select(
    "game_id, home_team:home_team_id(team_name), away_team:away_team_id(team_name), matchday"
).in_("game_id", match_ids).execute()

df_matches_info = pd.DataFrame(match_info_resp.data)
df_matches_info["home_team"] = df_matches_info["home_team"].apply(lambda x: x["team_name"])
df_matches_info["away_team"] = df_matches_info["away_team"].apply(lambda x: x["team_name"])
df_matches_info["match_label"] = (
    df_matches_info["home_team"] + " - " + df_matches_info["away_team"]
    + " (J" + df_matches_info["matchday"].astype(str) + ")"
)

# --- Le selectbox affiche le texte lisible, mais on garde le vrai game_id derrière ---
match_choice_label = st.selectbox("Choisis un match", df_matches_info["match_label"])
match_choice = df_matches_info[df_matches_info["match_label"] == match_choice_label]["game_id"].iloc[0]

# --- Récupération des passes de ce joueur, sur ce match ---
events_resp = supabase.table("events").select(
    "x, y, end_x, end_y, outcome_type"
).eq("player_id", int(player_id)).eq("match_id", int(match_choice)).eq("type", "Pass").execute()

df_passes = pd.DataFrame(events_resp.data)

if df_passes.empty:
    st.warning("Aucune passe trouvée pour ce joueur sur ce match.")
else:
    # ------------------------------------------------------------------
    # 1) Proportions réelles du terrain (105 m x 68 m), calculées une
    #    fois pour toutes. C'est cette valeur qui remplace le "0.65"
    #    choisi à l'oeil dans la version précédente.
    # ------------------------------------------------------------------
    PITCH_LENGTH_M = 105.0
    PITCH_WIDTH_M = 68.0
    ASPECT_RATIO = PITCH_WIDTH_M / PITCH_LENGTH_M  # ≈ 0.6476

    # ------------------------------------------------------------------
    # 2) Taille de la figure FIXÉE des deux côtés (largeur ET hauteur),
    #    calculée pour que la zone de tracé colle exactement au ratio
    #    ci-dessus. C'est le point clé qui corrige le bug de
    #    rétrécissement : Plotly n'a plus jamais besoin de "deviner"
    #    une hauteur à partir du conteneur, donc il n'y a plus rien
    #    à recalculer (et donc à casser) au plein écran ou au resize.
    # ------------------------------------------------------------------
    FIG_WIDTH = 900
    MARGIN = dict(l=10, r=10, t=10, b=10)
    plot_area_width = FIG_WIDTH - MARGIN["l"] - MARGIN["r"]
    plot_area_height = plot_area_width * ASPECT_RATIO
    FIG_HEIGHT = round(plot_area_height + MARGIN["t"] + MARGIN["b"])

    fig = go.Figure()

    # Contour du terrain
    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=100, line=dict(color="white", width=2))

    # Ligne médiane
    fig.add_shape(type="line", x0=50, y0=0, x1=50, y1=100, line=dict(color="white", width=1))

    # Rond central — coordonnées corrigées.
    # Avant : x0=41,y0=32,x1=59,y1=68 (rayon 9 en x, 18 en y) : une fois
    # le ratio 0.6476 appliqué à l'axe y, ça donnait une ellipse, pas un
    # cercle. Un vrai rond central fait 9,15 m de rayon ; converti dans
    # le repère 0-100 (x sur 105 m, y sur 68 m), ça donne un rayon
    # d'environ 8,7 unités en x et 13,5 unités en y.
    fig.add_shape(type="circle", x0=41.3, y0=36.5, x1=58.7, y1=63.5, line=dict(color="white", width=1))

    # Surface de réparation gauche
    fig.add_shape(type="rect", x0=0, y0=21.1, x1=17, y1=78.9, line=dict(color="white", width=1))

    # Surface de réparation droite
    fig.add_shape(type="rect", x0=83, y0=21.1, x1=100, y1=78.9, line=dict(color="white", width=1))

    # Petite surface (6 yards) gauche
    fig.add_shape(type="rect", x0=0, y0=36.8, x1=5.8, y1=63.2, line=dict(color="white", width=1))

    # Petite surface (6 yards) droite
    fig.add_shape(type="rect", x0=94.2, y0=36.8, x1=100, y1=63.2, line=dict(color="white", width=1))

    # Traces des passes — une trace par catégorie = légende cliquable native
    for outcome, couleur, label in [("Successful", "cyan", "Réussie"), ("Unsuccessful", "red", "Ratée")]:
        subset = df_passes[df_passes["outcome_type"] == outcome]
        if subset.empty:
            continue

        x_coords = []
        y_coords = []
        for _, row in subset.iterrows():
            x_coords += [row["x"], row["end_x"], None]
            y_coords += [row["y"], row["end_y"], None]

        fig.add_trace(go.Scatter(
            x=x_coords, y=y_coords,
            mode="lines+markers",
            line=dict(color=couleur, width=1.5),
            marker=dict(size=4),
            name=label
        ))

    fig.update_layout(
        # autosize=False : Plotly ne doit JAMAIS recalculer width/height
        # tout seul à partir de la taille du conteneur. C'est la cause
        # racine du rétrécissement au plein écran/resize : avec
        # autosize=True (ou implicite) + scaleanchor, chaque événement
        # de resize redéclenche un calcul qui peut se dégrader et finir
        # par donner une figure minuscule.
        autosize=False,
        width=FIG_WIDTH,
        height=FIG_HEIGHT,

        plot_bgcolor="#1a6b1a",
        paper_bgcolor="white",

        xaxis=dict(
            range=[0, 100], showgrid=False, zeroline=False, visible=False,
            # constrain="domain" : si jamais range et domain ne
            # correspondent pas exactement (ex: petit écart d'arrondi),
            # Plotly réduit la ZONE affichée plutôt que de laisser de
            # l'espace vide coloré autour du terrain.
            constrain="domain",
        ),
        yaxis=dict(
            range=[0, 100], showgrid=False, zeroline=False, visible=False,
            scaleanchor="x", scaleratio=ASPECT_RATIO,
            constrain="domain",
        ),

        margin=MARGIN,
        showlegend=True,
    )

    st.plotly_chart(
        fig,
        # width/height en entier (pixels) : depuis les versions récentes
        # de Streamlit, ce sont ces paramètres qui remplacent
        # use_container_width (déprécié). Un entier = taille FIXE du
        # composant Streamlit lui-même, indépendante de la largeur du
        # conteneur/de la fenêtre. Comme la figure interne a exactement
        # la même taille, il n'y a plus aucun recalcul à faire nulle
        # part : c'est ce qui garantit une taille stable au chargement,
        # après plein écran, après resize, et après changement de
        # sélection.
        width=FIG_WIDTH,
        height=FIG_HEIGHT,
        # config responsive=False : empêche explicitement Plotly.js
        # d'attacher un listener de resize de fenêtre au graphique
        # (redimensionnement de la fenêtre du navigateur, rerun suite à
        # un changement de sélection, etc.).
        # displayModeBar=False : supprime la barre d'icônes de Plotly
        # (zoom, pan, export PNG...). Tu as dit ne pas en avoir besoin,
        # et ça évite qu'elle chevauche la légende.
        config={"responsive": False, "displayModeBar": False},
        # key unique par joueur/match : force Streamlit à recréer le
        # composant graphique proprement à chaque changement de
        # sélection, plutôt que d'essayer de réutiliser/patcher l'état
        # (taille comprise) du graphique précédent.
        key=f"pass_map_{player_id}_{match_choice}",
    )