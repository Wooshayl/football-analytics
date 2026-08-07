import streamlit as st

st.title("Ligue 1 Analytics")

from utils.supabase_client import get_client

supabase = get_client()

response = supabase.table("football_team").select("*").execute()

st.write(f"Nombre d'équipes trouvées : {len(response.data)}")
st.dataframe(response.data)