# 📄 Metascreener ML — Streamlit App with Welcome Email & Walkthrough

import streamlit as st
import pandas as pd
import numpy as np
from transformers import pipeline as hf_pipeline
import firebase_admin
from firebase_admin import credentials, firestore, auth
from io import StringIO
import rispy
import base64
import uuid
import smtplib
from email.mime.text import MIMEText

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_credentials.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# App Title
st.title("📊 Metascreener ML — Systematic Review Screening Assistant")

# Email sending function
def send_welcome_email(email, project_name, token):
    message = f"""
    Welcome to Metascreener ML!

    You have been added to the project: {project_name}

    To access the project, use this shared access token: {token}

    Walkthrough:
    1️⃣ Go to the Metascreener ML app.
    2️⃣ Select 'Access via Shared Link' on the sidebar.
    3️⃣ Enter the shared token: {token}.
    4️⃣ Begin screening records, marking them as Include/Exclude.

    Progress and conflicts will be tracked automatically.

    Happy reviewing!
    Metascreener ML Team
    """
    msg = MIMEText(message)
    msg['Subject'] = f"Access to Metascreener ML Project: {project_name}"
    msg['From'] = "noreply@metascreenerml.com"
    msg['To'] = email

    try:
        with smtplib.SMTP('localhost') as server:  # Replace with real SMTP server
            server.send_message(msg)
        st.success(f"Welcome email sent to {email}")
    except Exception as e:
        st.error(f"Failed to send email: {e}")

# Collaboration Options
st.sidebar.header("Access Options")
login_option = st.sidebar.radio("Choose Access Method:", ["Sign Up", "Login with Email", "Access via Shared Link"])

if login_option == "Sign Up":
    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Sign Up"):
        try:
            user = auth.create_user(email=email, password=password)
            st.session_state['user_email'] = user.email
            st.success(f"Account created and logged in as {user.email}")
            # Send welcome email
            send_welcome_email(email, "New User Guide", "N/A")
        except:
            st.error("Failed to create account. Email may already exist.")

elif login_option == "Login with Email":
    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        try:
            user = auth.get_user_by_email(email)
            st.session_state['user_email'] = user.email
            st.success(f"Logged in as {user.email}")
        except:
            st.error("Authentication failed.")

elif login_option == "Access via Shared Link":
    shared_link_token = st.sidebar.text_input("Enter Shared Link Token")
    if st.sidebar.button("Access Project") and shared_link_token:
        st.session_state['user_email'] = f"guest_{shared_link_token}"
        st.success("Access granted via shared link.")

# Load/Save Project Data
def load_project_data(project_name):
    doc_ref = db.collection("projects").document(project_name)
    doc = doc_ref.get()
    if doc.exists:
        return pd.DataFrame(doc.to_dict()['data'])
    return None

def save_project_data(project_name, df):
    doc_ref = db.collection("projects").document(project_name)
    doc_ref.set({"data": df.to_dict(orient='records')})

# Best ML Model: BERT-based classifier
def bert_predict(df):
    if df['decision'].isin(['Include', 'Exclude']).sum() >= 10:
        model = hf_pipeline("text-classification", model="nlptown/bert-base-multilingual-uncased-sentiment")
        unscreened = df[df['decision'] == '']
        texts = (unscreened['title'].fillna('') + ' ' + unscreened['abstract'].fillna('')).tolist()
        preds = model(texts)
        scores = [p['score'] if p['label'].endswith('5') else 1-p['score'] for p in preds]  # crude positive relevance
        unscreened = unscreened.copy()
        unscreened['pred_score'] = scores
        return unscreened.sort_values('pred_score', ascending=False)
    return df[df['decision'] == '']

if 'user_email' in st.session_state:
    st.sidebar.header("Project")
    project_name = st.sidebar.text_input("Project Name")

    collaborator_email = st.sidebar.text_input("Invite Collaborator Email")
    if st.sidebar.button("Create New Project & Invite") and project_name and collaborator_email:
        token = str(uuid.uuid4())
        db.collection("projects").document(project_name).set({"data": [], "shared_token": token})
        send_welcome_email(collaborator_email, project_name, token)
        st.sidebar.write(f"✅ Project created. Token sent to {collaborator_email}")

    if st.sidebar.button("Load Project") and project_name:
        df = load_project_data(project_name)
        if df is not None:
            st.session_state['df'] = df
            st.success(f"Project '{project_name}' loaded.")
        else:
            st.warning("No existing project found. Upload new file.")

    uploaded_file = st.sidebar.file_uploader("Upload citations (.RIS, .NBIB, .CSV)", type=["ris", "nbib", "csv"])

    def parse_file(uploaded_file):
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        elif uploaded_file.name.endswith(".ris") or uploaded_file.name.endswith(".nbib"):
            entries = rispy.load(StringIO(uploaded_file.getvalue().decode("utf-8")))
            df = pd.DataFrame(entries)
        else:
            st.error("Unsupported file type.")
            return None
        df['decision'] = ''
        df['reason'] = ''
        df['reviewer'] = st.session_state['user_email']
        return df

    if uploaded_file:
        df = parse_file(uploaded_file)
        if df is not None:
            st.session_state['df'] = df
            save_project_data(project_name, df)
            st.success(f"Uploaded and saved {len(df)} records.")

    if 'df' in st.session_state:
        df = st.session_state['df']
        unscreened = bert_predict(df)

        if not unscreened.empty:
            record = unscreened.iloc[0]
            st.subheader("Current Record")
            st.write(f"**Title:** {record.get('title', '')}")
            st.write(f"**Abstract:** {record.get('abstract', '')}")

            keywords = ["pancreatic", "neuroendocrine", "PRRT", "everolimus", "sunitinib"]
            for kw in keywords:
                if kw.lower() in str(record.get('title', '')).lower() or kw.lower() in str(record.get('abstract', '')).lower():
                    st.markdown(f"- 🔍 **{kw}**")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Include"):
                    df.loc[record.name, 'decision'] = 'Include'
                    df.loc[record.name, 'reviewer'] = st.session_state['user_email']
                    save_project_data(project_name, df)
                    st.experimental_rerun()
            with col2:
                reason = st.selectbox("Reason for Exclusion", ["Wrong population", "Wrong intervention", "Wrong study design", "Not original research", "Non-English", "Duplicate"])
                if st.button("🚫 Exclude"):
                    df.loc[record.name, 'decision'] = 'Exclude'
                    df.loc[record.name, 'reason'] = reason
                    df.loc[record.name, 'reviewer'] = st.session_state['user_email']
                    save_project_data(project_name, df)
                    st.experimental_rerun()
        else:
            st.success("🎉 All records screened!")

        st.sidebar.header("Progress Dashboard")
        total = len(df)
        included = (df['decision'] == 'Include').sum()
        excluded = (df['decision'] == 'Exclude').sum()
        unscreened_count = total - included - excluded
        st.sidebar.metric("Total", total)
        st.sidebar.metric("Included", included)
        st.sidebar.metric("Excluded", excluded)
        st.sidebar.metric("Unscreened", unscreened_count)

        st.sidebar.header("PRISMA Counts")
        st.sidebar.write(f"Records identified: {total}")
        st.sidebar.write(f"Records included: {included}")
        st.sidebar.write(f"Records excluded: {excluded}")

else:
    st.info("👆 Please sign up, log in, or enter shared link token to begin.")

# Notes:
# 🔷 Sends welcome email with walkthrough & token on signup or project creation.
# 🔷 Owner can invite collaborators via email.
# 🔷 App remains named Metascreener ML.
