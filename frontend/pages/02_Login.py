import re
import time

import streamlit as st

from services.api_service import api_service
from utils.auth import init_auth_state
from utils.navigation import switch_page
from utils.ui_helpers import apply_custom_css, init_page_config, show_error, show_success

AUTH_VIEWS = ["Login", "Register", "Verify Email", "Reset Password"]

# Initialize
init_page_config("Login | News Central", "")
apply_custom_css()
init_auth_state()

st.session_state.setdefault("auth_view", "Login")
st.session_state.setdefault("password_reset_token", "")
st.session_state.setdefault("email_verification_token", "")
st.session_state.setdefault("verify_email_input", "")
st.session_state.setdefault("reset_email_input", "")
st.session_state.setdefault("verify_show_token_form", False)
st.session_state.setdefault("reset_show_token_form", False)
st.session_state.setdefault("auth_view_next", "")

# Backward-compatible state migration from previous tab-based flow
if st.session_state.pop("show_register", False):
    st.session_state["auth_view"] = "Register"
if st.session_state.pop("show_verify_form", False):
    st.session_state["auth_view"] = "Verify Email"
if st.session_state.pop("show_reset_form", False):
    st.session_state["auth_view"] = "Reset Password"
if st.session_state.pop("auto_verify_email", False):
    st.session_state["auth_view"] = "Verify Email"

# If a token arrives through deep link, open step-2 directly
if st.session_state.get("email_verification_token"):
    st.session_state["verify_show_token_form"] = True
    st.session_state["auth_view"] = "Verify Email"
if st.session_state.get("password_reset_token"):
    st.session_state["reset_show_token_form"] = True
    st.session_state["auth_view"] = "Reset Password"


def validate_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number"
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"
    return True, "Password is strong"


def validate_username(username: str) -> tuple[bool, str]:
    if len(username) < 3:
        return False, "Username must be at least 3 characters"
    if len(username) > 20:
        return False, "Username must be less than 20 characters"
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return False, "Username can only contain letters, numbers, and underscores"
    return True, "Username is valid"


def _queue_auth_view(view: str, notice: str = "") -> None:
    """Queue auth view switch for next rerun (safe with widget state)."""
    st.session_state["auth_view_next"] = view
    if notice:
        st.session_state["auth_notice"] = notice
    st.rerun()


def _render_login_panel() -> None:
    st.markdown("### :material/login: Welcome Back!")
    st.caption("Enter your credentials to access your personalized news feed")

    with st.form("login_form"):
        email = st.text_input(
            "Email Address",
            placeholder="your.email@example.com",
            icon=":material/email:",
        )
        password = st.text_input(
            "Password",
            type="password",
            placeholder="Enter your password",
            icon=":material/lock:",
        )

        col1, col2 = st.columns([3, 1])
        with col1:
            remember_me = st.checkbox("Remember me", value=False)
        with col2:
            submit = st.form_submit_button("Login", use_container_width=True, type="primary")

        if submit:
            if not email or not password:
                show_error("Please fill in all fields")
            elif not validate_email(email):
                show_error("Invalid email format")
            else:
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
        if st.button("Forgot Password?", use_container_width=True):
            st.session_state["reset_show_token_form"] = False
            _queue_auth_view("Reset Password")
    with col2:
        if st.button("Create Account", use_container_width=True):
            _queue_auth_view("Register")


def _render_register_panel() -> None:
    st.markdown("### :material/person_add: Create Your Account")
    st.caption("Join thousands of users getting personalized news recommendations")

    with st.form("register_form"):
        col1, col2 = st.columns(2)

        with col1:
            full_name = st.text_input(
                "Full Name",
                placeholder="John Doe",
                icon=":material/person:",
            )

        with col2:
            username = st.text_input(
                "Username",
                placeholder="Unique username (3-20 characters): johndoe",
                icon=":material/alternate_email:",
            )

        email = st.text_input(
            "Email Address",
            placeholder="your.email@example.com",
            icon=":material/email:",
        )

        col1, col2 = st.columns(2)
        with col1:
            password = st.text_input(
                "Password",
                type="password",
                placeholder="Create a strong password: Min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char",
                icon=":material/lock:",
            )
        with col2:
            confirm_password = st.text_input(
                "Confirm Password",
                type="password",
                placeholder="Re-enter your password",
                icon=":material/lock:",
            )

        if password:
            is_valid, message = validate_password(password)
            if is_valid:
                st.success(message)
            else:
                st.warning(message)

        submit = st.form_submit_button("Create Account", use_container_width=True, type="primary")

        if submit:
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

            if errors:
                for error in errors:
                    show_error(error)
            else:
                with st.spinner("Creating your account..."):
                    result = api_service.register(
                        email=email,
                        password=password,
                        username=username,
                        full_name=full_name,
                    )

                if result["success"]:
                    st.session_state["verify_email_input"] = email.strip()
                    st.session_state["verify_show_token_form"] = False
                    _queue_auth_view(
                        "Verify Email",
                        "Account created successfully. Check your email for the verification token.",
                    )
                else:
                    show_error(f"Registration failed: {result.get('error', 'Unknown error')}")

    st.divider()
    st.caption(":material/shield: Secured with JWT authentication and encrypted passwords.")


