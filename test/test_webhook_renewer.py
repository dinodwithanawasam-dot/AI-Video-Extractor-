"""
Unit tests for the Google Drive Webhook Renewer Lambda (src/webhook_renewer.py)
Tests automated 6-day renewal logic, payload creation, and Lambda handler.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

os.environ["PUBLIC_API_URL"] = "https://test-api.execute-api.us-east-1.amazonaws.com/prod"
os.environ["GDRIVE_INPUT_FOLDER_ID"] = "test_gdrive_folder_123"
os.environ["PUBLIC_WEBHOOK_TOKEN"] = "secure_token_abc"

from src.webhook_renewer import renew_webhook, lambda_handler


class TestWebhookRenewer(unittest.TestCase):

    @patch("src.utils.drive_utils.get_drive_service")
    def test_01_renew_webhook_success(self, mock_get_service):
        """Test renew_webhook generates valid channel ID and watch parameters."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        mock_watch = mock_service.files().watch
        mock_watch.return_value.execute.return_value = {
            "id": "mock_channel_uuid_123",
            "expiration": "1726050000000"
        }

        result = renew_webhook()
        self.assertEqual(result.get("id"), "mock_channel_uuid_123")
        self.assertEqual(result.get("expiration"), "1726050000000")

        # Verify arguments sent to Google Drive API
        mock_watch.assert_called_once()
        call_kwargs = mock_watch.call_args[1]
        self.assertEqual(call_kwargs["fileId"], "test_gdrive_folder_123")
        
        body = call_kwargs["body"]
        self.assertEqual(body["type"], "web_hook")
        self.assertEqual(body["address"], "https://test-api.execute-api.us-east-1.amazonaws.com/prod/webhook/drive")
        self.assertEqual(body["token"], "secure_token_abc")
        self.assertTrue(int(body["expiration"]) > 0)
        print("  [PASS] renew_webhook correctly formats and executes Google Drive watch request")

    def test_02_renew_webhook_missing_url(self):
        """Test renew_webhook raises ValueError if PUBLIC_API_URL is missing."""
        with patch.dict(os.environ, {"PUBLIC_API_URL": ""}):
            with self.assertRaises(ValueError) as ctx:
                renew_webhook()
            self.assertIn("PUBLIC_API_URL environment variable is not set", str(ctx.exception))
        print("  [PASS] renew_webhook strictly validates presence of PUBLIC_API_URL")

    @patch("src.webhook_renewer.renew_webhook")
    def test_03_lambda_handler_execution(self, mock_renew):
        """Test Lambda entry point called by EventBridge Scheduler."""
        mock_renew.return_value = {
            "id": "new_channel_777",
            "expiration": "1726050000000"
        }

        event = {"source": "aws.scheduler"}
        context = MagicMock()

        response = lambda_handler(event, context)
        self.assertEqual(response["status"], "renewed")
        self.assertEqual(response["channel_id"], "new_channel_777")
        print("  [PASS] lambda_handler handles EventBridge Scheduler trigger successfully")


if __name__ == "__main__":
    unittest.main()
