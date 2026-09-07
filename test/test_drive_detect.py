import os
import sys
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

sys.path.append(".")
from src.utils.drive_utils import get_drive_service
service = get_drive_service()
input_folder_id = os.getenv("GDRIVE_INPUT_FOLDER_ID")

res = service.files().list(
    q=f"'{input_folder_id}' in parents and trashed=false",
    supportsAllDrives=True,
    includeItemsFromAllDrives=True,
    fields="files(id, name, mimeType)",
    pageSize=5
).execute()

files = res.get("files", [])
print(f"Files discovered: {len(files)}")
for f in files:
    print(f"  - Name: {f.get('name')} (ID: {f.get('id')}) | Mime: {f.get('mimeType')}")