def _render_verify_panel() -> None:
    st.markdown("### :material/verified: Verify Your Email")
    st.caption("Step 1: Enter your email and request a verification token.")

    default_email = st.session_state.get("verify_email_input", "")
    with st.form("resend_verification_form", clear_on_submit=False):
        resend_email = st.text_input(
            "Email Address",
            value=default_email,
            placeholder="your.email@example.com",
            icon=":material/email:",
        )
        resend_submit = st.form_submit_button(
            "Send Verification Token",
            use_container_width=True,
            type="primary",
        )

        if resend_submit:
            email_value = (resend_email or "").strip()
            if not email_value:
                show_error("Please enter your email.")
            elif not validate_email(email_value):
                show_error("Invalid email format")
            else:
                with st.spinner("Sending verification email..."):
                    result = api_service.resend_verification(email_value)
                if result["success"]:
                    st.session_state["verify_email_input"] = email_value
                    st.session_state["verify_show_token_form"] = True
                    show_success("Verification token sent. Enter it in step 2.")
                else:
                    show_error(f"Failed to resend verification: {result.get('error', 'Unknown error')}")

    st.divider()

    if not st.session_state.get("verify_show_token_form", False):
        st.info("Step 2 will be available after you submit your email in step 1.")
        return

    st.caption("Step 2: Enter your verification token.")
    token_default = st.session_state.get("email_verification_token", "")
    with st.form("verify_email_form"):
        verification_token = st.text_input(
            "Verification Token",
            value=token_default,
            placeholder="Paste your verification token",
            icon=":material/key:",
        )
        verify_submit = st.form_submit_button(
            "Verify Email",
            use_container_width=True,
            type="primary",
        )

        if verify_submit:
            token_value = (verification_token or "").strip()
            st.session_state["email_verification_token"] = ""
            if not token_value:
                show_error("Verification token is required.")
            else:
                with st.spinner("Verifying email..."):
                    result = api_service.verify_email(token_value)
                if result["success"]:
                    st.session_state["verify_show_token_form"] = False
                    _queue_auth_view("Login", "Email verified successfully. You can now log in.")
                else:
                    show_error(f"Email verification failed: {result.get('error', 'Unknown error')}")


def _render_reset_panel() -> None:
    st.markdown("### :material/password: Reset Your Password")
    st.caption("Step 1: Enter your email and request a reset token.")

    default_email = st.session_state.get("reset_email_input", "")
    with st.form("request_reset_form", clear_on_submit=False):
        reset_email = st.text_input(
            "Email Address",
            value=default_email,
            placeholder="your.email@example.com",
            icon=":material/email:",
        )
        request_reset_submit = st.form_submit_button(
            "Send Reset Token",
            use_container_width=True,
            type="primary",
        )

        if request_reset_submit:
            email_value = (reset_email or "").strip()
            if not email_value:
                show_error("Please enter your email.")
            elif not validate_email(email_value):
                show_error("Invalid email format")
            else:
                with st.spinner("Sending reset token..."):
                    result = api_service.request_password_reset(email_value)
                if result["success"]:
                    st.session_state["reset_email_input"] = email_value
                    st.session_state["reset_show_token_form"] = True
                    show_success("Reset token sent. Enter token and new password in step 2.")
                else:
                    show_error(f"Failed to request reset: {result.get('error', 'Unknown error')}")

    st.divider()

    if not st.session_state.get("reset_show_token_form", False):
        st.info("Step 2 will be available after you submit your email in step 1.")
        return

    st.caption("Step 2: Enter reset token and your new password.")
    token_default = st.session_state.get("password_reset_token", "")
    with st.form("apply_reset_form"):
        reset_token = st.text_input(
            "Reset Token",
            value=token_default,
            placeholder="Paste your reset token",
            icon=":material/key:",
        )
        new_password = st.text_input(
            "New Password",
            type="password",
            placeholder="Create a strong password",
            icon=":material/lock:",
        )
        confirm_new_password = st.text_input(
            "Confirm New Password",
            type="password",
            placeholder="Re-enter new password",
            icon=":material/lock:",
        )
        apply_reset_submit = st.form_submit_button(
            "Reset Password",
            use_container_width=True,
            type="primary",
        )

        if apply_reset_submit:
            token_value = (reset_token or "").strip()
            st.session_state["password_reset_token"] = ""
            if not token_value:
                show_error("Reset token is required.")
            elif not new_password or not confirm_new_password:
                show_error("Please enter and confirm your new password.")
            elif new_password != confirm_new_password:
                show_error("Passwords do not match")
            else:
                password_valid, password_msg = validate_password(new_password)
                if not password_valid:
                    show_error(password_msg)
                else:
                    with st.spinner("Resetting password..."):
                        result = api_service.reset_password(token_value, new_password)
                    if result["success"]:
                        st.session_state["reset_show_token_form"] = False
                        _queue_auth_view("Login", "Password reset successful. Please log in with your new password.")
                    else:
                        show_error(f"Password reset failed: {result.get('error', 'Unknown error')}")


def main() -> None:
    st.title(":material/lock_open: Authentication")

    queued_view = (st.session_state.get("auth_view_next") or "").strip()
    if queued_view in AUTH_VIEWS:
        st.session_state["auth_view"] = queued_view
    st.session_state["auth_view_next"] = ""

    auth_notice = st.session_state.pop("auth_notice", None)
    if auth_notice:
        st.info(auth_notice)

    if not st.session_state.get("is_authenticated", False):
        if api_service.auto_login():
            st.success("Welcome back! Auto-login successful.")
            time.sleep(1)
            switch_page("news-feed")

    if st.session_state.get("is_authenticated", False):
        st.success("You are already logged in!")
        if st.button("Go to News Feed"):
            switch_page("news-feed")
        st.stop()

    selected_view = st.segmented_control(
        "Authentication",
        AUTH_VIEWS,
        key="auth_view",
        selection_mode="single",
        width="stretch",
        label_visibility="collapsed",
    )
    active_view = selected_view or st.session_state.get("auth_view", "Login")

    if active_view == "Login":
        _render_login_panel()
    elif active_view == "Register":
        _render_register_panel()
    elif active_view == "Verify Email":
        _render_verify_panel()
    else:
        _render_reset_panel()


if __name__ == "__main__":
    main()
