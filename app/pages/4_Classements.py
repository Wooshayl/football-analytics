import streamlit as st
from utils.supabase_client import get_client
import pandas as pd
import ast
st.set_page_config(layout="wide")

st.title("🏆 Classements")

supabase = get_client()

# Requête des buteurs, avec match_id cette fois
response = supabase.table("player_match_stats").select(
    "match_id, goals, players(player_name)"
).order("goals", desc=True).limit(10).execute()

df = pd.DataFrame(response.data)
df["player_name"] = df["players"].apply(lambda x: x["player_name"])

# Requête des matchs, avec l'id du match cette fois pour pouvoir joindre
response_matches = supabase.table("football_match").select(
    "game_id, home_team:home_team_id(team_name), away_team:away_team_id(team_name)"
).execute()

df_matches = pd.DataFrame(response_matches.data)
df_matches["home_team"] = df_matches["home_team"].apply(lambda x: x["team_name"])
df_matches["away_team"] = df_matches["away_team"].apply(lambda x: x["team_name"])
df_matches["match"] = df_matches["home_team"] + " - " + df_matches["away_team"]

# Jointure entre les deux DataFrames sur l'identifiant du match
df_final = df.merge(df_matches[["game_id", "match"]], left_on="match_id", right_on="game_id")

df_final.index = df_final.index + 1
st.dataframe(df_final[["player_name", "match", "goals"]])
