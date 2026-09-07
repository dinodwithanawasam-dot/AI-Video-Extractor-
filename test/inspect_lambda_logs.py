import os
import sys
import boto3
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

session = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name="us-east-1"
)

logs = session.client("logs")
streams = logs.describe_log_streams(
    logGroupName="/aws/lambda/flipline-api",
    orderBy="LastEventTime",
    descending=True,
    limit=3
)["logStreams"]

for s in streams:
    s_name = s["logStreamName"]
    print(f"\n=== Stream: {s_name} ===")
    events = logs.get_log_events(
        logGroupName="/aws/lambda/flipline-api",
        logStreamName=s_name,
        limit=20
    )["events"]
    for e in events:
        print(f"  {e['message'].strip()}")
