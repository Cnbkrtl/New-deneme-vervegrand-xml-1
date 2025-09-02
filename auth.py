import streamlit as st
import hashlib
from config_manager import load_all_keys

def check_password(password):
    """Direct password check for demo purposes."""
    return password == "195119"

def login_page():
    """Displays the login page and handles authentication."""
    st.markdown("""
    <div class="main-header">
        <h1>🔐 Admin Login</h1>
        <p>Please log in to access the Shopify Sync application.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("Username", value="Admin", disabled=True)
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if username == "Admin" and check_password(password):
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                # Try to load all API keys on successful login
                load_all_keys()
                st.success("Logged in successfully!")
                st.rerun()
            else:
                st.error("Incorrect username or password.")
    return False

def display_main_app():
    """This function will be called to display the main application after login."""
    # This is a placeholder. The main app logic from streamlit_app.py will be moved here.
    st.title("Main Application")
    st.write("Welcome to the main application!")

def get_page():
    """Gets the current page from session state, defaulting to dashboard."""
    return st.session_state.get("page", "dashboard")

def set_page(page_name):
    """Sets the current page in session state."""
    st.session_state.page = page_name
