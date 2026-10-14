import os
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Daily Data", page_icon="📊", layout="wide")

DATA_DIR = "data"
FILE_PATH = os.path.join(DATA_DIR, "latest.xlsx")
os.makedirs(DATA_DIR, exist_ok=True)


def get_secret(name, default):
    try:
        return st.secrets[name]
    except Exception:
        return default


ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", "admin123")
USER_PASSWORD = get_secret("USER_PASSWORD", "user123")

# ---------- Login ----------
if "role" not in st.session_state:
    st.session_state.role = None

if st.session_state.role is None:
    st.title("📊 Daily Data")
    pwd = st.text_input("Password likhein", type="password")
    if st.button("Login"):
        if pwd == ADMIN_PASSWORD:
            st.session_state.role = "admin"
            st.rerun()
        elif pwd == USER_PASSWORD:
            st.session_state.role = "user"
            st.rerun()
        else:
            st.error("Password ghalat hai")
    st.stop()

# ---------- Admin upload ----------
if st.session_state.role == "admin":
    st.sidebar.header("Admin: file upload")
    uploaded = st.sidebar.file_uploader("Aaj ki Excel file", type=["xlsx", "xls"])
    if uploaded is not None:
        with open(FILE_PATH, "wb") as f:
            f.write(uploaded.getbuffer())
        st.sidebar.success("File upload ho gayi. Purana data replace ho gaya.")

if st.sidebar.button("Logout"):
    st.session_state.role = None
    st.rerun()

# ---------- Show data ----------
st.title("📊 Daily Data")

if not os.path.exists(FILE_PATH):
    st.info("Abhi koi file upload nahi hui.")
    st.stop()

updated = datetime.fromtimestamp(os.path.getmtime(FILE_PATH))
st.caption(f"Akhri update: {updated.strftime('%d-%m-%Y %I:%M %p')}")


@st.cache_data
def load(path, mtime):
    return pd.read_excel(path, sheet_name=None)


sheets = load(FILE_PATH, os.path.getmtime(FILE_PATH))
names = list(sheets.keys())
sheet = st.selectbox("Sheet", names) if len(names) > 1 else names[0]
df = sheets[sheet]

query = st.text_input("🔍 Search")
if query:
    mask = df.astype(str).apply(
        lambda col: col.str.contains(query, case=False, na=False)
    ).any(axis=1)
    df = df[mask]

st.write(f"Total rows: {len(df)}")
st.dataframe(df, use_container_width=True, hide_index=True)
