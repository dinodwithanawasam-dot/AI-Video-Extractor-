import os
import sys
import boto3
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

session = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
)

def monitor():
    print("=" * 70, flush=True)
    print("🚀 FLIPLINE LIVE PIPELINE MONITOR", flush=True)
    print("=" * 70, flush=True)

    # 1. SQS Status
    sqs = session.client("sqs")
    queue_url = os.getenv("AWS_SQS_QUEUE_URL")
    print(f"\n[1] SQS Queue ({queue_url.split('/')[-1]}):", flush=True)
    try:
        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
        )
        avail = attrs["Attributes"].get("ApproximateNumberOfMessages", "0")
        inflight = attrs["Attributes"].get("ApproximateNumberOfMessagesNotVisible", "0")
        print(f"    Available Messages : {avail} (waiting to be processed)", flush=True)
        print(f"    In-Flight Messages : {inflight} (currently being processed)", flush=True)
    except Exception as e:
        print(f"    ❌ SQS Error: {e}", flush=True)

    # 2. ECS Cluster & Tasks
    ecs = session.client("ecs")
    cluster = "Flipline-Cluster"
    print(f"\n[2] ECS Fargate Cluster ({cluster}):", flush=True)
    try:
        tasks = ecs.list_tasks(cluster=cluster)
        task_arns = tasks.get("taskArns", [])
        print(f"    Running/Pending Tasks: {len(task_arns)}", flush=True)
        if task_arns:
            desc = ecs.describe_tasks(cluster=cluster, tasks=task_arns)
            for t in desc.get("tasks", []):
                t_id = t["taskArn"].split("/")[-1]
                status = t.get("lastStatus")
                desired = t.get("desiredStatus")
                started_by = t.get("startedBy", "N/A")
                print(f"    👉 Task [{t_id}] Status: {status} (Desired: {desired}) | Started By: {started_by}", flush=True)
    except Exception as e:
        print(f"    ❌ ECS Error: {e}", flush=True)

    # 3. ECS Worker CloudWatch Logs (Last 10 lines)
    logs = session.client("logs")
    log_group = "/ecs/flipline-worker-task"
    print(f"\n[3] Latest Worker Logs ({log_group}):", flush=True)
    try:
        streams = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy="LastEventTime",
            descending=True,
            limit=1
        ).get("logStreams", [])
        if streams:
            stream_name = streams[0]["logStreamName"]
            events = logs.get_log_events(
                logGroupName=log_group,
                logStreamName=stream_name,
                limit=10
            ).get("events", [])
            for ev in events[-10:]:
                msg = ev.get("message", "").strip()
                print(f"    | {msg}", flush=True)
        else:
            print("    ℹ️ No worker log streams yet (Worker has not run a job yet).", flush=True)
    except Exception as e:
        print(f"    ℹ️ {e}", flush=True)

    # 4. DynamoDB Processed Videos
    dynamodb = session.client("dynamodb")
    table_name = "Flipline_Videos"
    print(f"\n[4] DynamoDB Processed Videos Table ({table_name}):", flush=True)
    try:
        resp = dynamodb.scan(TableName=table_name, Limit=5)
        items = resp.get("Items", [])
        print(f"    Total Processed Records: {resp.get('Count', 0)}", flush=True)
        for item in items:
            video_id = item.get("video_id", {}).get("S", "N/A")
            status = item.get("status", {}).get("S", "N/A")
            print(f"    ✅ Video ID: {video_id} | Status: {status}", flush=True)
    except Exception as e:
        print(f"    ❌ DynamoDB Error: {e}", flush=True)

    # 5. Google Drive Folder State
    try:
        from src.utils.drive_utils import get_drive_service
        service = get_drive_service()
        if service:
            input_fid = os.getenv("GDRIVE_INPUT_FOLDER_ID")
            archive_fid = os.getenv("GDRIVE_ARCHIVE_FOLDER_ID")
            
            in_files = service.files().list(
                q=f"'{input_fid}' in parents and trashed=false",
                fields="files(id, name)"
            ).execute().get("files", [])
            
            arch_files = service.files().list(
                q=f"'{archive_fid}' in parents and trashed=false",
                fields="files(id, name)"
            ).execute().get("files", [])

            print(f"\n[5] Google Drive State:", flush=True)
            print(f"    📂 Input Folder (AI_Video_Input)   : {len(in_files)} file(s)", flush=True)
            for f in in_files[:3]:
                print(f"       - {f['name']} ({f['id']})", flush=True)
            print(f"    📦 Archive Folder (AI_Video_Archive): {len(arch_files)} file(s)", flush=True)
            for f in arch_files[:3]:
                print(f"       - {f['name']} ({f['id']})", flush=True)
    except Exception as e:
        print(f"\n[5] Google Drive Check: {e}", flush=True)

    print("\n" + "=" * 70, flush=True)

if __name__ == "__main__":
    monitor()
