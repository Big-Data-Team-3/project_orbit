import streamlit as st
import requests
import os

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="Project Orbit", layout="wide")
st.title("Project ORBIT – PE Dashboard for Forbes AI 50")

try:
    companies = requests.get(f"{API_BASE}/companies", timeout=5).json()
except Exception:
    companies = []

names = [c["company_name"] for c in companies] if companies else ["ExampleAI"]
choice = st.selectbox("Select company", names)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Structured pipeline")
    if st.button("Generate (Structured)"):
        resp = requests.post(f"{API_BASE}/dashboard/structured", json={"company_name": choice})
        st.markdown(resp.json()["dashboard"])

with col2:
    st.subheader("RAG pipeline")
    if st.button("Generate (RAG)"):
        resp = requests.post(f"{API_BASE}/dashboard/rag", json={"company_name": choice})
        st.markdown(resp.json()["dashboard"])
        