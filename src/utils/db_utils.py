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

TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "Flipline_Videos")

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
        region = os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION", "us-east-1")
        # When running inside AWS Lambda, boto3 automatically uses the IAM execution role and temporary STS tokens
        if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
            return boto3.resource('dynamodb', region_name=region)

        kwargs = {"region_name": region}
        ak = os.getenv("AWS_ACCESS_KEY_ID")
        sk = os.getenv("AWS_SECRET_ACCESS_KEY")
        st = os.getenv("AWS_SESSION_TOKEN")
        if ak and sk:
            kwargs["aws_access_key_id"] = ak
            kwargs["aws_secret_access_key"] = sk
            if st:
                kwargs["aws_session_token"] = st
        return boto3.resource('dynamodb', **kwargs)
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

def get_all_videos(limit: int = 50, approved_only: bool = True) -> list:
    """
    Fetches the latest videos from DynamoDB using the ByDateIndex, 
    sorted from newest to oldest.
    If approved_only is True:
      - Excludes unapproved videos.
      - Filters each video's reels list to only include approved reels.
      - Hides unapproved highlights.
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
        items = response.get('Items', [])
        if approved_only:
            filtered_items = []
            for item in items:
                is_fliplong = item.get('is_fliplong') is True or item.get('source') == 'fliplong'

                # ── RULE 1: Watchroom / Drive Videos (is_fliplong == False) ──
                # Auto reels, highlights OKKOMA approved! Direct pass to feed.
                if not is_fliplong:
                    filtered_items.append(item)
                    continue

                # ── RULE 2: FlipLONG Videos (is_fliplong == True) ──
                # Check which specific reels/highlights are approved:
                if item.get('is_approved') is not True:
                    continue

                reels = item.get('reels', [])
                # Only keep reels that the user specifically approved
                approved_reels = [r for r in reels if r.get('is_approved') is True]
                item['reels'] = approved_reels

                highlights = item.get('highlights', {})
                # Only keep highlights if specifically approved
                if isinstance(highlights, dict) and highlights.get('is_approved') is not True:
                    item['highlights'] = {}

                # If no approved reels or highlights remain, skip this FlipLONG item
                if not approved_reels and not item.get('highlights'):
                    continue

                filtered_items.append(item)
            return filtered_items
        return items
    except Exception as e:
        logger.error(f"Error fetching videos from DynamoDB: {e}")
        return []


def get_video_by_id(video_id: str) -> dict | None:
    """
    Fetches a single video record from DynamoDB by its primary key (video_id).
    video_id corresponds to the Google Drive file_id.
    """
    dynamodb = get_dynamodb_resource()
    if not dynamodb:
        return None

    try:
        table = dynamodb.Table(TABLE_NAME)
        response = table.get_item(Key={'video_id': video_id})
        return response.get('Item')
    except Exception as e:
        logger.error(f"Error fetching video {video_id} from DynamoDB: {e}")
        return None


def approve_video(
    video_id: str, 
    approved: bool = True, 
    reel_index: int = None, 
    reel_indices: list = None,
    approve_highlights: bool = None
) -> dict | None:
    """
    Updates the approval status of a video, individual reels, and highlights in DynamoDB.
    - If reel_index is provided: updates is_approved for that specific reel.
    - If reel_indices is provided: multi-select updates is_approved for specified indices.
    - If approve_highlights is provided: updates is_approved for highlights.
    - If no specific media specified: updates is_approved for all reels, highlights, and the video.
    Returns dict with updated video metadata or None on error.
    """
    dynamodb = get_dynamodb_resource()
    if not dynamodb:
        return None

    try:
        table = dynamodb.Table(TABLE_NAME)
        resp = table.get_item(Key={'video_id': video_id})
        item = resp.get('Item')
        if not item:
            return None

        reels = item.get('reels', [])
        highlights = item.get('highlights', {})
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

        # 1. Update Reels
        if reel_index is not None:
            if 0 <= reel_index < len(reels):
                reels[reel_index]['is_approved'] = approved
        elif reel_indices is not None:
            idx_set = set(reel_indices)
            for idx, r in enumerate(reels):
                r['is_approved'] = (idx in idx_set)
        elif approve_highlights is None:
            for r in reels:
                r['is_approved'] = approved

        # 2. Update Highlights
        if approve_highlights is not None and isinstance(highlights, dict):
            highlights['is_approved'] = approve_highlights
        elif reel_index is None and reel_indices is None and isinstance(highlights, dict):
            highlights['is_approved'] = approved

        # 3. Determine Parent Approval
        has_approved_reel = any(r.get('is_approved') is True for r in reels)
        has_approved_highlight = highlights.get('is_approved') is True if isinstance(highlights, dict) else False
        has_any_approved = has_approved_reel or has_approved_highlight or approved

        table.update_item(
            Key={'video_id': video_id},
            UpdateExpression="SET is_approved = :app, approved_at = :at, reels = :reels, highlights = :hl REMOVE approval_status",
            ExpressionAttributeValues={
                ":app": has_any_approved,
                ":at": now,
                ":reels": _convert_floats(reels),
                ":hl": _convert_floats(highlights)
            }
        )
        logger.info(f"Video {video_id} approval updated: has_any_approved={has_any_approved}")
        return {
            "video_id": video_id,
            "is_approved": has_any_approved,
            "reels": reels,
            "highlights": highlights
        }
    except Exception as e:
        logger.error(f"Error updating approval for {video_id}: {e}", exc_info=True)
        return None

