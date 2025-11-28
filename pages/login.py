import streamlit as st
import pandas as pd

# ---- Load data ----
@st.cache_data
def load_data():
    df = pd.read_csv("pj.csv")
    
    # Normalize email
    df['email'] = df['email'].astype(str).str.strip().str.lower()
    df['passcode'] = df['passcode'].astype(str).str.strip()
    
    return df

df = load_data()

# ---- Initialize session state ----
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "user_email" not in st.session_state:
    st.session_state.user_email = ""

# ---- Login Page ----
st.title("Login Page")

email = st.text_input("Email")
password = st.text_input("Passcode", type="password")

if st.button("Login"):
    email_clean = email.strip().lower()
    

    # Cek apakah email ada di data
    if email_clean in df['email'].values:
        stored_pass = df.loc[df['email'] == email_clean, 'passcode'].values[0]

        # Cek password
        if password == stored_pass:
            st.session_state.logged_in = True
            st.session_state.user_email = email_clean

            st.success("Login berhasil!")
            st.switch_page("pages/dashboards kdm.py")
        else:
            st.error("Passcode salah!")
    else:
        st.error("Email tidak ditemukan!")


st.write("---")
st.write("Pastikan email dan passcode sesuai data di *pj.csv*")


