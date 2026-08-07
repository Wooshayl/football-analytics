from supabase import create_client
from dotenv import load_dotenv
import os
import streamlit as st

load_dotenv(dotenv_path="../.env")

@st.cache_resource
def get_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)