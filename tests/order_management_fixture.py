import streamlit as st
st.session_state.authenticated = True
st.session_state.local_owner_email = 'synthetic-owner@example.test'
from order_management import render_order_management
render_order_management()
