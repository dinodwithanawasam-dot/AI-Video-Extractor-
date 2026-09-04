import os
import sys
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CREDENTIALS_FILE = 'credentials.json'

def validate_credentials():
    print("Testing credentials...")
    try:
        if not os.path.exists(CREDENTIALS_FILE):
            print(f"Error: {CREDENTIALS_FILE} not found.")
            return

        credentials = service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE, scopes=SCOPES
        )
        
        # Build the Drive service
        service = build('drive', 'v3', credentials=credentials)
        
        # Attempt to list files (max 1) just to verify auth works
        results = service.files().list(
            pageSize=1, fields="files(id, name)"
        ).execute()
        
        print("\n✅ SUCCESS: Authentication passed!")
        print("Successfully generated access token and called Google Drive API.")
        
        items = results.get('files', [])
        if items:
            print(f"Found {len(items)} file(s). Example file: {items[0]['name']}")
        else:
            print("No files found in the drive (but auth was successful).")
            
    except Exception as e:
        print(f"\n❌ FAILED: JWT or Authentication issue detected.")
        print(f"Error details: {e}")

if __name__ == '__main__':
    validate_credentials()
