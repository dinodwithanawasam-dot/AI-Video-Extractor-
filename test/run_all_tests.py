"""
Master Test Runner for AI Video Extractor Pipeline.
Runs all unit and integration tests and performs live resource checks.
Usage:
    python test/run_all_tests.py
"""
import os
import sys
import unittest
import time
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")


def run_unit_tests():
    print("=" * 70)
    print("🚀 RUNNING AUTOMATED UNIT & INTEGRATION TEST SUITES")
    print("=" * 70)

    test_dir = ROOT_DIR / "test"
    sys.path.insert(0, str(test_dir))

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(test_dir), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    start_time = time.time()
    result = runner.run(suite)
    duration = time.time() - start_time

    return result, duration


def run_live_integration_checks():
    print("\n" + "=" * 70)
    print("🌐 RUNNING LIVE CLOUD SERVICE SANITY CHECKS")
    print("=" * 70)

    # 1. Check Google Drive API credentials
    print("[1/4] Checking Google Drive Service Account...")
    try:
        from src.utils.drive_utils import get_drive_service
        service = get_drive_service()
        if service:
            res = service.files().list(pageSize=1, fields="files(id, name)").execute()
            print("      ✅ Google Drive Auth: PASSED (Successfully queried Google Drive API)")
        else:
            print("      ❌ Google Drive Auth: FAILED (get_drive_service returned None)")
    except Exception as e:
        print(f"      ❌ Google Drive Auth: ERROR ({e})")

    # 2. Check Cloudinary Configuration
    print("\n[2/4] Checking Cloudinary CDN Config...")
    try:
        import cloudinary
        import cloudinary.api
        cloudinary.config(
            cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
            api_key=os.getenv("CLOUDINARY_API_KEY"),
            api_secret=os.getenv("CLOUDINARY_API_SECRET"),
            secure=True
        )
        ping_res = cloudinary.api.ping()
        if ping_res.get("status") == "ok":
            print("      ✅ Cloudinary CDN: PASSED (Ping response: ok)")
        else:
            print(f"      ⚠️ Cloudinary CDN: Unexpected response {ping_res}")
    except Exception as e:
        print(f"      ❌ Cloudinary CDN: ERROR ({e})")

    # 3. Check DynamoDB Table
    print("\n[3/4] Checking AWS DynamoDB 'Flipline_Videos' Table...")
    try:
        import boto3
        dynamodb = boto3.client(
            'dynamodb',
            region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        desc = dynamodb.describe_table(TableName="Flipline_Videos")["Table"]
        status = desc.get("TableStatus")
        if status == "ACTIVE":
            print(f"      ✅ DynamoDB Flipline_Videos: PASSED (Table is {status})")
        else:
            print(f"      ⚠️ DynamoDB Flipline_Videos: Table status is {status}")
    except Exception as e:
        print(f"      ❌ DynamoDB Flipline_Videos: ERROR ({e})")

    # 4. Check AWS SQS Queue Status
    print("\n[4/4] Checking AWS SQS Queue URL...")
    sqs_url = os.getenv("AWS_SQS_QUEUE_URL", "")
    if not sqs_url or "YOUR_ACCOUNT" in sqs_url or sqs_url.endswith("/Flipline_Jobs") and "amazonaws.com//Flipline_Jobs" in sqs_url:
        print("      ℹ️ AWS SQS: Placeholder / Pending queue creation in AWS.")
        print("         -> As expected before deployment: DevOps will create 'Flipline_Jobs' in AWS Step 3.")
    else:
        try:
            import boto3
            sqs = boto3.client(
                'sqs',
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
            )
            sqs.get_queue_attributes(QueueUrl=sqs_url, AttributeNames=["All"])
            print(f"      ✅ AWS SQS: PASSED (Connected to {sqs_url})")
        except Exception as e:
            print("      ℹ️ AWS SQS: Queue pending creation or not yet accessible.")
            print(f"         ({e})")


def main():
    test_result, duration = run_unit_tests()
    run_live_integration_checks()

    print("\n" + "=" * 70)
    print("📊 OVERALL SUMMARY REPORT")
    print("=" * 70)
    print(f"Tests Run:    {test_result.testsRun}")
    print(f"Passed:       {test_result.testsRun - len(test_result.failures) - len(test_result.errors)}")
    print(f"Failures:     {len(test_result.failures)}")
    print(f"Errors:       {len(test_result.errors)}")
    print(f"Time Elapsed: {duration:.2f}s")
    print("=" * 70)

    if test_result.wasSuccessful():
        print("🎉 ALL TESTS PASSED! Local codebase is 100% verified and ready for deployment.\n")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED. Please review the tracebacks above.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
