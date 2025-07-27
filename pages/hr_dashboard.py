import streamlit as st
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hr_utils import(
    get_active_positions,
    get_current_phase_info,
    get_position_statistics,
    get_all_ba_groups,
    get_ba_members)

# page configuration
st.set_page_config(page_title = "HR Dashboard", layout = "wide")

# authentication check
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Please log in to access this page.")
    st.switch_page("app.py")
    st.stop()
    
# verify HR role
current_user = st.session_state["current_user"]
if current_user["user_type"] != "HR":
    st.error("Access Denied. This page is only accessible for HR users.")
    st.stop()
    
# ---Main Dashboard---
st.title("HR Dashboard for Berufungsverfahren Overview")

# Welcome message and other actions
col1, col2, col3 = st.columns([2,1,1])
with col1:
    st.markdown(f"WELCOME, {current_user['username']}!")
    st.markdown("Monitor all active job positions.")
  
with col2:
    if st.button("Create Position",type= "primary", use_container_width=True):
        st.switch_page("pages/create_job_position.py")
        
with col3:
    if st.button("Refresh", type = "secondary", use_container_width= True):
        st.rerun()
