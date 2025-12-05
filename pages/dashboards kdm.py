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

# -----------------------------
# Load Sheet PJ Kecamatan
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
# Load Sheet Fenomena
# -----------------------------
def load_fenomena_sheet():
    try:
        client = create_gspread_client()
        ws = client.open("Fenomena").sheet1

        data = ws.get_all_records()
        if not data:
            # Sheet kosong → buat dataframe standar
            df = pd.DataFrame(columns=["Kecamatan", "Desa", "Fenomena", "Status"])
            return df, ws

        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()

        # Pastikan semua kolom ada
        required_cols = ["Kecamatan", "Desa", "Fenomena", "Status"]
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""

        df["Kecamatan"] = df["Kecamatan"].astype(str).str.strip()
        df["Desa"] = df["Desa"].astype(str).str.strip()
        df["Fenomena"] = df["Fenomena"].astype(str).str.strip()
        df["Status"] = df["Status"].astype(str).str.strip()

        return df, ws

    except Exception as e:
        st.error("Gagal memuat Sheet Fenomena. Pastikan spreadsheet bernama 'Fenomena'.")
        st.exception(e)
        st.stop()
# -----------------------------
# MAIN APP
# -----------------------------
st.set_page_config(page_title="Dashboard KDM", page_icon="📊", layout="wide")

# Header
logo_url = "https://lamongankab.bps.go.id/_next/image?url=%2Fassets%2Flogo-bps.png&w=3840&q=75"
st.markdown(
    f"""
    <style>
      
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
            top: 15px;
            left: 92px;
            font-size: 11px;
            font-weight: bold;
            font-style: italic;
            line-height: 10px;
        }}
    </style>
    """,
    unsafe_allow_html=True
)

# Login
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
st.write(f"**Selamat Datang:** {nama_user}")
st.write(f"**Anda bertugas di Kecamatan:** {user_kecamatan}")
st.markdown("---")

# Load data PJ Kecamatan
sheet = load_sheet()
values = sheet.get_all_values()
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

# Load fenomena sheet
fenomena_df, fenomena_ws = load_fenomena_sheet()

# Normalisasi sebelum merge
filtered_df["Desa"] = filtered_df["Desa"].astype(str).str.strip()
fenomena_df["Desa"] = fenomena_df["Desa"].astype(str).str.strip()

filtered_df = filtered_df.merge(
    fenomena_df[["Desa", "Fenomena", "Status"]],
    how="left",
    on="Desa"
)
# Tambahkan kembali kolom Kecamatan dari user, bukan dari fenomena_df
if "Kecamatan" in filtered_df.columns:
    filtered_df.drop(columns=["Kecamatan"], inplace=True)

filtered_df.insert(0, "Kecamatan", user_kecamatan.title())
for col in ["Fenomena", "Status"]:
    filtered_df[col] = filtered_df[col].fillna("").replace("nan", "")


# Dropdown desa
st.subheader("Pilih Desa")
desa_list = [""] + sorted(filtered_df["Desa"].dropna().unique())
selected_desa = st.selectbox("Desa:", desa_list)

# Warna baris berdasarkan kategori
def color_row(row):
    kategori = filtered_df.loc[row.name, "Kategori"]
    color = {"Hijau": "#d4edda", "Kuning": "#fff3cd", "Merah": "#f8d7da"}.get(kategori, "#ffffff")
    return [f"background-color: {color}"] * len(row)

st.subheader("Data Kecamatan Anda")

# Tampilkan tabel (tanpa kolom kategori & nilai)
table_df = filtered_df.drop(columns=["_nilai", "Kategori"], errors="ignore")

st.dataframe(table_df.style.apply(color_row, axis=1), use_container_width=True)

# Form input fenomena
if selected_desa:
    st.markdown("---")
    st.subheader(f"Fenomena - {selected_desa}")

    old_row = fenomena_df[fenomena_df["Desa"] == selected_desa]
    old_fenomena = old_row["Fenomena"].iloc[0] if not old_row.empty else ""
    old_status = old_row["Status"].iloc[0] if not old_row.empty else ""

    fenomena = st.text_area("Fenomena:", value=old_fenomena, height=120)
    # Ambil semua nilai status unik dari sheet
    raw_status_options = sorted(fenomena_df["Status"].dropna().unique())
    fenomena = st.text_area("Fenomena:", value=old_fenomena, height=120)
    status_options = [" ", "Belum Selesai", "Selesai"]
    status_index = status_options.index(old_status) if old_status in status_options else 0
    status = st.selectbox("Status:", status_options, index=status_index)



    if st.button("Simpan", type="primary"):
        cell = fenomena_ws.find(selected_desa)

        if cell:
            fenomena_ws.update_cell(cell.row, 1, user_kecamatan)
            fenomena_ws.update_cell(cell.row, 2, selected_desa)
            fenomena_ws.update_cell(cell.row, 3, fenomena)
            fenomena_ws.update_cell(cell.row, 4, status)
        else:
            fenomena_ws.append_row([user_kecamatan, selected_desa, fenomena, status])

        st.success("Data berhasil disimpan!")
        st.rerun()


# Grafik
st.subheader("Grafik Progres")
chart_data = filtered_df.set_index("Desa")["_nilai"]
st.bar_chart(chart_data)
