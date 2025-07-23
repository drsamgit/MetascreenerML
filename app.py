import streamlit as st
import json
import bcrypt
import uuid
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

DB_FILE = 'users.json'

def load_users():
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(DB_FILE, 'w') as f:
        json.dump(users, f, indent=2, default=str)

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def generate_token():
    return str(uuid.uuid4())

def clean_expired_tokens(users):
    now = datetime.utcnow()
    for u, data in users.items():
        if data['reset_token'] and datetime.fromisoformat(data['token_expiry']) < now:
            users[u]['reset_token'] = None
            users[u]['token_expiry'] = None

def send_reset_email(email, reset_link):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "🔐 Password Reset Link"
    msg['From'] = "noreply@metascreenerml.local"
    msg['To'] = email

    html = f"""
    <html>
      <body>
        <p>Hi,<br>
           You requested a password reset.<br>
           Click here: <a href="{reset_link}">Reset Password</a><br>
           This link is valid for 1 hour.
        </p>
      </body>
    </html>
    """
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP('localhost') as server:
            server.send_message(msg)
        st.success(f"Reset link sent to {email}")
    except Exception as e:
        st.error(f"Failed to send email: {e}")

# Initialize
users = load_users()
clean_expired_tokens(users)
save_users(users)

# UI
st.title("🔐 Local Auth with Reset + Email")

page = st.sidebar.radio("Menu", ["Sign Up", "Login", "Reset Password", "Set New Password", "View Users"])

if page == "Sign Up":
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Register"):
        if email in users:
            st.error("Email already exists")
        else:
            users[email] = {
                "password_hash": hash_password(password),
                "reset_token": None,
                "token_expiry": None,
                "last_reset": None
            }
            save_users(users)
            st.success("User created")

elif page == "Login":
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if email in users and check_password(password, users[email]['password_hash']):
            st.success("Logged in!")
        else:
            st.error("Invalid credentials")

elif page == "Reset Password":
    email = st.text_input("Email")
    if st.button("Send Reset Link"):
        if email in users:
            token = generate_token()
            expiry = datetime.utcnow() + timedelta(hours=1)
            users[email]['reset_token'] = token
            users[email]['token_expiry'] = expiry
            users[email]['last_reset'] = datetime.utcnow().isoformat()
            save_users(users)
            reset_link = f"http://localhost:8501/?page=Set%20New%20Password&token={token}"
            send_reset_email(email, reset_link)
        else:
            st.error("Email not found")

elif page == "Set New Password":
    token = st.query_params.get("token", "")
    email = None
    for u, data in users.items():
        if data['reset_token'] == token and datetime.utcnow() < datetime.fromisoformat(data['token_expiry']):
            email = u
            break
    if email:
        st.write(f"Resetting password for {email}")
        new_pw = st.text_input("New Password", type="password")
        if st.button("Set Password"):
            users[email]['password_hash'] = hash_password(new_pw)
            users[email]['reset_token'] = None
            users[email]['token_expiry'] = None
            save_users(users)
            st.success("Password updated")
    else:
        st.error("Invalid or expired token")

elif page == "View Users":
    st.subheader("Registered Users")
    for u, data in users.items():
        st.write(f"📧 **{u}** — Last reset: {data.get('last_reset', 'N/A')}")
