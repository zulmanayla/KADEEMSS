from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = r"D:/Naya Geming/LOL/google_cred.json"

# Load creds
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
print("CREDENTIAL OK")

# Build Drive client
drive = build("drive", "v3", credentials=creds)
print("DRIVE CONNECT OK")

# List files (first 200)
result = drive.files().list(
    pageSize=200,
    fields="files(id, name, parents, mimeType)"
).execute()

files = result.get("files", [])

print("=== FILES FOUND ===")
for f in files:
    print(f)
