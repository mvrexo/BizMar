"""BizMar's responsive login view."""
from display_preferences import tr
from pathlib import Path
import base64
import re
import streamlit as st

ROOT = Path(__file__).resolve().parent


def render_login(sign_in, google_enabled=False, google_unauthorized=False):
    st.markdown(
        tr('<style>' + (ROOT / 'styles/login.css').read_text(encoding='utf-8-sig') + '</style>'),
        unsafe_allow_html=True,
    )
    with st.container(key='bizmar_login_header'):
        st.image((ROOT / 'assets/bizmar_logo.png').read_bytes(), width=150)
    with st.container(key='bizmar_login_layout'):
        brand, form = st.columns([1, 1], gap='large')
        with brand, st.container(key='bizmar_brand'):
            animation = base64.b64encode(
                (ROOT / 'assets/icons/animated_login.svg').read_bytes()
            ).decode('ascii')
            st.markdown(
                tr('<div class="bizmar-login-animation">'
                f'<img src="data:image/svg+xml;base64,{animation}" '
                'alt="Animated business illustration" width="900" height="700">'
                '</div>'),
                unsafe_allow_html=True,
            )
        with form, st.container(key='bizmar_login_card'):
            st.markdown(
                tr('<p class="bizmar-eyebrow">WELCOME BACK!</p>'
                '<p class="bizmar-card-description">Enter your email and your password to access your dashboard.</p>'),
                unsafe_allow_html=True,
            )
            if google_unauthorized:
                st.error(tr('This Google account is not authorized.'))
                if st.button(tr('Sign out of Google')):
                    st.logout()
                return

            with st.form('email_login_form'):
                email = st.text_input(
                    tr('Email address'),
                    placeholder=tr('you@example.com'),
                    icon=':material/mail:',
                    key='login_email',
                )
                password = st.text_input(
                    tr('Password'),
                    type='password',
                    placeholder=tr('Enter your password'),
                    icon=':material/lock:',
                    key='login_password',
                )
                clicked = st.form_submit_button(
                    tr('Log In →'),
                    type='primary',
                    use_container_width=True,
                    key='login_submit',
                )

            if clicked:
                if not email.strip() or not password:
                    st.error(tr('Please enter your email address and password.'))
                elif not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email.strip()):
                    st.error(tr('Please enter a valid email address.'))
                else:
                    success, message = sign_in(email.strip().lower(), password)
                    if success:
                        st.rerun()
                    else:
                        st.error(tr(message))

            if google_enabled:
                google_icon = base64.b64encode(
                    (ROOT / 'assets/icons/google.svg').read_bytes()
                ).decode('ascii')
                st.markdown(
                    tr(
                        '<style>.st-key-bizmar_google_login button p { display: flex; align-items: center; justify-content: center; gap: 10px; }'
                        '.st-key-bizmar_google_login button p::before { content: ""; display: inline-block; width: 20px; height: 20px; flex-shrink: 0;'
                        f'background: url("data:image/svg+xml;base64,{google_icon}") center / contain no-repeat; }}'
                        '</style>'
                    ),
                    unsafe_allow_html=True,
                )
                st.markdown(
                    tr('<div class="bizmar-divider">or</div>'),
                    unsafe_allow_html=True,
                )
                if st.button(
                    tr('Continue with Google'),
                    key='bizmar_google_login',
                    use_container_width=True,
                ):
                    st.login()
