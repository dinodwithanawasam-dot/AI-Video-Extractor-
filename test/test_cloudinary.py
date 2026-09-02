import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

# Load env variables
load_dotenv()

# Configure Cloudinary
cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key    = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET"),
    secure     = True
)

def test_upload():
    print("Testing Cloudinary Upload and Folder Creation...")
    
    # 1. Create a dummy test file
    test_file_path = "test_upload.txt"
    with open(test_file_path, "w") as f:
        f.write("This is a test file to check if folders are created correctly in Cloudinary.")
    
    # 2. Define test folder structure
    test_folder = "test_user_gmail_com/test_video_12345"
    print(f"Target Folder: {test_folder}")
    
    try:
        # 3. Upload to Cloudinary with explicit folder parameter
        print(f"Uploading {test_file_path} to Cloudinary...")
        result = cloudinary.uploader.upload(
            test_file_path,
            resource_type = "raw",
            folder        = test_folder,
            public_id     = "test_upload", # filename without extension
            overwrite     = True,
        )
        
        secure_url = result.get("secure_url", "")
        print(f"\n[SUCCESS] Upload Successful!")
        print(f"File URL: {secure_url}")
        print(f"\n[INFO] Now go check your Cloudinary Media Library.")
        print(f"You should see: test_user_gmail_com -> test_video_12345 -> test_upload.txt")
        
    except Exception as e:
        print(f"\n[ERROR] Upload Failed: {e}")
        
    finally:
        # Clean up local dummy file
        if os.path.exists(test_file_path):
            os.remove(test_file_path)

if __name__ == "__main__":
    test_upload()
