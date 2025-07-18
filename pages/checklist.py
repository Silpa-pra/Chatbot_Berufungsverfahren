import streamlit as st
import sys
import os

# Add the root directory to the Python path to allow importing from utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from checklist_utils import get_full_procedure_data, get_all_positions, update_task_status

# --- Page Configuration and Authentication ---
st.set_page_config(page_title="Checklist", layout="wide")

if " not in st.session_state or not st.session_state.logged_in:
    st.warning("Please log in to view this page.")
    st.switch_page("app.py") # Redirect to login page
    st.stop()

st.title("Berufungsverfahren Checklist")

# --- Data Loading & Position Selection ---
current_user = st.session_state["current_user"]
positions = get_all_positions()

if not positions:
    st.warning("No job positions found in the database.")
    st.stop()

# Create a formatted list of positions for the selectbox
position_options = {pos['position_id']: f"{pos['position_title']} (Kennziffer: {pos['kenziffer']})" for pos in positions}
selected_position_id = st.selectbox(
    "Select a Job Position to view its checklist:",
    options=list(position_options.keys()),
    format_func=lambda x: position_options[x]
)

# --- Initialize or Reset the Phase Tracker ---
# If the selected position changes, reset the phase index back to 0
if 'current_pos_id' not in st.session_state or st.session_state.current_pos_id != selected_position_id:
    st.session_state.current_pos_id = selected_position_id
    st.session_state.current_phase_index = 0

# --- Helper function to check if all tasks in a phase are done ---
def is_phase_complete(phase):
    for step in phase['steps'].values():
        for task in step['tasks']:
            if task['task_status'] != 'completed':
                return False
    return True

# --- Main Display Logic ---
if selected_position_id:
    phases_data = get_full_procedure_data(selected_position_id, current_user['user_id'])

    if not phases_data:
        st.error("Could not load the checklist for this position.")
        st.stop()

    # Get an ordered list of phase IDs to navigate through them
    ordered_phase_ids = list(phases_data.keys())
    
    # Determine the current phase to display using the index from session_state
    current_phase_index = st.session_state.current_phase_index
    current_phase_id = ordered_phase_ids[current_phase_index]
    current_phase = phases_data[current_phase_id]

    # --- Display the SINGLE active phase ---
    phase_title = f"{current_phase['phase_code']}. {current_phase['phase_title']}"
    st.header(phase_title)
    
    if current_phase.get('phase_link'):
        st.markdown(f"ℹ️ [Link for this Phase]({current_phase['phase_link']})")

    # Display all steps and tasks for the current phase
    for step_id, step in current_phase['steps'].items():
        st.markdown(f"--- \n#### {step['step_code']}. {step['step_title']}")
        st.caption(f"Responsible: *{step['responsible']}*")
        
        if step.get('step_link'):
            st.markdown(f"ℹ️ [Link for this Step]({step['step_link']})")

        for task in step['tasks']:
            cols = st.columns([0.05, 0.65, 0.3])
            is_checked = task['task_status'] == 'completed'
            
            with cols[0]:
                # The checkbox will be for interactivity in the next step
                st.checkbox(" ", value=is_checked, key=f"task_{task['task_id']}")
            
            with cols[1]:
                st.markdown(f"<div style='margin-top: -5px;'>{task['task_description']}</div>", unsafe_allow_html=True)
                if task.get('task_link'):
                    st.markdown(f"↪ [Link for this task]({task['task_link']})")
            
            with cols[2]:
                # Visual status indicator
                if task['task_status'] == 'completed':
                    st.success("✅ Completed")
                elif task['task_status'] == 'in_progress':
                    st.info("▶️ In Progress")
                else:
                    st.warning("⚪ Not Started")

    st.markdown("---")
    
    # --- Navigation Logic ---
    phase_is_done = is_phase_complete(current_phase)
    is_last_phase = (current_phase_index == len(ordered_phase_ids) - 1)

    if is_last_phase and phase_is_done:
        st.success("🎉 Congratulations! All phases for this procedure are complete.")
    elif not is_last_phase:
        # The button is disabled until the phase is complete
        if st.button("Next Phase →", disabled=not phase_is_done, type="primary"):
            st.session_state.current_phase_index += 1
            st.rerun() # Refresh the page to show the next phase
    
    if not phase_is_done:
        st.info("ℹ️ Please complete all tasks in the current phase to proceed.")