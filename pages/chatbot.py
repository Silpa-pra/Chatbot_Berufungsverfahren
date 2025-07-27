import streamlit as st
import sys
import os

# Add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from checklist_utils import( 
    get_all_positions,
    get_full_procedure_data,
    analyze_user_progress,
    update_task_status,
    create_chat_session, 
    save_chat_message,
    get_chat_history,
    generate_chatbot_response,
    detect_status_question,
    detect_task_help_request
    )
from chatbot_logic import get_full_chain, get_task_simplification_chain

# --- Page Configuration and Authentication ---
st.set_page_config(page_title="Hiring Assistant", layout="wide")

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Please log in to view this page.")
    st.switch_page("app.py")
    st.stop()

# --- Main App Header---
st.title("AI Hiring Procedure Assistant")
current_user = st.session_state["current_user"]

# --- Initialize Session State ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "selected_position_id" not in st.session_state:
    st.session_state.selected_position_id = None
if "current_status_data" not in st.session_state:
    st.session_state.current_status_data = None
if "chat_session_id" not in st.session_state:
    st.session_state.chat_session_id = None
    

# --- position selection section ---
st.subheader("Select Job Position")

positions = get_all_positions(current_user['user_id'], current_user['user_type'])

if not positions:
    st.error("""
    No job positions assigned to you yet.
    
    Please contact HR to be added to a BA (Berufungsausschuss) committee for a position.
    """)
    # Disable chat input when no positions
    st.chat_input("No positions available...", disabled=True)
    st.stop()

# Display BA membership info
unique_bas = {}
for pos in positions:
    if pos['ba_name'] not in unique_bas:
        unique_bas[pos['ba_name']] = pos['is_head']

# Show user's BA memberships
with st.expander(" Your BA Memberships", expanded=False):
    for ba_name, is_head in unique_bas.items():
        if is_head:
            st.write(f"• **{ba_name}** - You are the **HEAD** ")
        else:
            st.write(f"• **{ba_name}** - Member")
            
position_options ={}
for pos in positions:
    display_text = f"{pos['position_title']}({pos['kenziffer']})"
    if pos['is_head']:
        display_text +=  "HEAD"
    position_options[pos['position_id']]={
        'display': display_text,
        'data': pos
    }
    
selected_position_id = st.selectbox(
    "Choose the position you want to work on:",
    options=[None] + list(position_options.keys()),
    format_func=lambda x: "-- Select a position --" if x is None else position_options[x]['display'],
    key="position_selector"
)

# Show position details when selected
if selected_position_id and selected_position_id in position_options:
    pos_data = position_options[selected_position_id]['data']
    col1,col2, col3 = st.columns(3)
    with col1:
        st.info(f"Department: {pos_data['department']}")
    with col2:
        st.info(f"BA Committee:{pos_data['ba_name']}")
    with col3:
        role = "BA Head" if pos_data['is_head'] else "BA Member"
        st.info(f"**Your role:** {role}")


# --- Handle position selection ---
if selected_position_id !=  st.session_state.selected_position_id:
    st.session_state.selected_position_id = selected_position_id
    st.session_state.messages = []
    st.session_state.current_status_data = None
    st.session_state.chat_session_id = None
    
    # load checklist immediately when positionis selected
    if selected_position_id:
        st.session_state.current_status_data = get_full_procedure_data(
            current_user['user_id'], 
            selected_position_id
            )
            
# ---Initialize chat session when position is selected---
if selected_position_id and not st.session_state.chat_session_id:
    # create new chat session
    st.session_state.chat_session_id = create_chat_session(
        current_user['user_id'],
        selected_position_id
        ) 
    
    # load previous chat history
    chat_history = get_chat_history(
        current_user['user_id'],
        selected_position_id,
        limit=20 # loads only last 20 message
        )
    
    # convert history to session state format
    if chat_history:
        st.session_state.messages = [
            {
                "role": "user" if msg['sender_type']== 'user' else "assistant",
                "content": msg['message_text']
            }
            for msg in reversed(chat_history)
        ]
        

# --- Main Application Logic ---
#TODO : BA and HR different UI after login- BV to chatbot, HR to dashboard
# If no position has been selected yet, display the selection menu.
if st.session_state.selected_position_id is None:
    st.info("Please select a job position above to get started.")
    #Disable chat input when no position is selected
    st.chat_input("Select a position first..", disabled=True)
