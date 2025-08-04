import streamlit as st
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hr_utils import(
    get_active_positions,
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

# Get data
positions = get_active_positions()
statistics = get_position_statistics()
ba_groups = get_all_ba_groups()

# Enhanced summary metrics - now includes BA info
st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.metric(label= "Active Positions", value= len(positions), delta= None)

with col2:
    st.metric("Total BA Groups", len(ba_groups))
    
st.markdown("---")
st.subheader("Active Positions & BA Management")

if positions:
    for position in positions:
        # Convert position tuple to dict for easier access
        if isinstance(position, tuple):
            pos_dict = {
                'position_id': position[0], 
                'position_title': position[1],
                'department': position[2],
                'kenziffer': position[3],
                'position_status': position[4],
                'ba_id': position[5],
                'ba_name': position[6],
                'total_tasks': position[7] or 0,
                'completed_tasks': position[8] or 0
            }
        else:
            pos_dict = position
        
        # Calculate progress
        total = pos_dict.get('total_tasks', 0)
        completed = pos_dict.get('completed_tasks', 0)
        progress = (completed / total * 100) if total > 0 else 0
        
        with st.expander(f"**{pos_dict['position_title']}** ({pos_dict['kenziffer']}) - {progress:.1f}% complete"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Position Information")
                st.write(f"**Department:** {pos_dict['department']}")
                st.write(f"**Status:** {pos_dict['position_status']}")
                st.write(f"**Progress:** {completed}/{total} tasks completed")
                
                # Progress bar
                if total > 0:
                    st.progress(progress/100)
                else:
                    st.info("No tasks available yet")
                    
            with col2:
                st.markdown("#### BA Committee Information")
                
                if pos_dict.get('ba_id'):
                    st.write(f"**BA Group:** {pos_dict.get('ba_name', 'Unknown')}")
                    
                    # Show BA members
                    members = get_ba_members(pos_dict['ba_id'])
                    if members:
                        st.write("**Members:**")
                        # Show head first
                        head_members = [m for m in members if m.get('is_head')]
                        regular_members = [m for m in members if not m.get('is_head')]
                        
                        for member in head_members:
                            st.write(f"- {member['username']} ({member['email']}) - **HEAD**")
                        for member in regular_members:
                            st.write(f"- {member['username']} ({member['email']})")
                        
                        st.caption(f"Total: {len(members)} member{'s' if len(members) != 1 else ''}")
                    else:
                        st.warning("BA group exists but has no members")
                        
                else:
                    st.warning("No BA assigned yet")
                    st.write("This position needs a BA committee to proceed.")
                    
                    # Show available unassigned BAs
                    unassigned_bas = [ba for ba in ba_groups if ba.get('position_count', 0) == 0]
                    if unassigned_bas:
                        st.write("**Available BA Groups:**")
                        for ba in unassigned_bas[:2]:  # Show first 2 available
                            col_ba1, col_ba2 = st.columns([3, 1])
                            with col_ba1:
                                st.write(f"- {ba['ba_name']} ({ba.get('member_count', 0)} members)")
                            with col_ba2:
                                if st.button("Assign", key=f"assign_ba_{ba['ba_id']}_to_{pos_dict['position_id']}"):
                                    pass
                    
                    if st.button(f"Create New BA", key=f"create_ba_{pos_dict['position_id']}"):
                        pass
            
            # Action buttons row
            action_col1, action_col2, action_col3 = st.columns(3)
            
            with action_col1:
                if st.button(f"View Details", key=f"view_details_{pos_dict['position_id']}", use_container_width=True):
                    pass
            
            with action_col2:
                if st.button(f"Delete Position", key=f"delete_{pos_dict['position_id']}", use_container_width=True, type="secondary"):
                    pass
            
            with action_col3:
                if pos_dict.get('ba_id'):
                    if st.button(f"Contact BA Members", key=f"contact_{pos_dict['position_id']}", use_container_width=True):
                        pass
                else:
                    st.empty()  # Empty space when no BA is assigned

else:
    st.info("No active job positions found.")
    
    # Show unassigned BA groups when no positions exist
    if ba_groups:
        st.markdown("---")
        st.subheader("Available BA Groups")
        st.info("These BA groups are ready to be assigned to new positions.")
        
        unassigned_bas = [ba for ba in ba_groups if ba.get('position_count', 0) == 0]
        
        if unassigned_bas:
            for ba in unassigned_bas:
                with st.expander(f"**{ba['ba_name']}** - {ba.get('member_count', 0)} members"):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.write(f"**Created:** {ba['created_at'].strftime('%d.%m.%Y')}")
                        
                        # Show members
                        members = get_ba_members(ba['ba_id'])
                        if members:
                            st.write("**Members:**")
                            for member in members:
                                if member.get('is_head'):
                                    st.write(f"- {member['username']} ({member['email']}) - **HEAD**")
                                else:
                                    st.write(f"- {member['username']} ({member['email']})")
                        else:
                            st.write("*No members assigned yet*")
                    
                    with col2:
                        st.info("Available for assignment")
        else:
            st.success("All BA groups are currently assigned!")

with st.sidebar:
    st.header("HR Dashboard Guide")
    st.markdown("### Overview")
    st.info(""" This dashboard provides a comprehensive view of all hiring procedure and their progress. """)
    
    st.markdown("---")
    st.markdown("### Key Features")
    st.markdown("""
                **Metric Overview:**
                - Active position count
                BA assignment status
                Committee statistics
                
                **BA Management:**
                - View all BA committees
                - See member assignments
                - Identify committee heads
                - Track committee progress
                """)

    # Logout button
    if st.button("Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.current_user = None
        st.switch_page("app.py")