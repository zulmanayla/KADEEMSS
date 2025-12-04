# pages/dashboards kdm.py
import streamlit as st
import pandas as pd
import gspread
import json
import io
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# -----------------------------
# CONFIG
# -----------------------------
FOLDER_ID = "1mkUYxy16XNTmhV4uy-DXo5le6oMyvPHs"

# -----------------------------
# Credentials
# -----------------------------
def get_credentials(scopes):
    creds_dict = st.secrets["google_credentials"]
    return Credentials.from_service_account_info(creds_dict, scopes=scopes)

def create_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = get_credentials(scopes)
    client = gspread.authorize(creds)
    return client

def init_drive():
    scopes = ["https://www.googleapis.com/auth/drive"]
    creds = get_credentials(scopes)
    return build("drive", "v3", credentials=creds)

# -----------------------------
# Load Sheet
# -----------------------------
@st.cache_resource(ttl=300)
def load_sheet(spreadsheet_name="PJ Kecamatan", worksheet_name="Sheet1"):
    try:
        client = create_gspread_client()
        return client.open(spreadsheet_name).worksheet(worksheet_name)
    except Exception as e:
        st.error("Gagal membuka Google Sheet. Pastikan service account sudah di-share!")
        st.exception(e)
        st.stop()

# -----------------------------
# Fenomena.json
# -----------------------------
def get_file_id(name):
    drive = init_drive()
    query = f"name='{name}' and '{FOLDER_ID}' in parents and trashed=false"
    resp = drive.files().list(q=query, fields="files(id)").execute()
    files = resp.get("files", [])
    return files[0]["id"] if files else None

def load_fenomena_json():
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

def save_fenomena_json(data):
    drive = init_drive()
    file_id = get_file_id("fenomena.json")
    temp_file = "temp_fenomena.json"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    media = MediaFileUpload(temp_file, mimetype="application/json")
    if file_id:
        drive.files().update(fileId=file_id, media_body=media).execute()
    else:
        drive.files().create(body={"name": "fenomena.json", "parents": [FOLDER_ID]}, media_body=media).execute()

# -----------------------------
# MAIN APP
# -----------------------------
st.set_page_config(page_title="Dashboard KDM", page_icon="📊", layout="wide")

# BERSIHKAN HEADER
logo_url = "https://lamongankab.bps.go.id/_next/image?url=%2Fassets%2Flogo-bps.png&w=3840&q=75"
st.markdown(
    f"""
    <style>
        [data-testid="stHeader"] {{ background: transparent !important; }}
        [data-testid="stToolbar"]::before {{
            content: "";
            display: flex;
            position: absolute;
            left: 50px;
            top: 13px;
            width: 240px;
            height: 40px;
            background-image: url('{logo_url}');
            background-repeat: no-repeat;
            background-size: 38px;
            padding-left: 45px;
        }}
        [data-testid="stToolbar"]::after {{
            content: "BADAN PUSAT STATISTIK \\A KABUPATEN LAMONGAN";
            white-space: pre;
            position: absolute;
            top: 13px;
            left: 92px;
            font-size: 11px;
            font-weight: bold;
            font-style: italic;
        }}
    </style>
    """,
    unsafe_allow_html=True
)


# Login check
df_login = pd.read_csv("pj.csv")
df_login["email"] = df_login["email"].str.strip().str.lower()

if not st.session_state.get("logged_in"):
    st.switch_page("pages/login.py")

user_email = st.session_state.user_email.lower()
user_row = df_login[df_login["email"] == user_email]
if user_row.empty:
    st.error("Akun tidak terdaftar!")
    st.stop()

user_kecamatan = user_row.iloc[0]["kecamatan"]
nama_user = user_row.iloc[0]["nama_pegawai"]

st.title("📊 Dashboard Kecamatan - KDM")
st.write(f"**Selamat datang, {nama_user}** | Kecamatan: **{user_kecamatan}**")
st.markdown("---")

# Load data
sheet = load_sheet()
values = sheet.get("A1:Z")
if len(values) < 2:
    st.error("Sheet kosong!")
    st.stop()

header = values[1]
df = pd.DataFrame(values[2:], columns=header)

df["Kecamatan"] = df["Kecamatan"].astype(str).str.replace(r"^\[\d+\]\s*", "", regex=True).str.strip().str.lower()
filtered_df = df[df["Kecamatan"] == user_kecamatan.lower()].copy()

if filtered_df.empty:
    st.warning("Belum ada data untuk kecamatan Anda.")
    st.stop()

# Hitung kategori
col = "% KDM + SWmaps vs SE2016"
filtered_df["_nilai"] = pd.to_numeric(
    filtered_df[col].astype(str).str.replace("[%,]", "", regex=True).str.replace(",", "."),
    errors="coerce"
)

def get_kategori(x):
    if pd.isna(x): return "Merah"
    return "Hijau" if x >= 100 else "Kuning" if x >= 70 else "Merah"

filtered_df["Kategori"] = filtered_df["_nilai"].apply(get_kategori)

# Load fenomena
if "fenomena_data" not in st.session_state:
    st.session_state.fenomena_data = load_fenomena_json()

filtered_df["Fenomena"] = filtered_df["Desa"].map(lambda x: st.session_state.fenomena_data.get(x, {}).get("fenomena", ""))
filtered_df["Status"] = filtered_df["Desa"].map(lambda x: st.session_state.fenomena_data.get(x, {}).get("status", ""))

# UI desa
st.subheader("Pilih Desa")
desa_list = [""] + sorted(filtered_df["Desa"].dropna().unique())
selected_desa = st.selectbox("Desa:", desa_list)

def color_row(row):
    # Ambil kategori berdasarkan index baris
    kategori = filtered_df.loc[row.name, "Kategori"]
    color = {"Hijau": "#d4edda", "Kuning": "#fff3cd", "Merah": "#f8d7da"}.get(kategori, "#ffffff")
    return [f"background-color: {color}"] * len(row)


st.subheader("Data Kecamatan Anda")

# -----------------------------
# 🔥 BAGIAN YANG ANDA MINTA:
# Sembunyikan kolom “Kategori”
# -----------------------------
table_df = filtered_df.drop(columns=["_nilai", "Kategori"], errors="ignore")

st.dataframe(table_df.style.apply(color_row, axis=1), use_container_width=True)

# Form input fenomena
if selected_desa:
    st.markdown("---")
    st.subheader(f"Fenomena - {selected_desa}")
    old = st.session_state.fenomena_data.get(selected_desa, {})

    fenomena = st.text_area("Fenomena:", value=old.get("fenomena", ""), height=120)
    status_options = [" ", "Belum Selesai", "Selesai"]
    current_status = old.get("status", " ")
    status_index = status_options.index(current_status) if current_status in status_options else 0
    status = st.selectbox("Status:", status_options, index=status_index)

    if st.button("Simpan", type="primary"):
        st.session_state.fenomena_data[selected_desa] = {
            "fenomena": fenomena.strip(),
            "status": status
        }
        try:
            save_fenomena_json(st.session_state.fenomena_data)
            st.success("Berhasil disimpan!")
            st.rerun()
        except Exception as e:
            st.error("Gagal menyimpan!")
            st.exception(e)

# Chart
st.subheader("Grafik Progres")
chart_data = filtered_df.set_index("Desa")["_nilai"]
st.bar_chart(chart_data)
