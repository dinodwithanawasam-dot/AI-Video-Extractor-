"""
Unit and integration tests for FastAPI server and Mangum Lambda handler in api.py.
"""
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Set test environment variables only if not already provided
os.environ.setdefault("PUBLIC_WEBHOOK_TOKEN", "test_secret_token_123")
os.environ.setdefault("GDRIVE_INPUT_FOLDER_ID", "test_folder_abc")
os.environ.setdefault("AWS_SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123456789012/Flipline_Jobs")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

from fastapi.testclient import TestClient
from api import app, lambda_handler


class TestApiEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=True)

    def test_01_health_check(self):
        """Test GET /health returns ok or starting status."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("whisper_model_loaded", data)
        print("  [PASS] GET /health responded with 200 OK")

    def test_02_webhook_verification_valid_token(self):
        """Test GET /webhook/drive with matching token returns 200 and token text."""
        token = os.getenv("PUBLIC_WEBHOOK_TOKEN") or "test_secret_token_123"
        response = self.client.get(f"/webhook/drive?token={token}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, token)
        print("  [PASS] GET /webhook/drive with valid token verified")

    def test_03_webhook_verification_invalid_token(self):
        """Test GET /webhook/drive with invalid token returns 403 Forbidden."""
        response = self.client.get("/webhook/drive?token=wrong_token")
        self.assertEqual(response.status_code, 403)
        self.assertIn("Invalid token", response.json().get("detail", ""))
        print("  [PASS] GET /webhook/drive with invalid token correctly rejected (403)")

    def test_04_webhook_receive_ignored_state(self):
        """Test POST /webhook/drive ignores non-add/update states (e.g. sync)."""
        headers = {"X-Goog-Resource-State": "sync"}
        response = self.client.post("/webhook/drive", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "ignored")
        self.assertEqual(data.get("state"), "sync")
        print("  [PASS] POST /webhook/drive correctly ignores sync handshake")

    @patch("api._sqs.send_message")
    @patch("src.utils.drive_utils.get_drive_service")
    def test_05_webhook_receive_video_added(self, mock_drive_service, mock_sqs_send):
        """Test POST /webhook/drive detects a video file and sends message to SQS."""
        mock_service = MagicMock()
        mock_drive_service.return_value = mock_service
        
        # Mock Google Drive files.list response
        mock_list = mock_service.files().list
        mock_list.return_value.execute.return_value = {
            "files": [
                {
                    "id": "drive_file_999",
                    "name": "sample_podcast.mp4",
                    "mimeType": "video/mp4"
                }
            ]
        }
        
        headers = {"X-Goog-Resource-State": "add"}
        response = self.client.post("/webhook/drive", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "queued")
        self.assertEqual(data.get("file_name"), "sample_podcast.mp4")

        # Verify SQS send_message was called with expected payload
        mock_sqs_send.assert_called_once()
        call_kwargs = mock_sqs_send.call_args[1]
        self.assertEqual(call_kwargs["QueueUrl"], os.environ["AWS_SQS_QUEUE_URL"])
        sent_body = json.loads(call_kwargs["MessageBody"])
        self.assertEqual(sent_body["file_id"], "drive_file_999")
        self.assertEqual(sent_body["file_name"], "sample_podcast.mp4")
        print("  [PASS] POST /webhook/drive successfully queues video job to SQS")

    @patch("src.utils.drive_utils.get_drive_service")
    def test_06_webhook_receive_non_video_file(self, mock_drive_service):
        """Test POST /webhook/drive ignores non-video files (e.g. PDF/Image)."""
        mock_service = MagicMock()
        mock_drive_service.return_value = mock_service
        
        mock_service.files().list.return_value.execute.return_value = {
            "files": [
                {
                    "id": "drive_file_888",
                    "name": "document.pdf",
                    "mimeType": "application/pdf"
                }
            ]
        }
        
        headers = {"X-Goog-Resource-State": "add"}
        response = self.client.post("/webhook/drive", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "not_a_video")
        print("  [PASS] POST /webhook/drive ignores non-video files")

    def test_07_mangum_lambda_handler(self):
        """Test that Mangum lambda_handler handles API Gateway v2 HTTP event properly."""
        # Simulated API Gateway HTTP API proxy event
        event = {
            "version": "2.0",
            "routeKey": "GET /health",
            "rawPath": "/health",
            "rawQueryString": "",
            "headers": {
                "host": "test.execute-api.us-east-1.amazonaws.com"
            },
            "requestContext": {
                "http": {
                    "method": "GET",
                    "path": "/health",
                    "protocol": "HTTP/1.1",
                    "sourceIp": "127.0.0.1",
                    "userAgent": "test-client"
                }
            },
            "isBase64Encoded": False
        }
        context = MagicMock()
        context.get_remaining_time_in_millis.return_value = 30000

        result = lambda_handler(event, context)
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertIn("status", body)
        print("  [PASS] Mangum lambda_handler executed successfully with simulated API Gateway event")


if __name__ == "__main__":
    unittest.main()
