# 📄 Metascreener ML — Deduplication, Dashboard Counts & Enhanced Roles

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
    cred = credentials.Certificate("firebase_credentials.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

st.title("📊 Metascreener ML — Systematic Review Screening Assistant")

# Deduplication Function
def deduplicate(df):
    df['dedup_key'] = df['title'].str.lower().str.strip()
    deduped_df = df.drop_duplicates(subset='dedup_key')
    duplicates_detected = len(df) - len(deduped_df)
    return deduped_df, duplicates_detected

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
login_option = st.sidebar.radio("", ["Sign Up", "Login"])

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

if 'user_email' in st.session_state:
    st.sidebar.header("Dashboard")

    projects = [doc.id for doc in db.collection("projects").stream()]
    project_name = st.sidebar.selectbox("Select Project", projects)

    if st.session_state.get('role') == "Admin":
        collaborator_email = st.sidebar.text_input("Invite Collaborator Email")
        if st.sidebar.button("Invite Collaborator") and project_name and collaborator_email:
            send_html_welcome_email(collaborator_email, project_name)
            st.sidebar.write(f"✅ Invitation sent to {collaborator_email}")

    if project_name:
        df_doc = db.collection("projects").document(project_name).get()
        if df_doc.exists:
            df = pd.DataFrame(df_doc.to_dict()['data'])

            total_uploaded = len(df)
            deduped_df, duplicates_detected = deduplicate(df)
            unique_after_dedup = len(deduped_df)

            st.sidebar.write(f"Articles uploaded: {total_uploaded}")
            st.sidebar.write(f"Duplicates detected: {duplicates_detected}")
            st.sidebar.write(f"Unique articles after deduplication: {unique_after_dedup}")

            if st.sidebar.button("Deduplicate Automatically"):
                db.collection("projects").document(project_name).set({"data": deduped_df.to_dict(orient='records')})
                st.success("Deduplication complete and saved.")
                df = deduped_df

            included = (df['decision'] == 'Include').sum()
            excluded = (df['decision'] == 'Exclude').sum()
            unscreened = unique_after_dedup - included - excluded

            # Progress Chart
            fig = go.Figure(go.Indicator(
                mode = "gauge+number",
                value = (included+excluded)/unique_after_dedup*100 if unique_after_dedup else 0,
                title = {'text': "Screening Progress (%)"},
                gauge = {'axis': {'range': [0,100]}, 'bar': {'color': "#4CAF50"}}
            ))
            st.plotly_chart(fig)

            if not df[df['decision']==''].empty:
                record = df[df['decision']==''].iloc[0]
                st.subheader("Current Record")
                st.write(f"**Title:** {record.get('title', 'NA')}")
                st.write(f"**Abstract:** {record.get('abstract', 'NA')}")
                st.write(f"**Year:** {record.get('publication_year', 'NA')}")
                st.write(f"**Journal:** {record.get('journal', 'NA')}")
                st.write(f"**Type of Article:** {record.get('type_of_article', 'NA')}")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ Include"):
                        df.loc[record.name, 'decision'] = 'Include'
                        df.loc[record.name, 'reviewer'] = st.session_state['user_email']
                        db.collection("projects").document(project_name).set({"data": df.to_dict(orient='records')})
                        st.experimental_rerun()
                with col2:
                    reason = st.selectbox("Reason for Exclusion", ["Wrong population", "Wrong intervention", "Wrong study design", "Not original research", "Non-English", "Duplicate"])
                    if st.button("🚫 Exclude"):
                        df.loc[record.name, 'decision'] = 'Exclude'
                        df.loc[record.name, 'reason'] = reason
                        df.loc[record.name, 'reviewer'] = st.session_state['user_email']
                        db.collection("projects").document(project_name).set({"data": df.to_dict(orient='records')})
                        st.experimental_rerun()

else:
    st.info("👆 Please sign up or log in to begin.")

# Notes:
# 🔷 Adds automatic deduplication module with dashboard counts.
# 🔷 Shows uploaded, duplicates detected, and unique counts.
# 🔷 Includes HTML branded welcome email, progress chart, and roles.
# 🔷 App remains named Metascreener ML.
