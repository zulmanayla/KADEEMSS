import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import json
import io
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===========================================================
#                  FOLDER GOOGLE DRIVE
# ===========================================================
FOLDER_ID = "1mkUYxy16XNTmhV4uy-DXo5le6oMyvPHs"


# ===========================================================
#                 GOOGLE AUTH VIA STREAMLIT SECRETS
# ===========================================================
def get_credentials(scopes):
    """Membuat credentials dari st.secrets."""
    cred_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(cred_dict, scopes=scopes)
    return creds


def create_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = get_credentials(scopes)
    client = gspread.Client(auth=creds)

    retry = Retry(total=5, connect=5, read=5, backoff_factor=1)
    adapter = HTTPAdapter(max_retries=retry)
    client.session.mount("https://", adapter)

    return client


def init_drive():
    scopes = ["https://www.googleapis.com/auth/drive"]
    creds = get_credentials(scopes)
    return build("drive", "v3", credentials=creds)


# ===========================================================
#                 LOAD SHEETS via SECRETS
# ===========================================================

@st.cache_resource
def load_sheet():
    client = create_gspread_client()
    sheet = client.open("PJ Kecamatan").worksheet("Sheet1")
    return sheet


# ===========================================================
#            LOAD & SAVE fenomena.json di Google Drive
# ===========================================================
def get_file_id(name):
    drive = init_drive()
    query = f"name='{name}' and '{FOLDER_ID}' in parents"
    result = drive.files().list(q=query).execute()
    files = result.get("files", [])
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
    file_id = get_file_id("fenomena.json")
    drive = init_drive()

    temp_path = "fenomena_temp.json"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    media = MediaFileUpload(temp_path, mimetype="application/json")

    if file_id:
        drive.files().update(fileId=file_id, media_body=media).execute()
    else:
        metadata = {
            "name": "fenomena.json",
            "parents": [FOLDER_ID],
            "mimeType": "application/json"
        }
        drive.files().create(body=metadata, media_body=media).execute()


# ===========================================================
#                 STREAMLIT PAGE CONFIG & HEADER
# ===========================================================
st.set_page_config(
    page_title="Dashboard",
    page_icon="https://lamongankab.bps.go.id/_next/image?url=%2Fassets%2Flogo-bps.png&w=3840&q=75",
    layout="wide"
)

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


# ===========================================================
#                 LOGIN VALIDATION
# ===========================================================
df_login = pd.read_csv("pj.csv")
df_login["email"] = df_login["email"].str.strip().str.lower()

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.switch_page("pages/login.py")

user_email = st.session_state.user_email.lower()
user_row = df_login[df_login["email"] == user_email]

if user_row.empty:
    st.error("Akun tidak ada di data login.")
    st.stop()

user_kecamatan = user_row.iloc[0]["kecamatan"]
nama_user = user_row.iloc[0]["nama_pegawai"]


# ===========================================================
#                    HEADER USER
# ===========================================================
st.title("📊 Dashboard Kecamatan")
st.write(f"**Selamat Datang:** {nama_user}")
st.write(f"**Anda bertugas di Kecamatan:** {user_kecamatan}")
st.markdown("---")


# ===========================================================
#               LOAD DATA DARI GOOGLE SHEETS
# ===========================================================
sheet = load_sheet()
values = sheet.get("A1:Z")

header = values[1]
rows = values[2:]
df = pd.DataFrame(rows, columns=header)

df["Kecamatan"] = (
    df["Kecamatan"]
    .astype(str)
    .str.replace(r"^\[\d+\]\s*", "", regex=True)
    .str.strip()
    .str.lower()
)

filtered_df = df[df["Kecamatan"] == user_kecamatan.lower()].copy()

if filtered_df.empty:
    st.warning("Tidak ada data untuk kecamatan Anda.")
    st.stop()


# ===========================================================
#                  KONVERSI PERSEN & KATEGORI
# ===========================================================
persen_col = "% KDM + SWmaps vs SE2016"

filtered_df[persen_col] = (
    filtered_df[persen_col]
    .astype(str)
    .str.strip()
    .apply(lambda x: x if x.endswith("%") else f"{x}%")
)

filtered_df["_nilai_num"] = (
    filtered_df[persen_col]
    .str.replace("%", "")
    .str.replace(",", ".")
    .astype(float)
)


def kategori(x):
    if x >= 100:
        return "Hijau"
    elif x >= 70:
        return "Kuning"
    else:
        return "Merah"


filtered_df["Kategori"] = filtered_df["_nilai_num"].apply(kategori)


# ===========================================================
#           LOAD FENOMENA DATA DARI GOOGLE DRIVE
# ===========================================================
if "fenomena_data" not in st.session_state:
    st.session_state.fenomena_data = load_fenomena_json()

filtered_df["Fenomena"] = ""
filtered_df["Status"] = ""

for desa, obj in st.session_state.fenomena_data.items():
    filtered_df.loc[filtered_df["Desa"] == desa, "Fenomena"] = obj.get("fenomena", "")
    filtered_df.loc[filtered_df["Desa"] == desa, "Status"] = obj.get("status", "")


# ===========================================================
#           DROPDOWN DESA — FORM INPUT FENOMENA
# ===========================================================
st.subheader("Pilih Desa untuk Input Fenomena")

desa_list = filtered_df["Desa"].unique()
selected_desa = st.selectbox("Pilih Desa:", [""] + list(desa_list))


# ===========================================================
#                  TABEL (SELALU MUNCUL)
# ===========================================================
st.subheader("📁 Data Kecamatan")

df_display = filtered_df.drop(columns=["Kategori", "_nilai_num"], errors="ignore")


def highlight_rows(row):
    kategori_val = filtered_df.loc[row.name, "Kategori"]
    if kategori_val == "Hijau":
        return ["background-color: #b7f7b7"] * len(row)
    elif kategori_val == "Kuning":
        return ["background-color: #fff3b0"] * len(row)
    else:
        return ["background-color: #ffb3b3"] * len(row)


st.dataframe(df_display.style.apply(highlight_rows, axis=1), use_container_width=True)


# ===========================================================
#          FORM FENOMENA (HILANGKAN GRAFIK SAAT DIPILIH)
# ===========================================================
if selected_desa:

    st.markdown("---")
    st.subheader(f"Input Fenomena & Status: {selected_desa}")

    fenomena_lama = st.session_state.fenomena_data.get(selected_desa, {}).get("fenomena", "")
    status_lama = st.session_state.fenomena_data.get(selected_desa, {}).get("status", "")

    fenomena_input = st.text_area("Tuliskan fenomena:", value=fenomena_lama)

    status_options = [" ", "Selesai", "Belum Selesai"]

    status_input = st.selectbox(
        "Pilih Status:",
        status_options,
        index=status_options.index(status_lama) if status_lama in status_options else 0
    )

    if st.button("💾 Simpan"):
        st.session_state.fenomena_data[selected_desa] = {
            "fenomena": fenomena_input,
            "status": status_input,
        }
        save_fenomena_json(st.session_state.fenomena_data)
        st.success("Data berhasil disimpan!")
        st.rerun()

    st.stop()


# ===========================================================
#                     GRAFIK BAR
# ===========================================================
st.subheader("📈 Grafik Progres (%)")

chart_df = filtered_df[["Desa", "_nilai_num"]].set_index("Desa")
st.bar_chart(chart_df)
