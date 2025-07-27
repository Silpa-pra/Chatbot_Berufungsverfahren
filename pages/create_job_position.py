import streamlit as st
import sys 
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hr_utils import(
    create_ba_committee_with_position,
    get_available_users_for_ba,
    get_all_procedures 
)

st.set_page_config(page_title="Create new Job Position", layout="wide")

#Authentication check
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Please login to view the page.")
    st.switch_page("app.py")
    st.stop()
    
if st.session_state.current_user["user_type"] != "HR":
    st.error("Access Denied. This page is only accessible for HR users.")
    st.stop()
    
#Backbutton 
if st.button("<- Back to Dashboard", type = "secondary"):
    st.switch_page("pages/hr_dashboard.py")
    
#Header
st.markdown("Create New Job Position")
st.markdown("Fill in the details below to create a new position with BA comittee")
st.divider()

# Initialize session state for multi-step form
if "form_step" not in st.session_state:
    st.session_state.form_step = 1
if "selected_members" not in st.session_state:
    st.session_state.selected_members = []
if "form_data" not in st.session_state:
    st.session_state.form_data ={}
    
#success state
if "position_created" in st.session_state and st.session_state.position_created:
    st.success("Position created successfully!")
    
    #display creation summary
    if "created_position_data" in st.session_state:
        data = st.session_state.created_position_data
        st.markdown("### Created Position Summary")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Position Details:**")
            st.write("- **Title:** {data['position_title']}")
            st.write("- **Department:** {data['department']}")
            st.write("- **Reference:** {data['kenziffer']}")       
            st.write("- **Position ID:** {data['position_id']}")      
        
        with col2:
            st.info(f""" 
                    **BA Committee:**
                    -**Name:** {data['ba_name']}
                    -**BA ID:** {data['ba_id']}
                    -**Members:**{len(data['members'])}selected
                    -**Head:**{data['ba_head_name']}
                    """)
            
        #member list
        st.markdown("**BA Members:**")
        for member in data['members']:
            if member['is_head']:
                st.markdown(f"**{member['username']} ({member['email']})** - *Head*")
            else:
                st.markdown(f"{member['username']} ({member['email']})")
                
    
    # action button
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Create Another Position", type="primary", use_container_width= True):
            #reset form
            for key in ["position_created", "created_position_data", "form_step", "selected_members", "form_data"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    
    with col2:
        if st.button("Back to Dashboard", type="secondary", use_container_width=True):
            st.switch_page("pages/hr_dashboard.py")
    st.stop()

#form steps
col1, col2 = st.columns(2)   

with col1:
    # Step 1 - Position Details
    st.markdown("### Position Details")
    
    with st.form("position_details"):
        col1, col2 = st.columns(2)
        
        with col1:
            position_title = st.text_input( "position Title*",
                                           placeholder= "eg., Professor for Computer Science",
                                           value = st.session_state.form_data.get('position_title','')
                                           )
            
            kenziffer = st.text_input("Reference Number(kenziffer) *",
                                      placeholder="eg., W§-2025-001",
                                      value= st.session_state.form_data.get('kenziffer',''),
                                      help= "Must be unique")
        
        with col2:
            department = st.text_input( "Department *",
                                           placeholder= "eg., Faculty of Engineering",
                                           value = st.session_state.form_data.get('department','')
                                           )
            
            procedures = get_all_procedures()
            if not procedures:
                st.error("No Procedures available. Please create a procedure first")
                st.stop()
                
            selected_procedure = st.selectbox("Hiring Procedure",
                                              options=[p['procedure_id'] for p in procedures],
                                              format_func= lambda x: next(p ['procedure_title'] for p in procedures if p ['procedure_id'] == x),
                                              help = "Select the appropriate hiring procedure"
                                              )
            
        ba_name =st.text_input("BA Committee Name *",
                               placeholder= "eg., BA Informatik 2025",
                               value= st.session_state.form_data.get('ba_name', ''),
                               help = "Name for the committee"
                               )
        
        if st.form_submit_button("Continue to member selection", type="primary"):
            if not all([position_title, department, kenziffer, ba_name]):
                st.error("Please fill all required fields")
            else:
                #save form data
                st.session_state.form_data.update({
                    'position_title': position_title,
                    'department': department,
                    'kenziffer': kenziffer,
                    'ba_name': ba_name,
                    'procedure_id': selected_procedure
                })
                st.session_state.form_step =2
                st.rerun()

#Step 2: BA members( only show if step 1 is completed)
if st.session_state.form_step >= 2:
    st.divider()
    st.markdown("### Select BA Members")
    
    #Get available users
    available_users = get_available_users_for_ba()
    
    if not available_users:
        st.error("No BA users available. Please create BA users first-")
        if st.button("Go back to fix"):
            st.session_state.form_step = 1
            st.rerun()
        st.stop()
        
    
    st.markdown("**Available Users** (Select atleast 2)")
    
    #Multi select for members
    user_options= {user['user_id']: f"{user['username']}({user['email']})" for user in available_users}
    
    selected_user_ids = st.multiselect("Select BA Members",
                                       options= list(user_options.keys()),
                                       format_func= lambda x: user_options[x],
                                       default= st.session_state.selected_members,
                                       help= "Select atleast 2 members for the committee"
                                       )
    
    # Update session state
    st.session_state.selected_members = selected_user_ids
    
    if len(selected_user_ids) >=2:
        #Select BA Head
        selected_user_for_head = {uid: user_options[uid] for uid in selected_user_ids}
        
        ba_head_id = st.selectbox("Select BA Head *",
                                  options=list(selected_user_for_head.keys()),
                                  format_func= lambda x: selected_user_for_head[x],
                                  )
        
        #Step 3. show summary before creatiion
        st.markdown("### Review Before Creation")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Position Details**")
            st.write(f"**Title:** {st.session_state.form_data['position_title']}")
            st.write(f"**Department:** {st.session_state.form_data['department']}")
            st.write(f"**Kennziffer:** {st.session_state.form_data['kenziffer']}")
            st.write(f"**BA Name:** {st.session_state.form_data['ba_name']}")
            
            
            #show selected procedure
            if st.session_state.form_data.get('procedure_id'):
                proc_title = next((p['procedure_title']for p in procedures if p['procedure_id'] == st.session_state.form_data['procedure_id']), "Unknown")
                st.write(f"**Procedure** {proc_title}")
            
        with col2:
            st.markdown("**BA Committee**")
            st.write(f"**Total Members:** {len(selected_user_ids)}")
            st.write(f"**BA Head:** {user_options[ba_head_id]}")
            st.write("**Members:**")       
            for uid in selected_user_ids:
                if uid == ba_head_id:
                    st.write(f"{user_options[uid]}(Head)")
                else:
                    st.write(f"{user_options[uid]}")
                    
        
        # Final submission
        st.divider()
        
        col1, col2 = st.columns([1, 1]) 
        with col1:
            if st.button("<- Back to Edit", use_container_width=True):
                st.session_state.form_step=1
                st.rerun()
                
        with col2:
            if st.button("Create Position", type="primary", use_container_width=True):
                with st.spinner("Creatinf Position and BA committee..."):
                    try:
                        #Create the position with Ba committee
                        result = create_ba_committee_with_position(
                            position_title= st.session_state.form_data['position_title'],
                            department=st.session_state.form_data['department'],
                            kenziffer=st.session_state.form_data['kenziffer'],
                            procedure_id=st.session_state.form_data['procedure_id'],
                            created_by=st.session_state.current_user['user_id'],
                            ba_name=st.session_state.form_data['ba_name'],
                            member_ids=selected_user_ids,
                            head_id=ba_head_id
                        )
                        
                        if result['success']:
                            # Store creation data for display
                            st.session_state.created_position_data = {
                                'position_title': st.session_state.form_data['position_title'],
                                'department': st.session_state.form_data['department'],
                                'kenziffer': st.session_state.form_data['kenziffer'],
                                'ba_name': st.session_state.form_data['ba_name'],
                                'position_id': result['position_id'],
                                'ba_id': result['ba_id'],
                                'procedure_id': result.get('procedure_id', 'Auto-assigned'),
                                'members': [user for user in available_users if user['user_id'] in selected_user_ids],
                                'ba_head_name': user_options[ba_head_id]
                            }
                            
                            # Mark as created and add head info
                            for member in st.session_state.created_position_data['members']:
                                member['is_head'] = member['user_id'] == ba_head_id
                            
                            st.session_state.position_created = True
                            st.rerun()
                        else:
                            st.error(f"Failed to create position: {result.get('error', 'Unknown error')}")
                            
                    except Exception as e:
                        st.error(f"Error creating position: {str(e)}")
    
    elif selected_user_ids:
        st.warning(f" Please select at least 2 members. Currently selected: {len(selected_user_ids)}")
    

    # Helper info
    st.divider()
    st.caption("- All fields marked with * are required")
    st.caption("- Kenziffer must be unique across all positions")
    st.caption("- BA committees need at least 2 members")
    st.caption("- One member must be designated as head")