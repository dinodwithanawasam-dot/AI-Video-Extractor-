"""
Unit tests for the AI Video Processing Worker (src/worker.py)
Tests SQS polling, job execution, DynamoDB saving, message deletion, and failure recovery.
"""
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

os.environ["AWS_SQS_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/123456789012/Flipline_Jobs"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

from src.worker import run_worker


class TestWorkerPipeline(unittest.TestCase):

    @patch("boto3.client")
    def test_01_worker_empty_queue(self, mock_boto3_client):
        """Worker should poll SQS and exit cleanly when queue is empty."""
        mock_sqs = MagicMock()
        mock_boto3_client.return_value = mock_sqs
        mock_sqs.receive_message.return_value = {"Messages": []}

        # Should not raise any exceptions
        run_worker()
        mock_sqs.receive_message.assert_called_once()
        mock_sqs.delete_message.assert_not_called()
        print("  [PASS] Worker handles empty SQS queue cleanly and exits")

    @patch("src.worker.load_whisper_model")
    @patch("src.worker.process_job")
    @patch("src.worker.save_video_record")
    @patch("boto3.client")
    def test_02_worker_successful_job(
        self, mock_boto3_client, mock_save_db, mock_process_job, mock_load_model
    ):
        """Worker pulls job, executes pipeline, saves to DB, and deletes SQS message."""
        mock_sqs = MagicMock()
        mock_boto3_client.return_value = mock_sqs

        test_job = {
            "file_id": "vid_abc123",
            "file_name": "interview.mp4"
        }
        mock_sqs.receive_message.return_value = {
            "Messages": [
                {
                    "Body": json.dumps(test_job),
                    "ReceiptHandle": "receipt_token_xyz"
                }
            ]
        }

        mock_load_model.return_value = MagicMock()
        mock_process_job.return_value = {
            "folder": "test_user/interview_123",
            "main_title": "AI in 2026",
            "summary": "Insightful discussion on AI agentic pipelines",
            "article_path": "data/output/article.md",
            "denoised_video": "https://res.cloudinary.com/demo/video1.mp4",
            "denoised_audio": "https://res.cloudinary.com/demo/audio1.mp3",
            "highlights": {"title": "Key Moment"},
            "reels": [{"title": "Short 1"}]
        }
        mock_save_db.return_value = True

        run_worker()

        # 1. Check process_job was called
        mock_process_job.assert_called_once()

        # 2. Check save_video_record was called with expected DB schema
        mock_save_db.assert_called_once()
        db_record = mock_save_db.call_args[0][0]
        self.assertEqual(db_record["video_id"], "vid_abc123")
        self.assertEqual(db_record["status"], "success")
        self.assertEqual(db_record["main_title"], "AI in 2026")

        # 3. Check SQS message was deleted (crucial!)
        mock_sqs.delete_message.assert_called_once_with(
            QueueUrl=os.environ["AWS_SQS_QUEUE_URL"],
            ReceiptHandle="receipt_token_xyz"
        )
        print("  [PASS] Worker successfully executes job, saves to DynamoDB, and deletes SQS ticket")

    @patch("src.worker.load_whisper_model")
    @patch("src.worker.process_job")
    @patch("src.worker.save_video_record")
    @patch("boto3.client")
    def test_03_worker_failure_retains_sqs_message(
        self, mock_boto3_client, mock_save_db, mock_process_job, mock_load_model
    ):
        """On job failure, worker logs error and does NOT delete message (for automatic retry)."""
        mock_sqs = MagicMock()
        mock_boto3_client.return_value = mock_sqs

        test_job = {
            "file_id": "vid_fail_123",
            "file_name": "corrupt_video.mp4"
        }
        mock_sqs.receive_message.return_value = {
            "Messages": [
                {
                    "Body": json.dumps(test_job),
                    "ReceiptHandle": "receipt_token_error"
                }
            ]
        }

        mock_load_model.return_value = MagicMock()
        # Simulate video processing error
        mock_process_job.side_effect = RuntimeError("FFmpeg decode error: file corrupted")

        # Should catch exception internally and not crash
        run_worker()

        # SQS message MUST NOT be deleted so SQS visibility timeout can retry
        mock_sqs.delete_message.assert_not_called()
        mock_save_db.assert_not_called()
        print("  [PASS] Worker failure safely preserves SQS message for automatic retry")


if __name__ == "__main__":
    unittest.main()