else:
    current_position_name = position_options[selected_position_id]['display']
    st.success(f"Working on: {current_position_name}")
    
    # Create 2 column: chat on left, checklist on right
    col1, col2 = st.columns([1,1])
    
    #--- left column: Chat Interface---
    with col1:
        st.subheader("Chat with Chatbot")
        
        # create a container for chat messages
        chat_container = st.container()
        
        # display chat history inside the container
        with chat_container:
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
        
        #Handle new user input 
        if user_input := st.chat_input("Ask me about your progress or any procedure question..."):
            
            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": user_input})
            
            # save user message to database
            save_chat_message(
                st.session_state.chat_session_id, 
                "user",
                user_input
                )
            
            #display user message
            with st.chat_message("user"):
                st.markdown(user_input)
                
            # Generate bot response
            with st.chat_message("assistant"):
                with st.spinner("Let me check that for you..."):
                    
                    #check if user is asking for task help / simplification
                    is_task_help_request = detect_task_help_request(user_input)
                    
                    # check if user is asking aabout status/progress
                    is_status_question = detect_status_question(user_input)
                    
                    # Handle task simplification requests using current task data.
                    if is_task_help_request and st.session_state.current_status_data:                        
                        current_step = st.session_state.current_status_data['current_step']
                        
                        if current_step and current_step['tasks']:
                            # find first incomplete task
                            current_task = None
                            for task in current_step['tasks']:
                                if task['task_status'] != 'completed':
                                    current_task = task
                                    break
                            
                            if not current_task:
                                current_task = current_step['tasks'][0]
                                
                            # use task simplification chain
                            simplification_chain = get_task_simplification_chain()
                            
                            response= simplification_chain.invoke({
                                "task_description": current_task['task_description'],
                                "required_documents": current_task['required_documents'] or "None specified",
                                "step_title": current_step['step_title'],
                                "phase_title": current_step['phase_title']
                            })
                            
                            st.markdown(response)
                            
                            # Add helpful links if available
                            if current_task.get('task_link'):
                                st.markdown(f"\n LINK: {current_task['task_link']}")
                        
                        else:
                            response= " I couldnot find a current task. Please check your status"
                            st.warning(response)
                         
                    # Handle status questions by refreshing and displaying current data.   
                    elif is_status_question:                                            
                        #Refresh status data to get latest informtion
                        st.session_state.current_status_data = get_full_procedure_data(current_user['user_id'], selected_position_id)
                        
                        if st.session_state.current_status_data:
                            response = generate_chatbot_response(st.session_state.current_status_data)
                            st.markdown(response)
                        
                        else:
                            response = " I couldnot find any procedure data for this position."
                            st.error(response)
                    
                    # Handle general procedure questions using LangChain SQL generattion.
                    else:
                        try:
                            full_chain = get_full_chain()
                            response = full_chain.invoke({"question": user_input})
                            st.markdown(response)
                        except Exception as e:
                            response = f"Sorry, I encountered an error.{str(e)}"
                            st.error(response)
                            
                    
                    # add bot response to chat history
                    st.session_state.messages.append({"role": "assistant", "content": response})
                    
                    # save bot response to database   
                    save_chat_message(
                        st.session_state.chat_session_id, 
                        "bot", 
                        response
                        )  
    # Right column: Interactive checklist                
    with col2:
        st.subheader("Current Tasks")
        
        if st.session_state.current_status_data and st.session_state.current_status_data['current_step']:
            status_data = st.session_state.current_status_data
            current_step = status_data['current_step']
            progress = status_data['progress']
            
            #progress indicator
            progress_bar_value = progress["current_step_percentage"]/ 100
            st.progress(progress_bar_value, text = f"Step Progress:{progress['current_step_completed']}/{progress['current_step_total']}tasks({progress['current_step_percentage']:.1f}%)")
            
            #current step info
            with st.container(border=True):
                st.markdown(f" **PHASE:** {current_step['phase_title']}")
                st.markdown(f"**Step:** {current_step['step_title']}")
                
            #show link if available
            if current_step.get('step_link'):
                st.markdown(f"LINK: ({current_step['step_link']})")
        
            st.markdown("**Tasks:**") 
        
            # display tasks as checkboxes
            task_updated= False
            for task in current_step['tasks']:
                checkbox_key = f"task_{task['task_id']}_pos_{selected_position_id}"
                is_completed = task['task_status'] == 'completed'
                
                #created checkbox
                task_checked = st.checkbox(
                    label= task['task_description'],
                    value = is_completed,
                    key = checkbox_key,
                    help = f"Required documents: {task['required_documents']}" if task['required_documents'] else "No specific documents required."
                    )       
                
                # Handle task status updates when checkbox state changed
                if task_checked != is_completed:
                    new_status = 'completed' if task_checked else 'not_started'
                    success = update_task_status(
                        current_user['user_id'], 
                        selected_position_id, 
                        task['task_id'], 
                        new_status
                        )              
                    
                    if success:
                        task_updated = True
                        status_text = "completed" if task_checked else "pending"
                        st.success(f"Task marked as {status_text}!")
                    else:
                        st.error("Failed to update task status.")
                    
            
                #show task link if available
                if task.get('task_link'):
                    st.markdown(f"LINK: ({task['task_link']})")
                    
                st.markdown("---")
            
            # Auto refresh if any task was updated
            if task_updated:
                st.session_state.current_status_data = get_full_procedure_data(
                    current_user['user_id'], 
                    selected_position_id
                    )
                st.rerun()
                
            #quick actions
            st.markdown("---")
            col_refresh = st.columns(1)[0]
            
            with col_refresh:
                if st.button("Refresh status"):
                    st.session_state.current_status_data = get_full_procedure_data(
                        current_user['user_id'], 
                        selected_position_id
                        )
                    st.rerun()
        
        else:
            # Show message when no status data is loaded yet
            st.info(" The checklist will appear here once you select a job positon assigned to you")

with st.sidebar:
    st.header("How to use!!")
    st.markdown("""
                **Left Side- Chat interface:**\n
                - ASk questions about your progress \n
                - Ask about next steps \n
                - Say "help me with the current task" or for simplified explanation \n
                - General procedure questions
                
                **Right Side - Tasks:**\n
                - View your current tasks\n
                - Checkoff completed tasks\n
                - Track your progress
                """)
    st.markdown("---")
    
    #chat history info
    #if st.session_state.chat_session_id:
     #   st.info(f"Chat Session Id:{st.session_state.chat_session_id}")
    