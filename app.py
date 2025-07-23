import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from io import StringIO
import base64
import rispy
import plotly.graph_objects as go
from transformers import pipeline as hf_pipeline
import firebase_admin
from firebase_admin import credentials, firestore, auth
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

# 🔷 Firebase init (Secrets preferred, fallback to local)
def init_firebase():
    if not firebase_admin._apps:
        try:
            cred_json = json.loads(st.secrets["firebase_credentials_json"])
            cred = credentials.Certificate(cred_json)
            firebase_admin.initialize_app(cred)
            st.info("✅ Firebase initialized from Streamlit Secrets")
        except KeyError:
            if os.path.exists("firebase_credentials.json"):
                cred = credentials.Certificate("firebase_credentials.json")
                firebase_admin.initialize_app(cred)
                st.warning("⚠️ Firebase initialized from local file")
            else:
                st.error("❌ Firebase credentials not found. Please configure Streamlit Secrets or local file.")

init_firebase()
db = firestore.client()

# 🔷 Welcome Email (HTML)
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

# 🔷 Password reset
def send_password_reset_email(email):
    try:
        link = auth.generate_password_reset_link(email)
        st.info(f"Password reset link: {link}")
    except Exception as e:
        st.error(f"Failed to send reset link: {e}")

# 🔷 Deduplicate
def deduplicate(df):
    df['dedup_key'] = df['title'].str.lower().str.strip()
    deduped_df = df.drop_duplicates(subset='dedup_key')
    return deduped_df, len(df) - len(deduped_df)

# 🔷 UI
st.title("📊 Metascreener ML — Systematic Review Screening Assistant")

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
            st.success(f"Created as {role} and logged in as {user.email}")
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
            st.error("Authentication failed.")
elif login_option == "Reset Password":
    email = st.sidebar.text_input("Enter your email")
    if st.sidebar.button("Send Password Reset Link"):
        send_password_reset_email(email)

if 'user_email' in st.session_state:
    st.sidebar.header("Dashboard")

    projects = [doc.id for doc in db.collection("projects").stream()]
    project_name = st.sidebar.selectbox("Select Project", projects)

    if st.session_state.get('role') == "Admin":
        collab_email = st.sidebar.text_input("Invite Collaborator Email")
        if st.sidebar.button("Invite Collaborator") and project_name and collab_email:
            send_html_welcome_email(collab_email, project_name)
            st.sidebar.write(f"✅ Invitation sent to {collab_email}")

        st.sidebar.subheader("Manage Collaborators")
        collaborators_ref = db.collection("users").stream()
        for doc in collaborators_ref:
            collaborator = doc.id
            current_role = doc.to_dict().get("role", "Reviewer")
            new_role = st.sidebar.selectbox(f"Role for {collaborator}",
                                            ["Admin", "Reviewer"],
                                            index=0 if current_role == "Admin" else 1,
                                            key=collaborator)
            if st.sidebar.button(f"Update Role: {collaborator}"):
                db.collection("users").document(collaborator).update({"role": new_role})
                st.sidebar.success(f"Updated role: {collaborator} → {new_role}")

    if project_name:
        df_doc = db.collection("projects").document(project_name).get()
        if df_doc.exists:
            df = pd.DataFrame(df_doc.to_dict()['data'])
            uploaded = len(df)
            deduped_df, dups = deduplicate(df)
            unique = len(deduped_df)

            st.sidebar.write(f"Uploaded: {uploaded}")
            st.sidebar.write(f"Duplicates: {dups}")
            st.sidebar.write(f"Unique: {unique}")

            if st.sidebar.button("Deduplicate Automatically"):
                db.collection("projects").document(project_name).set({"data": deduped_df.to_dict(orient='records')})
                st.success("Deduplicated and saved.")
                df = deduped_df

            included = (df['decision'] == 'Include').sum()
            excluded = (df['decision'] == 'Exclude').sum()
            unscreened = unique - included - excluded

            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=(included+excluded)/unique*100 if unique else 0,
                title={'text': "Screening Progress (%)"},
                gauge={'axis': {'range': [0,100]}, 'bar': {'color': "#4CAF50"}}
            ))
            st.plotly_chart(fig)

            if not df[df['decision']==''].empty:
                record = df[df['decision']==''].iloc[0]
                st.subheader("Current Record")
                st.write(f"**Title:** {record.get('title', 'NA')}")
                st.write(f"**Abstract:** {record.get('abstract', 'NA')}")
                st.write(f"**Year:** {record.get('publication_year', 'NA')}")
                st.write(f"**Journal:** {record.get('journal', 'NA')}")
                st.write(f"**Type:** {record.get('type_of_article', 'NA')}")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ Include"):
                        df.loc[record.name, 'decision'] = 'Include'
                        df.loc[record.name, 'reviewer'] = st.session_state['user_email']
                        db.collection("projects").document(project_name).set({"data": df.to_dict(orient='records')})
                        st.experimental_rerun()
                with col2:
                    reason = st.selectbox("Reason for Exclusion", ["Wrong population", "Wrong intervention", "Wrong design", "Not research", "Non-English", "Duplicate"])
                    if st.button("🚫 Exclude"):
                        df.loc[record.name, 'decision'] = 'Exclude'
                        df.loc[record.name, 'reason'] = reason
                        df.loc[record.name, 'reviewer'] = st.session_state['user_email']
                        db.collection("projects").document(project_name).set({"data": df.to_dict(orient='records')})
                        st.experimental_rerun()

else:
    st.info("👆 Please sign up, log in, or reset password to begin.")
