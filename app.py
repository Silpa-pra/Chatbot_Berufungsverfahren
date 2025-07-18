import streamlit as st
from auth import register_user, get_user_by_login, verify_password


st.set_page_config(page_title ="Login | Signup")

# Simulate session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None

#login | Signup Tab
st.title("Welcome to :red[Chatbot]")
    
tab1, tab2 = st.tabs(["Login", "Signup"])

with tab1:
    #Allow user to enter either username or email
    login_identifier = st.text_input('Username or Email', key = 'login_identifier', placeholder = 'Enter a your Username or email')
    password = st.text_input('Password', type = 'password', key = 'login_password', placeholder = 'Enter your Password')

    if st.button('Login'):
        if not login_identifier or not password:
            st.warning("Please fill both username/email and password")
        else:
            try:
                user = get_user_by_login(login_identifier)
                
                if user and verify_password(password, user["password_hash"]):
                    st.session_state.logged_in = True
                    st.session_state.current_user = user
                    st.success("Logged in successfully!")
                    st.switch_page("pages/chatbot.py")
                else:
                    # Simplified and more secure error message
                    st.error("Invalid credentials. Please try again.")
            except Exception as e:
                st.error(f"Login error: {str(e)}")

    st.caption("Don't have an account? Switch to Signup tab")

with tab2:
    email = st.text_input('Email Address', key ='signup_email', placeholder = 'mustermann@example.com')
    password = st.text_input('Password', type = 'password', key = 'signup_password', placeholder = 'Enter a Password')
    username = st.text_input('Username', key = 'signup_username', placeholder = 'Enter a unique Username')
    user_type = st.selectbox('User Type', ['BV', 'HR'], key = 'signup_user_type')
   
    if st.button("Register"):
        if not email or not password or not username or not user_type:
            st.warning("All fields except department are required!")
        elif '@' not in email:
            st.warning("Please enter a valid email address")
        elif len(password) < 6:
            st.error("Password must be atleast 6 characters")
        else:
            try:
                if register_user(username, password, email, user_type):
                    st.success("Resgistration successful! Please login")
                else:
                    st.error("Registration failed! Username or emails already exists")
            except Exception as e:
                st.error(f"Registration error: {str(e)}")
    
    st.caption("Already have an account? Switch to Login tab")