import streamlit as st
import json
import bcrypt
import uuid
import pandas as pd
import rispy
from datetime import datetime, timedelta
import os

DB_FILE = 'users.json'
RECORDS_FILE = 'records.json'

# Helpers
def load_users():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, 'w') as f:
            json.dump({}, f)
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(DB_FILE, 'w') as f:
        json.dump(users, f, indent=2, default=str)

def load_records():
    if not os.path.exists(RECORDS_FILE):
        with open(RECORDS_FILE, 'w') as f:
            json.dump([], f)
    with open(RECORDS_FILE, 'r') as f:
        return json.load(f)

def save_records(records):
    with open(RECORDS_FILE, 'w') as f:
        json.dump(records, f, indent=2, default=str)

def hash_password(password): return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
def check_password(password, hashed): return bcrypt.checkpw(password.encode(), hashed.encode())
def generate_token(): return str(uuid.uuid4())

# Init
users = load_users()
records = load_records()

# Clean expired tokens
now = datetime.utcnow()
for u, d in users.items():
    if d.get('reset_token') and datetime.fromisoformat(d['token_expiry']) < now:
        d['reset_token'] = None
        d['token_expiry'] = None
save_users(users)

# UI
st.title("🔐 Metascreener ML — Screening Tool")

page = st.sidebar.radio("Menu", ["Sign Up", "Login", "Reset Password", "Set New Password", "Dashboard"])

# Auth
if page == "Sign Up":
    email = st.text_input("Email").strip().lower()
    pw = st.text_input("Password", type="password")
    role = st.selectbox("Role", ["reviewer", "admin"])
    if st.button("Register"):
        if email in users:
            st.error("User exists")
        else:
            users[email] = {"password_hash": hash_password(pw), "role": role, "last_reset": None}
            save_users(users)
            st.success("User created")

elif page == "Login" or st.session_state.get("logged_in", False):
    if not st.session_state.get("logged_in", False):
        email = st.text_input("Email").strip().lower()
        pw = st.text_input("Password", type="password")
        if st.button("Login"):
            if email in users and check_password(pw, users[email]['password_hash']):
                st.session_state.update({"logged_in": True, "user_email": email, "role": users[email]["role"]})
                st.success("✅ Logged in")
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")
    else:
        st.header(f"📊 Dashboard ({st.session_state['role'].capitalize()}) — {st.session_state['user_email']}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚪 Log out"):
                st.session_state.clear()
                st.experimental_rerun()
        with col2:
            if st.button("🔒 Reset My Password"):
                token = generate_token()
                users[st.session_state['user_email']]['reset_token'] = token
                users[st.session_state['user_email']]['token_expiry'] = (now + timedelta(hours=1)).isoformat()
                save_users(users)
                reset_link = f"http://localhost:8501/?page=Set%20New%20Password&token={token}"
                st.info(f"Reset link: {reset_link}")

        if st.session_state['role'] == "admin":
            st.subheader("👥 Users")
            for u, d in users.items():
                st.write(f"{u} — {d['role']}")
            st.subheader("📤 Upload Records")
            uploaded = st.file_uploader("Upload RIS/CSV/NBIB", type=["ris", "csv", "nbib"])
            if uploaded:
                if uploaded.name.endswith(".csv"):
                    df = pd.read_csv(uploaded)
                    new_recs = df.to_dict(orient='records')
                else:
                    new_recs = rispy.load(uploaded)
                for r in new_recs:
                    r["decision"] = ""
                    r["reviewer_email"] = ""
                save_records(new_recs)
                st.success(f"Uploaded {len(new_recs)} records")
        else:
            st.subheader("📝 Screening")
            st.write("Click below to start screening records.")
            if st.button("Start Screening"):
                st.experimental_set_query_params(page="Screening")
                st.experimental_rerun()

elif page == "Reset Password":
    email = st.text_input("Email").strip().lower()
    if st.button("Send Reset Link"):
        if email in users:
            token = generate_token()
            users[email]['reset_token'] = token
            users[email]['token_expiry'] = (now + timedelta(hours=1)).isoformat()
            save_users(users)
            reset_link = f"http://localhost:8501/?page=Set%20New%20Password&token={token}"
            st.info(f"Reset link: {reset_link}")
        else:
            st.error("No such user")

elif page == "Set New Password":
    token = st.query_params.get("token", "")
    user = next((u for u, d in users.items() if d.get("reset_token") == token and datetime.utcnow() < datetime.fromisoformat(d["token_expiry"])), None)
    if user:
        new_pw = st.text_input("New Password", type="password")
        if st.button("Set Password"):
            users[user]['password_hash'] = hash_password(new_pw)
            users[user]['reset_token'] = None
            save_users(users)
            st.success("Password updated")
    else:
        st.error("Invalid or expired token")

elif page == "Screening":
    st.header("📝 Screening")
    screened = sum(1 for r in records if r["decision"])
    total = len(records)
    progress = int(screened / total * 100) if total else 0
    st.progress(progress / 100)
    st.write(f"📊 Progress: {progress}% ({screened}/{total})")

    next_rec = next((r for r in records if not r["decision"]), None)
    if next_rec:
        st.write(f"**Title:** {next_rec.get('title', 'N/A')}")
        st.write(f"**Abstract:** {next_rec.get('abstract', 'N/A')}")
        col1, col2 = st.columns(2)
        if col1.button("✅ Include"):
            next_rec["decision"] = "Include"
            next_rec["reviewer_email"] = st.session_state['user_email']
            save_records(records)
            st.experimental_rerun()
        if col2.button("🚫 Exclude"):
            next_rec["decision"] = "Exclude"
            next_rec["reviewer_email"] = st.session_state['user_email']
            save_records(records)
            st.experimental_rerun()
    else:
        st.success("🎉 All records screened!")

    if st.button("⬇️ Export CSV"):
        df = pd.DataFrame(records)
        st.download_button("Download CSV", df.to_csv(index=False).encode(), "screened_records.csv", "text/csv")
    if st.button("⬇️ Export RIS"):
        ris = []
        for r in records:
            ris.append({'TY': 'JOUR', 'TI': r.get('title', ''), 'AB': r.get('abstract', ''), 'N1': f"{r['decision']} by {r['reviewer_email']}"})
        ris_str = rispy.dumps(ris)
        st.download_button("Download RIS", ris_str, "screened_records.ris", "application/x-research-info-systems")
