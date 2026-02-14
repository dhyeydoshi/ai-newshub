import streamlit as st
import plotly.graph_objects as go
from services.api_service import api_service
from utils.auth import init_auth_state, require_auth, logout
from utils.navigation import switch_page
from utils.ui_helpers import (
    init_page_config,
    apply_custom_css,
    show_error,
    show_success,
    show_loading,
    format_date,
    show_toast,
)

# Initialize
init_page_config("Profile | News Summarizer", "")
apply_custom_css()
init_auth_state()


@require_auth
def main() -> None:
    """User profile page"""
    st.title("My Profile")
    st.caption(f"Logged in as **{st.session_state.get('username', 'User')}**")

    st.divider()

    with show_loading("Loading profile..."):
        result = api_service.get_profile()

    if not result["success"]:
        show_error(f"Failed to load profile: {result.get('error')}")
        return

    profile = result["data"]

    tab1, tab2, tab3, tab4 = st.tabs([
        "Profile Info",
        "Reading History",
        "Analytics",
        "Account",
    ])

    with tab1:
        st.markdown("### Personal Information")

        col1, col2 = st.columns([1, 2])

        with col1:
            st.markdown(
                """
            <div style='text-align: center; padding: 2rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 50%; width: 150px; height: 150px; margin: auto;'>
                <h1 style='color: white; margin-top: 40px; font-size: 4rem;'></h1>
            </div>
            """,
                unsafe_allow_html=True,
            )

            st.markdown("<br>", unsafe_allow_html=True)

            if st.button("Change Photo", use_container_width=True):
                st.info("Photo upload coming soon!")

        with col2:
            with st.form("profile_form"):
                full_name = st.text_input(
                    "Full Name",
                    value=profile.get("full_name", ""),
                    placeholder="John Doe",
                )

                email = st.text_input(
                    "Email Address",
                    value=profile.get("email", ""),
                    disabled=True,
                    help="Email cannot be changed",
                )

                username = st.text_input(
                    "Username",
                    value=profile.get("username", ""),
                    disabled=True,
                    help="Username cannot be changed",
                )

                bio = st.text_area(
                    "Bio",
                    value=profile.get("bio", ""),
                    placeholder="Tell us about yourself...",
                    height=100,
                )

                col1, col2 = st.columns(2)
                with col1:
                    location = st.text_input("Location", value=profile.get("location", ""))
                with col2:
                    website = st.text_input("Website", value=profile.get("website", ""))

                if st.form_submit_button("Save Changes", use_container_width=True, type="primary"):
                    update_data = {
                        "full_name": full_name,
                        "bio": bio,
                        "location": location,
                        "website": website,
                    }

                    with show_loading("Updating profile..."):
                        update_result = api_service.update_profile(update_data)

                    if update_result["success"]:
                        show_success("Profile updated successfully!")
                        show_toast("Changes saved!")
                    else:
                        show_error(f"Update failed: {update_result.get('error')}")

        st.divider()

        st.markdown("### Account Statistics")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Articles Read",
                profile.get("total_articles_read", 0),
                "+5 this week",
            )

        with col2:
            st.metric(
                "Total Time",
                f"{profile.get('total_reading_time', 0) // 60}h",
                "+2h this week",
            )

        with col3:
            st.metric("Streak", f"{profile.get('reading_streak', 0)} days", "")

        with col4:
            member_since = profile.get("created_at", "")
            if member_since:
                st.metric("Member Since", format_date(member_since))

    with tab2:
        st.markdown("### Your Reading History")
        st.caption("Articles you've read recently")

        with show_loading("Loading history..."):
            history_result = api_service.get_reading_history(limit=20)

        if history_result["success"]:
            history = history_result["data"].get("history", [])

            if history:
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    filter_topic = st.selectbox(
                        "Filter by topic",
                        ["All", "Technology", "Science", "Business", "Politics", "Sports"],
                    )
                with col2:
                    sort_by = st.selectbox(
                        "Sort by",
                        ["Most Recent", "Most Time Spent", "Highest Rated"],
                    )
                with col3:
                    if st.button("Clear History"):
                        st.warning("Are you sure? This action cannot be undone.")

                st.divider()

                for idx, item in enumerate(history[:10]):
                    with st.container():
                        col1, col2 = st.columns([3, 1])

                        with col1:
                            st.markdown(f"**{item.get('title', 'Untitled')}**")
                            st.caption(
                                f"{item.get('source', 'Unknown')} | {format_date(item.get('read_at', ''))}"
                            )

                        with col2:
                            time_spent = item.get("time_spent_seconds", 0)
                            st.metric("Time", f"{time_spent // 60}m {time_spent % 60}s")

                        if st.button("Read Again", key=f"reread_{idx}"):
                            st.session_state.selected_article = item.get("article_id")
                            switch_page("article-view")

                        st.divider()

                if len(history) > 10:
                    if st.button("Load More"):
                        show_toast("Loading more history...")
            else:
                st.info("No reading history yet. Start reading articles to build your history!")
        else:
            show_error("Failed to load reading history")

    with tab3:
        st.markdown("### Your Reading Analytics")
        st.caption("Insights into your reading habits")

        col1, col2 = st.columns(2)

        with col1:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                    y=[5, 8, 6, 9, 7, 12, 10],
                    mode="lines+markers",
                    name="Articles Read",
                    line=dict(color="#667eea", width=3),
                    marker=dict(size=8),
                )
            )
            fig.update_layout(
                title="Weekly Reading Activity",
                xaxis_title="Day",
                yaxis_title="Articles",
                height=300,
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig = go.Figure(
                data=[
                    go.Pie(
                        labels=["Technology", "Science", "Business", "Politics", "Sports"],
                        values=[35, 25, 20, 12, 8],
                        hole=0.3,
                    )
                ]
            )
            fig.update_layout(title="Reading by Topic", height=300)
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        st.markdown("#### Detailed Statistics")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(
                """
            **This Week**
            - Articles: 42
            - Time: 5.2 hours
            - Avg/day: 6 articles
            """
            )

        with col2:
            st.markdown(
                """
            **This Month**
            - Articles: 180
            - Time: 22 hours
            - Completion: 85%
            """
            )

        with col3:
            st.markdown(
                """
            **All Time**
            - Articles: 1,234
            - Time: 156 hours
            - Favorite: Technology
            """
            )

    with tab4:
        st.markdown("### Account Security")

        with st.expander("Change Password"):
            with st.form("password_form"):
                current_password = st.text_input("Current Password", type="password")
                new_password = st.text_input(
                    "New Password",
                    type="password",
                    help="Min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char",
                )
                confirm_password = st.text_input("Confirm New Password", type="password")

                if st.form_submit_button("Update Password", type="primary"):
                    if not all([current_password, new_password, confirm_password]):
                        show_error("All fields are required")
                    elif new_password != confirm_password:
                        show_error("Passwords do not match")
                    else:
                        st.info("Password change feature coming soon!")

        st.divider()

        st.markdown("### Two-Factor Authentication")
        st.caption("Add an extra layer of security to your account")

        if st.button("Enable 2FA", type="primary"):
            st.info("2FA setup coming soon!")

        st.divider()

        st.markdown("### Active Sessions")
        st.caption("Manage your active login sessions")

        sessions = [
            {"device": "Chrome on Windows", "location": "New York, US", "last_active": "Just now"},
            {"device": "Safari on iPhone", "location": "New York, US", "last_active": "2 hours ago"},
        ]

        for idx, session in enumerate(sessions):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{session['device']}**")
                st.caption(f"{session['location']} | {session['last_active']}")
            with col2:
                if st.button("Revoke", key=f"revoke_{idx}"):
                    show_success("Session revoked")
            st.divider()

        st.markdown("### Sign Out")

        col1, col2 = st.columns([2, 1])
        with col1:
            if st.button("Logout from this device", use_container_width=True):
                logout()
        with col2:
            if st.button("Logout from all devices", use_container_width=True, type="primary"):
                logout(all_devices=True)

        st.divider()

        st.markdown("### Danger Zone")

        with st.expander("Delete Account", expanded=False):
            st.warning("Warning: This action is permanent and cannot be undone!")

            st.markdown(
                """
Deleting your account will:
            - Remove all your personal data
            - Delete your reading history
            - Cancel any subscriptions
            - Remove all preferences and settings
            """
            )

            confirm_delete = st.text_input(
                "Type 'DELETE' to confirm",
                placeholder="DELETE",
            )

            if st.button("Delete My Account", type="primary", disabled=confirm_delete != "DELETE"):
                st.error("Account deletion is permanent. Contact support to proceed.")


if __name__ == "__main__":
    main()
