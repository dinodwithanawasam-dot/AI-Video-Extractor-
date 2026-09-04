"""
Unit tests for DynamoDB operations in src/utils/db_utils.py.
Tests float-to-decimal conversion, record persistence, and querying via ByDateIndex.
"""
import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.utils.db_utils import _convert_floats, save_video_record, get_all_videos


class TestDynamoDBUtils(unittest.TestCase):

    def test_01_convert_floats_to_decimal(self):
        """Verify float values in nested dicts/lists are converted to Decimal."""
        sample_data = {
            "title": "Sample Reel",
            "score": 0.985,
            "timestamps": [12.5, 45.0],
            "nested": {
                "confidence": 0.88,
                "label": "AI"
            }
        }
        converted = _convert_floats(sample_data)
        self.assertIsInstance(converted["score"], Decimal)
        self.assertEqual(converted["score"], Decimal("0.985"))
        self.assertIsInstance(converted["timestamps"][0], Decimal)
        self.assertIsInstance(converted["nested"]["confidence"], Decimal)
        print("  [PASS] _convert_floats recursively converts all floats to Decimal")

    @patch("src.utils.db_utils.get_dynamodb_resource")
    def test_02_save_video_record(self, mock_get_resource):
        """Verify save_video_record injects record_type='video' and calls put_item."""
        mock_dynamo = MagicMock()
        mock_get_resource.return_value = mock_dynamo
        mock_table = MagicMock()
        mock_dynamo.Table.return_value = mock_table

        record = {
            "video_id": "test_vid_123",
            "main_title": "Test Title",
            "summary": "Test Summary",
            "status": "success",
            "created_at": "2026-09-04T10:00:00Z",
            "score": 0.95
        }

        success = save_video_record(record)
        self.assertTrue(success)
        mock_table.put_item.assert_called_once()
        
        saved_item = mock_table.put_item.call_args[1]["Item"]
        self.assertEqual(saved_item["record_type"], "video")
        self.assertEqual(saved_item["video_id"], "test_vid_123")
        self.assertIsInstance(saved_item["score"], Decimal)
        print("  [PASS] save_video_record formats and persists record to DynamoDB table")

    @patch("src.utils.db_utils.get_dynamodb_resource")
    def test_03_get_all_videos(self, mock_get_resource):
        """Verify get_all_videos queries ByDateIndex with descending sort."""
        mock_dynamo = MagicMock()
        mock_get_resource.return_value = mock_dynamo
        mock_table = MagicMock()
        mock_dynamo.Table.return_value = mock_table

        mock_table.query.return_value = {
            "Items": [{"video_id": "vid_1"}, {"video_id": "vid_2"}]
        }

        videos = get_all_videos(limit=10)
        self.assertEqual(len(videos), 2)
        mock_table.query.assert_called_once()
        query_kwargs = mock_table.query.call_args[1]
        self.assertEqual(query_kwargs["IndexName"], "ByDateIndex")
        self.assertFalse(query_kwargs["ScanIndexForward"])  # Descending order
        print("  [PASS] get_all_videos queries ByDateIndex in descending order")


if __name__ == "__main__":
    unittest.main()
