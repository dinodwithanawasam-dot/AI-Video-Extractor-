import os
import boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal
import sys
import datetime
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(ROOT_DIR))

from log import get_logger

logger = get_logger(__name__)
load_dotenv(ROOT_DIR / ".env")

TABLE_NAME = "Flipline_Videos"

def _convert_floats(obj):
    """Recursively convert all float values to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: _convert_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_floats(i) for i in obj]
    return obj

def get_dynamodb_resource():
    """Initializes and returns the DynamoDB resource using environment credentials."""
    try:
        dynamodb = boto3.resource(
            'dynamodb',
            region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        return dynamodb
    except Exception as e:
        logger.error(f"Failed to initialize DynamoDB resource: {e}")
        return None

def save_video_record(record: dict) -> bool:
    """
    Saves a processed video record into DynamoDB.
    Expected keys: video_id, created_at, status, main_title, summary, article_path,
    denoised_video, denoised_audio, highlights, reels.
    """
    dynamodb = get_dynamodb_resource()
    if not dynamodb:
        return False
        
    try:
        table = dynamodb.Table(TABLE_NAME)
        
        # Ensure the record has the GSI partition key
        record["record_type"] = "video"

        # DynamoDB does not support Python float — convert all floats to Decimal
        record = _convert_floats(record)
        
        table.put_item(Item=record)
        logger.info(f"Successfully saved record for video_id: {record.get('video_id')} to DynamoDB.")
        return True
    except Exception as e:
        logger.error(f"Error saving record to DynamoDB: {e}", exc_info=True)
        return False

def get_all_videos(limit: int = 50) -> list:
    """
    Fetches the latest videos from DynamoDB using the ByDateIndex, 
    sorted from newest to oldest.
    """
    dynamodb = get_dynamodb_resource()
    if not dynamodb:
        return []

    try:
        table = dynamodb.Table(TABLE_NAME)
        response = table.query(
            IndexName='ByDateIndex',
            KeyConditionExpression=Key('record_type').eq('video'),
            ScanIndexForward=False, # False = Descending order (newest first)
            Limit=limit
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error fetching videos from DynamoDB: {e}")
        return []
