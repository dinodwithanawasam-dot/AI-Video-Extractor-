import yaml
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Define project root and config path
ROOT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = ROOT_DIR / "config" / "params.yaml"

def load_config():
    """Load configuration from params.yaml"""
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Config file not found at: {CONFIG_FILE}")
        
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f)

# Global CONFIG dictionary
CONFIG = load_config()

# Helper accessors
LLM_CONFIG = CONFIG.get("llm", {})
WHISPER_CONFIG = CONFIG.get("whisper", {})
VIDEO_CONFIG = CONFIG.get("video", {})
PATHS_CONFIG = CONFIG.get("paths", {})

# Auto-create necessary directories based on config
os.makedirs(ROOT_DIR / PATHS_CONFIG.get("input_dir", "data/input"), exist_ok=True)
os.makedirs(ROOT_DIR / PATHS_CONFIG.get("output_dir", "data/output"), exist_ok=True)
os.makedirs(ROOT_DIR / PATHS_CONFIG.get("temp_dir", "data/temp"), exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
