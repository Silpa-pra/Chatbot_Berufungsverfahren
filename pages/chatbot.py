import streamlit as st
import sys
import os
from datetime import datetime, timedelta

# Add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from checklist_utils import( 
    get_all_positions,
    get_shared_procedure_data,
    update_shared_task_status,
    create_chat_session, 
    save_chat_message,
    get_chat_history,
    save_document_upload,
    get_uploaded_document,
    read_uploaded_document,
    delete_uploaded_doc
    )
from chatbot_logic import (
    get_full_chain,
    get_profile_suggestion,
    detect_current_task_question,
    generate_task_response,
    detect_status_question,
    detect_task_help_request,
    )

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
session_defaults = {
    "messages": [],
     "selected_position_id" : None,
     "current_status_data" : None,
     "chat_session_id": None    
}

for key, default in session_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default
    

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
            
position_options = {
    pos['position_id']: {
        'display': f"{pos['position_title']}({pos['kenziffer']})" + (" HEAD" if pos['is_head'] else ""),
        'data': pos
    }
    for pos in positions
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
        st.info(f" **Department:** {pos_data['department']}")
    with col2:
        st.info(f" **BA Committee:** {pos_data['ba_name']}")
    with col3:
        role = "BA Head" if pos_data['is_head'] else "BA Member"
        st.info(f" **Your role:** {role}")


# --- Handle position selection ---
if selected_position_id !=  st.session_state.selected_position_id:
    st.session_state.selected_position_id = selected_position_id
    st.session_state.messages = []
    st.session_state.current_status_data = None
    st.session_state.chat_session_id = None
    st.session_state.show_completion_history = False
    
    # load checklist immediately when positionis selected
    if selected_position_id:
        st.session_state.current_status_data = get_shared_procedure_data(
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
        limit=7 # loads only last 7 message
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
    st.success(f"**Working on:** {current_position_name}")
    
    # Create 2 column: chat on left, checklist on right
    col1, col2 = st.columns(2)
    
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
                    
                    
                    is_task_help_request = detect_task_help_request(user_input) #check if user is asking for task help / simplification                    
                    is_status_question = detect_status_question(user_input) # check if user is asking aabout status/progress
                    is_current_task_question = detect_current_task_question(user_input)   # check if user is asking about current task or next task
                    
                    if is_current_task_question:
                        if 'next' in user_input.lower() or 'after' in user_input.lower():
                            response_type = "next_task"
                        else:
                            response_type = "current_task"
                        response = generate_task_response(st.session_state.current_status_data, response_type, user_input)
                        st.markdown(response)
                    
                    elif is_task_help_request:
                        response = generate_task_response(st.session_state.current_status_data, "task_help", user_input)
                        st.markdown(response)
                        
                    elif is_status_question:
                        st.session_state.current_status_data = get_shared_procedure_data(selected_position_id)
                        response = generate_task_response(st.session_state.current_status_data, "status", user_input)
                        st.markdown(response)
                        
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
        st.subheader("Shared BA Progress") 
        
        if st.session_state.current_status_data and st.session_state.current_status_data['current_step']:
            status_data = st.session_state.current_status_data
            
            #check if the user selected a different step to view
            if 'selected_step_index' in st.session_state:
                current_step = status_data['all_steps'][st.session_state.selected_step_index]
            else:               
                current_step = status_data['current_step']
            progress = status_data['progress']
            
            #progress indicator
            progress_bar_value = progress["current_step_percentage"]/ 100
            st.progress(progress_bar_value, text = f"Step Progress:{progress['current_step_completed']}/{progress['current_step_total']}tasks({progress['current_step_percentage']:.1f}%)")
            
            #current step info
            with st.container(border=True):
                st.markdown(f" **PHASE:** {current_step['phase_title']}")
                st.markdown(f"**STEP:** {current_step['step_title']}")
                st.caption("Shared progress - all BA memberes see the same status")
                
            #show link if available
            if current_step.get('step_link'):
                st.markdown(f"LINK: ({current_step['step_link']})")
        
            st.markdown("**TASKS:**") 
            
            if 'success_messages' in st.session_state and st.session_state.success_messages:
                        # Display messages that are less than 5 seconds old
                        current_time = datetime.now()
                        messages_to_keep = []
                        messages_displayed = False
    
                        for msg_data in st.session_state.success_messages:
                            # Using datetime comparison
                            if current_time - msg_data['timestamp'] < timedelta(seconds=8):
                                st.success(msg_data['message'])
                                if msg_data['notes']:
                                    st.info(f"Note saved: {msg_data['notes']}")
                                messages_to_keep.append(msg_data)
                                messages_displayed = True
    
                        # Keep only recent messages
                        st.session_state.success_messages = messages_to_keep
                        
                        if messages_displayed:
                            st.markdown("")
                            
                        if not messages_to_keep:
                            st.session_state.success_messages=[]
        
            # display tasks as checkboxes
            task_updated= False
            for task in current_step['tasks']:
                task_id = task.get('task_id', 'unknown')
                checkbox_key = f"task_{task.get('task_id', 'unknown')}_pos_{selected_position_id}"
                is_completed = task.get('task_status', 'not_started') == 'completed'
                
                # task lable with completion attribution
                task_label = task.get('task_description', 'Unknown task')
                if is_completed :
                    task_label += " **-(Completed)** "
                    
                # task checkbox with info
                col_task, col_info = st.columns([4,1])
                
                with col_task:
                    task_checked = st.checkbox(
                        label = task_label,
                        value = is_completed,
                        key = checkbox_key,
                        help = f"Required documents: {task.get('required_documents', 'None specified')}" if task.get('required_documents') else "No specific documents required.",
                        disabled = False
                    )
                
                with col_info:
                    if is_completed and task.get('completed_at'):
                        st.caption(f"Completed at: {task['completed_at'].strftime('%m.%d.%Y')}")
                    elif not is_completed:
                        st.caption("Pending")
                
                #Show completion notes if available
                if is_completed and task.get('notes'):
                    st.caption(f"Note: {task['notes']}")
                    
                # show required documents and upload option if task requires documents
                if task.get('required_documents') and task.get('required_documents')!= 'None specified':
                    with st.expander(f"**Required!!** {task.get('required_documents')}", expanded = not is_completed):
                        #check if document was already uploaded
                        existing_doc = get_uploaded_document(task_id, selected_position_id)
                        if existing_doc:
                            st.success(f"Document uploaded:{existing_doc['original_filename']}")
                            
                            #add delete button
                            if st.button("Delete Document", key = f"delete_doc_{task_id}_{selected_position_id}"):
                                if delete_uploaded_doc(task_id, selected_position_id):
                                    st.success("Document deleted successfully.")
                                    st.rerun()
                                else:
                                    st.error("Failed to delete the document. Plese try again")
                            
                        # show file uploader if not completed and no existing document
                        if not is_completed and not existing_doc:
                            uploaded_file = st.file_uploader(
                                "Upload document (.txt file only)",
                                type=['txt'],
                                key = f"doc_{task_id}_{selected_position_id}",
                                help = f"Upload {task.get('required_documents')}"
                            )
                            if uploaded_file is not None:
                                #Show file info
                                st.info(f"Selected: {uploaded_file.name}({uploaded_file.size/ 1024:.1f}KB)")
                                
                                #store in session state temporarily
                                if 'pending_uploads' not in st.session_state:
                                    st.session_state.pending_uploads = {}
                                st.session_state.pending_uploads[task_id] = uploaded_file
                                
                         
                        # AI suggestion button - only if document exists    
                        if "Requirement Profile" in task.get('required_documents', ''):
                            col_suggest, col_space = st.columns([2,2])
                            
                            with col_suggest:
                                if st.button("Get AI Suggestions", key=f"suggest_{task_id}_{selected_position_id}"):
                                    with st.spinner("Analyzing profile and generating suggestions..."):
                                        # Read the document content
                                        uploaded_doc = None
                                        if 'pending_uploads' in st.session_state and task_id in st.session_state.pending_uploads:
                                            uploaded_doc = st.session_state.pending_uploads[task_id].read().decode("utf-8")
                                        else:
                                            uploaded_doc = read_uploaded_document(task_id, selected_position_id)
                                            
                                        if uploaded_doc:
                                            result = get_profile_suggestion(uploaded_doc)
                                        # Store in session state...
                                        else:
                                            st.error("Could not read the document!!")
                                            
                                        
                                        if uploaded_doc:
                                            #Get ai suggestions
                                            result = get_profile_suggestion(uploaded_doc)
                                            
                                            # Store in session state
                                            if 'ai_suggestions' not in st.session_state:
                                                st.session_state.ai_suggestions = {}
                                            st.session_state.ai_suggestions[task_id] = result
                                        else:
                                            st.error("Could not read the document!!")
                            
                            if 'ai_suggestions' in st.session_state and task_id in st.session_state.ai_suggestions:
                                result = st.session_state.ai_suggestions[task_id]
                                
                                if result['status'] == 'success':
                                    st.markdown("### AI Suggestions")

                                    #show suggestions
                                    for  suggestion in result['suggestions']:
                                        st.markdown(f"{suggestion}")
                                    
                                    # Show missing elements
                                    if result['missing_elements']:
                                        st.markdown(" Missing Elements")
                                        for element in result['missing_elements']:
                                            st.markdown(f"{element}")
            
                                    # Show improved version
                                    if result['improved_version']:
                                        st.markdown(" Suggested Improved Version")
                                        st.markdown(" **Here's an improved version incorporating the suggestions:** ")
                                        st.markdown("#### Download Improved Version")
                    
                                            # Download button
                                        st.download_button(
                                                label="Click to Download",
                                                data=result['improved_version'],
                                                file_name=f"improved_profile_{task_id}.txt",
                                                mime="text/plain",
                                                key=f"download_sugg_{task_id}_{selected_position_id}"
                                                )
                    
                                            # Show in text area
                                        st.text_area(
                                                "Improved Profile:",
                                                value=result['improved_version'],
                                                height=400,
                                                key=f"improved_sugg_{task_id}_{selected_position_id}"
                                                )
                                
                                else:
                                    st.error("Could not generate suggestions. Please try again.")
        
                                # Clear suggestions button
                                if st.button("Clear Suggestions", key=f"clear_sugg_{task_id}_{selected_position_id}"):
                                    del st.session_state.ai_suggestions[task_id]
                                    st.rerun()                              
                        
                       
                # Handle task status updates with shared progress
                if task_checked != is_completed:
                    confirm_key = f"confirm_{task_id}_{selected_position_id}"
                     
                    # show notes input and confirmation
                    with st.container():
                        col_note, col_action = st.columns([3,1])
                        
                        with col_note:
                            if task_checked:
                                notes = st.text_area("Completion note:",
                                                 key = f"notes_{task['task_id']}_{selected_position_id}",
                                                 placeholder= "Brief note about completion, documents submitted, etc.",
                                                 height = 70
                                                 )
                            
                            else:
                                notes = None
                        with col_action:
                            can_complete = True
                            warning_msg = None
                            
                            if task_checked and task.get('required_documents') and task.get('required_documents') != 'None specified':
                                # check if document is uploaded or exists
                                has_upload = (
                                    'pending_uploads' in st.session_state and task_id in st.session_state.pending_uploads
                                )
                                has_existing = get_uploaded_document(task_id, selected_position_id) is not None
                                
                                if not has_upload and not has_existing:
                                    can_complete = False
                                    warning_msg = "Please upload the required .txt document first"
                            
                            # show warning if needed        
                            if warning_msg:
                                st.warning(warning_msg)
                                
                            button_text = "ConfirmComplete" if task_checked else "Confirm Pending"
                            button_type = "primary" if task_checked else "secondary"
                            
                            if st.button(button_text, key = confirm_key, type = button_type, disabled = not can_complete):
                                new_status = 'completed' if task_checked else 'not_started'
                                
                                # Handle file if present
                                upload_success = True
                                if task_checked and 'pending_uploads' in st.session_state and task_id in st.session_state.pending_uploads:
                                    uploaded_file = st.session_state.pending_uploads[task_id]
                                    upload_success = save_document_upload(
                                        current_user.get('user_id'),
                                        selected_position_id,
                                        task_id,
                                        uploaded_file
                                    )
                                    
                                    if upload_success:
                                        #clear from pending uploads
                                        del st.session_state.pending_uploads[task_id]
                                    else:
                                        st.error("Failed to upload document. Please try again.")
                                
                                if upload_success:
                                    success = update_shared_task_status(
                                        selected_position_id, 
                                        task_id, 
                                        new_status,
                                        current_user['user_id'],
                                        current_user['username'],
                                        notes if task_checked else None
                                        )              
                    
                                    if success:
                                        task_updated = True
                                        status_text = "completed" if task_checked else "pending"
                        
                                        if 'success_messages' not in st.session_state:
                                            st.session_state.success_messages = []
                            
                                        success_msg = f"Task marked as {status_text} fot the entire BA Group!!"
                                        
                                        if task_checked and task.get('required_documents') and 'uploaded_file' in locals():
                                            success_msg += f"Document  '{uploaded_file.name}' uploaded successfully!"
                                        
                                        st.session_state.success_messages.append({
                                            'message': success_msg,
                                            'notes' : notes if task_checked and notes else None,
                                            'timestamp': datetime.now()
                                        })
                                    else:
                                        st.error("Failed to update task status.")
                                             
            
                #show task link if available
                if task.get('task_link'):
                    st.markdown(f"LINK: ({task['task_link']})")
                    
                st.markdown("---")
            
            # Auto refresh if any task was updated
            if task_updated:
                st.session_state.current_status_data = get_shared_procedure_data(
                    selected_position_id
                    )
                st.rerun()
                
            
            # find which step we are on
            current_step_number = 0
            for i,step in enumerate(status_data['all_steps']):
                if step['step_id'] == current_step['step_id']:
                    current_step_number =i
                    break
            
            # Navigate buttons in columns
            col_nav, col_refresh = st.columns(2)
            
            with col_nav:      
                # show previous button if not on first step
                if current_step_number > 0:
                    if st.button("<- Go to Previous Step", key = "prev_step"):
                        # Store which step to show
                        st.session_state.selected_step_index = current_step_number - 1
                        st.rerun()           
            
            with col_refresh:
                # show return button if viewing old step, otherwise refresh button
                if 'selected_step_index' in st.session_state:
                    if st.button("Return to Current Step", key = "return_current"):
                        del st.session_state.selected_step_index
                        st.rerun()
                else:
                    if st.button("Refresh status"):
                        st.session_state.current_status_data = get_shared_procedure_data( 
                            selected_position_id
                            )
                        st.rerun()
                        
            st.markdown("---")
            
        
        else:
            # Show message when no status data is loaded yet
            st.info(" The checklist will appear here once you select a job positon assigned to you")

with st.sidebar:
    st.header("How to use!!")
    st.markdown("""
                **Left Side- Chat interface:**\n
                - Ask questions about your progress \n
                - Ask about next steps \n
                - Say "help me with the current task" or for simplified explanation \n
                - General procedure questions
                
                **Right Side - Tasks:**\n
                - View tasks shared among BA group\n
                - See what has already been done\n
                - Checkoff completed tasks\n
                - Track overall committee progress
                """)
    st.markdown("---")
    
    # Logout button
    if st.button("Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.current_user = None
        st.switch_page("app.py")
    
   