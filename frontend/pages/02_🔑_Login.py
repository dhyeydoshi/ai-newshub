import streamlit as st
import re
import time
from services.api_service import api_service
from utils.auth import init_auth_state
from utils.ui_helpers import init_page_config, apply_custom_css, show_error, show_success

# Initialize
init_page_config("Login | News Summarizer", "🔑")
apply_custom_css()
init_auth_state()

if not st.session_state.get("is_authenticated", False):
    if api_service.auto_login():
        st.success("Welcome back! Auto-login successful.")
        time.sleep(1)
        st.switch_page("pages/03_📱_News_Feed.py")


# Redirect if already authenticated
if st.session_state.get("is_authenticated", False):
    st.success("You are already logged in!")
    if st.button("Go to News Feed"):
        st.switch_page("pages/03_📱_News_Feed.py")
    st.stop()


def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    return True, "Password is strong"


def validate_username(username: str) -> tuple[bool, str]:
    """Validate username"""
    if len(username) < 3:
        return False, "Username must be at least 3 characters"
    if len(username) > 20:
        return False, "Username must be less than 20 characters"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores"
    return True, "Username is valid"


def main():
    st.title("🔑 Authentication")

    # Tabs for Login and Register
    tab1, tab2 = st.tabs(["🔓 Login", "📝 Register"])

    # ========================================================================
    # LOGIN TAB
    # ========================================================================
    with tab1:
        st.markdown("### Welcome Back!")
        st.caption("Enter your credentials to access your personalized news feed")

        with st.form("login_form"):
            email = st.text_input(
                "Email Address",
                placeholder="your.email@example.com",
                help="Enter your registered email address"
            )

            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter your password",
                help="Your account password"
            )

            col1, col2 = st.columns([3, 1])
            with col1:
                remember_me = st.checkbox("Remember me", value=False)
            with col2:
                submit = st.form_submit_button("Login", use_container_width=True, type="primary")

            if submit:
                # Validation
                if not email or not password:
                    show_error("Please fill in all fields")
                elif not validate_email(email):
                    show_error("Invalid email format")
                else:
                    # Attempt login
                    with st.spinner("Authenticating..."):
                        result = api_service.login(email, password, remember_me)

                    if result["success"]:
                        show_success("Login successful! Redirecting...")
                        time.sleep(1)
                        st.rerun()
                    else:
                        show_error(f"Login failed: {result.get('error', 'Unknown error')}")

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Forgot Password?", use_container_width=True):
                st.info("Password reset feature coming soon!")
        with col2:
            if st.button("📝 Create Account", use_container_width=True):
                st.info("Switch to the Register tab above!")

    # ========================================================================
    # REGISTER TAB
    # ========================================================================
    with tab2:
        st.markdown("### Create Your Account")
        st.caption("Join thousands of users getting personalized news recommendations")

        with st.form("register_form"):
            col1, col2 = st.columns(2)

            with col1:
                full_name = st.text_input(
                    "Full Name",
                    placeholder="John Doe",
                    help="Your full name"
                )

            with col2:
                username = st.text_input(
                    "Username",
                    placeholder="johndoe",
                    help="Unique username (3-20 characters)"
                )

            email = st.text_input(
                "Email Address",
                placeholder="your.email@example.com",
                help="Your email address"
            )

            col1, col2 = st.columns(2)

            with col1:
                password = st.text_input(
                    "Password",
                    type="password",
                    placeholder="Create a strong password",
                    help="Min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char"
                )

            with col2:
                confirm_password = st.text_input(
                    "Confirm Password",
                    type="password",
                    placeholder="Re-enter your password"
                )

            # Show password strength
            if password:
                is_valid, message = validate_password(password)
                if is_valid:
                    st.success(f"✅ {message}")
                else:
                    st.warning(f"⚠️ {message}")

            agree_terms = st.checkbox(
                "I agree to the Terms of Service and Privacy Policy",
                help="You must agree to continue"
            )

            submit = st.form_submit_button("Create Account", use_container_width=True, type="primary")

            if submit:
                # Validation
                errors = []

                if not all([full_name, username, email, password, confirm_password]):
                    errors.append("All fields are required")

                if not validate_email(email):
                    errors.append("Invalid email format")

                username_valid, username_msg = validate_username(username)
                if not username_valid:
                    errors.append(username_msg)

                password_valid, password_msg = validate_password(password)
                if not password_valid:
                    errors.append(password_msg)

                if password != confirm_password:
                    errors.append("Passwords do not match")

                if not agree_terms:
                    errors.append("You must agree to the terms and conditions")

                if errors:
                    for error in errors:
                        show_error(error)
                else:
                    # Attempt registration
                    with st.spinner("Creating your account..."):
                        result = api_service.register(
                            email=email,
                            password=password,
                            username=username,
                            full_name=full_name
                        )

                    if result["success"]:
                        show_success("Account created successfully! Please login.")
                        st.info("Switch to the Login tab to access your account")
                    else:
                        show_error(f"Registration failed: {result.get('error', 'Unknown error')}")

        st.divider()

        st.markdown("""
        #### 🔒 Security Features
        - 🔐 End-to-end encryption
        - 🛡️ JWT token authentication
        - 🔑 Secure password hashing
        - 📧 Email verification (optional)
        """)


if __name__ == "__main__":
    main()

