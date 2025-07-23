# 📄 Metascreener ML — Add Password Reset & Change Collaborator Roles

import streamlit as st
import pandas as pd
import numpy as np
from transformers import pipeline as hf_pipeline
import firebase_admin
from firebase_admin import credentials, firestore, auth
from io import StringIO
import rispy
import base64
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import plotly.graph_objects as go

# Initialize Firebase
if not firebase_admin._apps:
   import json
cred_json = json.loads(st.secrets["firebase_credentials_json"])
cred = credentials.Certificate(cred_json)
firebase_admin.initialize_app(cred)

db = firestore.client()

st.title("📊 Metascreener ML — Systematic Review Screening Assistant")

# Password Reset
def send_password_reset_email(email):
    try:
        link = auth.generate_password_reset_link(email)
        st.info(f"Password reset link sent: {link}")
    except Exception as e:
        st.error(f"Failed to send password reset link: {e}")

# HTML Welcome Email
def send_html_welcome_email(email, project_name):
    html_content = f"""
    <html><body>
    <h2 style='color:#4CAF50;'>Welcome to Metascreener ML!</h2>
    <p>You have been invited to collaborate on the project: <strong>{project_name}</strong>.</p>
    <p>Please <a href='https://metascreener.app'>log in here</a> using your email. Your dashboard will display all your projects, including: <strong>{project_name}</strong>.</p>
    <p>Happy screening!<br>— <em>The Metascreener ML Team</em></p>
    </body></html>
    """
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Invitation to Metascreener ML Project: {project_name}"
    msg['From'] = "noreply@metascreenerml.com"
    msg['To'] = email
    msg.attach(MIMEText(html_content, 'html'))
    try:
        with smtplib.SMTP('localhost') as server:
            server.send_message(msg)
        st.success(f"Invitation email sent to {email}")
    except Exception as e:
        st.error(f"Failed to send email: {e}")

# Authentication
st.sidebar.header("User Access")
login_option = st.sidebar.radio("", ["Sign Up", "Login", "Reset Password"])

if login_option == "Sign Up":
    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Password", type="password")
    role = st.sidebar.selectbox("Role", ["Admin", "Reviewer"])
    if st.sidebar.button("Sign Up"):
        try:
            user = auth.create_user(email=email, password=password)
            db.collection("users").document(email).set({"role": role})
            st.session_state['user_email'] = user.email
            st.session_state['role'] = role
            st.success(f"Account created as {role} and logged in as {user.email}")
        except:
            st.error("Failed to create account. Email may already exist.")

elif login_option == "Login":
    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        try:
            user = auth.get_user_by_email(email)
            role_doc = db.collection("users").document(email).get()
            st.session_state['user_email'] = user.email
            st.session_state['role'] = role_doc.to_dict().get("role", "Reviewer")
            st.success(f"Logged in as {user.email} ({st.session_state['role']})")
        except:
            st.error("Authentication failed. Use correct email or reset password.")

elif login_option == "Reset Password":
    email = st.sidebar.text_input("Enter your email")
    if st.sidebar.button("Send Password Reset Link"):
        send_password_reset_email(email)

if 'user_email' in st.session_state:
    st.sidebar.header("Dashboard")

    projects = [doc.id for doc in db.collection("projects").stream()]
    project_name = st.sidebar.selectbox("Select Project", projects)

    if st.session_state.get('role') == "Admin":
        collaborator_email = st.sidebar.text_input("Invite Collaborator Email")
        if st.sidebar.button("Invite Collaborator") and project_name and collaborator_email:
            send_html_welcome_email(collaborator_email, project_name)
            st.sidebar.write(f"✅ Invitation sent to {collaborator_email}")

        st.sidebar.subheader("Manage Collaborators")
        collaborators_ref = db.collection("users").stream()
        for doc in collaborators_ref:
            collaborator = doc.id
            collaborator_role = doc.to_dict().get('role', 'Reviewer')
            new_role = st.sidebar.selectbox(f"Role for {collaborator}", ["Admin", "Reviewer"], index=0 if collaborator_role=="Admin" else 1, key=collaborator)
            if st.sidebar.button(f"Update Role for {collaborator}"):
                db.collection("users").document(collaborator).update({"role": new_role})
                st.sidebar.success(f"Updated role for {collaborator} to {new_role}")

else:
    st.info("👆 Please sign up, log in, or reset password to begin.")

# Notes:
# 🔷 Adds password reset functionality.
# 🔷 Adds Admin ability to change collaborators' roles from dashboard.
# 🔷 App remains named Metascreener ML.
