
import streamlit as st
import pandas as pd
import gspread
import json
import io
from typing import Dict, Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from google.auth.exceptions import RefreshError

# -----------------------------
# CONFIG
# -----------------------------
FOLDER_ID = "1mkUYxy16XNTmhV4uy-DXo5le6oMyvPHs"  # Folder tempat fenomena.json

# -----------------------------
# Get credentials directly from st.secrets (clean & working)
# -----------------------------
def get_credentials(scopes):
    """Return Google Credentials from Streamlit secrets."""
    info = st.secrets["google_credentials"]  # This expects the full JSON dict
    return Credentials.from_service_account_info(info, scopes=scopes)

# -----------------------------
# Create gspread client with retry
# -----------------------------
def create_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = get_credentials(scopes)
    gc = gspread.authorize(creds)

    # Add retry strategy for robustness
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    gc.session.mount("http://", adapter)
    gc.session.mount("https://", adapter)

    return gc

# -----------------------------
# Google Drive service
# -----------------------------
def init_drive():
    scopes = ["https://www.googleapis.com/auth/drive"]
    creds = get_credentials(scopes)
    return build("drive", "v3", credentials=creds)

# -----------------------------
# Load Google Sheet with helpful error messages
# -----------------------------
@st.cache_resource(ttl=60)  # Refresh every 60 seconds
def load_sheet(spreadsheet_name: str = "PJ Kecamatan", worksheet_name: str = "Sheet1"):
    try:
        client = create_gspread_client()
        sheet = client.open(spreadsheet_name).worksheet(worksheet_name)
        return sheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Spreadsheet '{spreadsheet_name}' tidak ditemukan!")
        st.info("""
        Pastikan:
        - Nama spreadsheet **persis sama** (case-sensitive)
        - Service account email sudah di-share sebagai **Editor**
        - Spreadsheet tidak di Trash
        """)
        st.stop()
    except RefreshError:
        st.error("Gagal autentikasi ke Google. Periksa `secrets.toml` → private_key harus pakai enter asli, bukan `\\n`!")
        st.stop()
    except Exception as e:
        st.error("("Terjadi kesalahan saat mengakses Google Sheet.")
        st.exception(e)
        st.stop()

# -----------------------------
# Fenomena.json helpers (Google Drive)
# -----------------------------
def get_file_id(name: str) -> str | None:
    drive = init_drive()
    query = f"name='{name}' and '{FOLDER_ID}' in parents and trashed=false"
    result = drive.files().list(q=query, fields="files(id)").execute()
    files = result.get("files", [])
    return files[0]["id"] if files else None

def load_fenomena_json() -> dict:
    file_id = get_file_id("fenomena.json")
    if not file_id:
        return {}
    drive = init_drive()
    request = drive.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return json.loads(fh.read().decode("utf-8"))

def save_fenomena_json(data: dict):
    drive = init_drive()
    file_id = get_file_id("fenomena.json")
    temp_file = "temp_fenomena.json"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    media = MediaFileUpload(temp_file, mimetype="application/json")
    if file_id:
        drive.files().update(fileId=file_id, media_body=media).execute()
    else:
        metadata = {"name": "fenomena.json", "parents": [FOLDER_ID]}
        drive.files().create(body=metadata, media_body=media).execute()

# -----------------------------
# STREAMLIT APP STARTS HERE
# -----------------------------
st.set_page_config(page_title="Dashboard KDM", page_icon="📊", layout="wide")

# Custom header with logo
logo_url = "https://lamongankab.bps.go.id/_next/image?url=%2Fassets%2Flogo-bps.png&w=3840&q=75"
st.markdown(
    f"""
    <style>
    [data-testid="stToolbar"]::before {{
        content: "";
        position: absolute;
        left: 50px; top: 13px;
        width: 38px; height: 40px;
        background: url('{logo_url}') no-repeat;
        background-size: contain;
    }}
    [data-testid="stToolbar"]::after {{
        content: "BADAN PUSAT STATISTIK KABUPATEN LAMONGAN";
        position: absolute;
        left: 100px; top: 18px;
        font-size: 11px; font-weight: bold; font-style: italic;
    }}
    </style>
    """, unsafe_allow_html=True
)

# --- Login Check ---
df_login = pd.read_csv("pj.csv")
df_login["email"] = df_login["email"].str.strip().str.lower()

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.switch_page("pages/login.py")

user_email = st.session_state.user_email.lower()
user_row = df_login[df_login["email"] == user_email]
if user_row.empty:
    st.error("Akun tidak terdaftar!")
    st.stop()

user_kecamatan = user_row.iloc[0]["kecamatan"]
nama_user = user_row.iloc[0]["nama_pegawai"]

st.title("Dashboard Kecamatan - KDM")
st.write(f"**Selamat datang, {nama_user}**")
st.write(f"**Kecamatan:** {user_kecamatan}")
st.markdown("---")

# --- Load Data ---
sheet = load_sheet("PJ Kecamatan", "Sheet1")
values = sheet.get("A1:Z")
if len(values) < 2:
    st.error("Data di Google Sheet kosong!")
    st.stop()

header = values[1]
data_rows = values[2:]
df = pd.DataFrame(data_rows, columns=header)

# Clean Kecamatan column
df["Kecamatan"] = df["Kecamatan"].astype(str).str.replace(r"^\[\d+\]\s*", "", regex=True).str.strip().str.lower()
filtered_df = df[df["Kecamatan"] == user_kecamatan.lower()].copy()

if filtered_df.empty:
    st.warning("Belum ada data untuk kecamatan Anda.")
    st.stop()

# Process percentage column
persen_col = "% KDM + SWmaps vs SE2016"
filtered_df[persen_col] = filtered_df[persen_col].astype(str).str.replace("%", "").str.strip()
filtered_df["_nilai_num"] = pd.to_numeric(filtered_df[persen_col].str.replace(",", "."), errors="coerce")

def kategori(nilai):
    if pd.isna(nilai): return "Merah"
    if nilai >= 100: return "Hijau"
    elif nilai >= 70: return "Kuning"
    else: return "Merah"

filtered_df["Kategori"] = filtered_df["_nilai_num"].apply(kategori)

# Load fenomena.json
if "fenomena_data" not in st.session_state:
    with st.spinner("Memuat data fenomena..."):
        st.session_state.fenomena_data = load_fenomena_json()

# Apply existing fenomena & status
filtered_df["Fenomena"] = filtered_df["Desa"].map(
    lambda x: st.session_state.fenomena_data.get(x, {}).get("fenomena", "")
)
filtered_df["Status"] = filtered_df["Desa"].map(
    lambda x: st.session_state.fenomena_data.get(x, {}).get("status", "")
)

# --- UI ---
st.subheader("Pilih Desa untuk Input Fenomena")
desa_list = [""] + sorted(filtered_df["Desa"].dropna().unique().tolist())
selected_desa = st.selectbox("Desa:", desa_list, index=0)

# Table with color
st.subheader("Data Kecamatan Anda")
display_df = filtered_df.drop(columns=["_nilai_num"], errors="ignore")

def highlight_kategori(row):
    cat = row["Kategori"]
    color = {"Hijau": "#d4edda", "Kuning": "#fff3cd", "Merah": "#f8d7da"}.get(cat, "#ffffff")
    return [f"background-color: {color}" for _ in row]

st.dataframe(display_df.style.apply(highlight_kategori, axis=1), use_container_width=True)

# Form input fenomena
if selected_desa:
    st.markdown("---")
    st.subheader(f"Input Fenomena - {selected_desa}")
    old = st.session_state.fenomena_data.get(selected_desa, {})
    fenomena = st.text_area("Fenomena:", value=old.get("fenomena", ""), height=150)
    status = st.selectbox("Status:", [" ", "Belum Selesai", "Selesai"], 
                          index=[" ", "Belum Selesai", "Selesai"].index(old.get("status", " ")) 
                          if old.get("status") in [" ", "Belum Selesai", "Selesai"] else 0)

    if st.button("Simpan Fenomena", type="primary"):
        st.session_state.fenomena_data[selected_desa] = {
            "fenomena": fenomena.strip(),
            "status": status
        }
        try:
            save_fenomena_json(st.session_state.fenomena_data)
            st.success("Berhasil disimpan ke Google Drive!")
            st.rerun()
        except Exception as e:
            st.error("Gagal menyimpan ke Drive!")
            st.exception(e)

# Chart
st.subheader("Grafik Progres per Desa")
chart_data = filtered_df.set_index("Desa")["_nilai_num"].sort_values(ascending=True)
st.bar_chart(chart_data)

