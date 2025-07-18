import streamlit as st
import sys
import os

# Add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from checklist_utils import get_all_positions
from chatbot_logic import get_full_chain

# --- Page Configuration and Authentication ---
st.set_page_config(page_title="Hiring Assistant", layout="wide")

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Please log in to view this page.")
    st.switch_page("app.py")
    st.stop()

st.title("AI Hiring Procedure Assistant")
current_user = st.session_state["current_user"]

# --- Initialize Session State ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "selected_position_id" not in st.session_state:
    st.session_state.selected_position_id = None

# --- Display existing chat messages ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Main Application Logic ---

# 1. Greet the user if this is the very first message.
if not st.session_state.messages:
    welcome_message = f"Welcome, {current_user['username']}! I'm here to help you with the hiring process."
    st.session_state.messages.append({"role": "assistant", "content": welcome_message})
    with st.chat_message("assistant"):
        st.markdown(welcome_message)

# 2. If no position has been selected yet, display the selection menu.
if st.session_state.selected_position_id is None:
    # DEBUG: Add debugging information
    st.write("DEBUG: Fetching positions...")
    positions = get_all_positions()
    st.write(f"DEBUG: Found {len(positions)} positions")
    st.write(f"DEBUG: Positions data: {positions}")
    
    if not positions:
        no_pos_message = "It looks like there are no active job positions right now."
        st.info(no_pos_message)
        # Add to history only if it's the second message
        if len(st.session_state.messages) == 1:
            st.session_state.messages.append({"role": "assistant", "content": no_pos_message})
    else:
        # Prompt the user to select a position
        prompt_message = "Please select a job position below to continue."
        st.info(prompt_message)
        if len(st.session_state.messages) == 1:
            st.session_state.messages.append({"role": "assistant", "content": prompt_message})

        position_options = {pos['position_id']: f"{pos['position_title']} (Kennziffer: {pos['kenziffer']})" for pos in positions}

        selected_id = st.selectbox(
            "Select a Job Position:",
            options=list(position_options.keys()),
            format_func=lambda x: position_options[x],
            index=None,
            placeholder="Choose a position...",
            key="position_selector"
        )

        # If the user makes a selection, save it and refresh the page.
        if selected_id:
            st.session_state.selected_position_id = selected_id
            confirmation_message = f"Great! We are now discussing {position_options[selected_id]}. How can I help you?"
            st.session_state.messages.append({"role": "assistant", "content": confirmation_message})
            st.rerun()

# 3. If a position IS selected, enable the chat input.
else:
    if user_input := st.chat_input("How can I assist you?"):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # Here you can add logic to check for "checklist" keywords
                # or just call the main LLM chain.
                full_chain = get_full_chain()
                response = full_chain.invoke({"question": user_input})
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

