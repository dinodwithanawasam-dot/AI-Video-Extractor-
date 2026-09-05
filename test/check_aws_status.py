import os
import sys
import boto3
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

# Explicitly use credentials from .env
session = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
)

def log(msg):
    print(msg, flush=True)

def check_status():
    log("=" * 60)
    log("CHECKING AWS PIPELINE STATUS")
    log("=" * 60)

    # 1. Identity Check
    sts = session.client("sts")
    identity = sts.get_caller_identity()
    log(f"Authenticated AWS Identity: {identity['Arn']}")
    log(f"   Account: {identity['Account']}")

    # 2. SQS Queue Status
    sqs = session.client("sqs")
    queues = sqs.list_queues().get("QueueUrls", [])
    log(f"\nSQS Queues Found: {len(queues)}")
    for q_url in queues:
        try:
            attrs = sqs.get_queue_attributes(
                QueueUrl=q_url,
                AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible", "ApproximateNumberOfMessagesDelayed"]
            )
            log(f"   - URL: {q_url}")
            log(f"     Messages: Available={attrs['Attributes'].get('ApproximateNumberOfMessages')}, In-Flight={attrs['Attributes'].get('ApproximateNumberOfMessagesNotVisible')}")
        except Exception as e:
            log(f"     Error: {e}")

    # 3. EventBridge Pipes
    pipes = session.client("pipes")
    log("\nEventBridge Pipes:")
    try:
        pipe_list = pipes.list_pipes()
        pipes_found = pipe_list.get("Pipes", [])
        if pipes_found:
            for p in pipes_found:
                log(f"   - Name: {p.get('Name')}")
                log(f"     State: {p.get('CurrentState')} | Target: {p.get('Target')}")
        else:
            log("   No EventBridge Pipes found.")
    except Exception as e:
        log(f"   Pipes Error: {e}")

    # 4. EventBridge Scheduler
    scheduler = session.client("scheduler")
    log("\nEventBridge Schedules:")
    try:
        schedules = scheduler.list_schedules()
        sched_list = schedules.get("Schedules", [])
        if sched_list:
            for s in sched_list:
                log(f"   - Name: {s.get('Name')}")
                log(f"     State: {s.get('State')} | Schedule: {s.get('ScheduleExpression')}")
        else:
            log("   No Schedules found.")
    except Exception as e:
        log(f"   Scheduler Error: {e}")

    # 5. ECS Cluster & Tasks
    ecs = session.client("ecs")
    cluster_name = "Flipline-Cluster"
    log(f"\nECS Cluster: {cluster_name}")
    try:
        tasks = ecs.list_tasks(cluster=cluster_name)
        task_arns = tasks.get("taskArns", [])
        log(f"   - Active/Pending Tasks: {len(task_arns)}")
        if task_arns:
            desc = ecs.describe_tasks(cluster=cluster_name, tasks=task_arns)
            for t in desc.get("tasks", []):
                t_id = t["taskArn"].split("/")[-1]
                t_def = t["taskDefinitionArn"].split("/")[-1]
                log(f"     * [{t_id}] Status: {t.get('lastStatus')} (Desired: {t.get('desiredStatus')}) | Def: {t_def} | StartedBy: {t.get('startedBy', 'N/A')}")
                for c in t.get("containers", []):
                    if c.get("exitCode") is not None or c.get("reason"):
                        log(f"       Container: {c.get('name')} | ExitCode: {c.get('exitCode')} | Reason: {c.get('reason')}")
        
        task_defs = ecs.list_task_definitions(familyPrefix="flipline-worker-task", sort="DESC")
        log(f"   - Latest Task Definition: {task_defs.get('taskDefinitionArns', ['None'])[0]}")
    except Exception as e:
        log(f"   ECS Error: {e}")

    # 6. ECR Image Status
    ecr = session.client("ecr")
    log("\nECR Repository: flipline-worker")
    try:
        images = ecr.describe_images(repositoryName="flipline-worker")
        image_details = sorted(images.get("imageDetails", []), key=lambda x: x.get("imagePushedAt"), reverse=True)
        if image_details:
            latest_img = image_details[0]
            tags = latest_img.get("imageTags", [])
            log(f"   - Latest Image Digest: {latest_img.get('imageDigest')[:25]}...")
            log(f"   - Tags: {tags}")
            log(f"   - Pushed At: {latest_img.get('imagePushedAt')}")
    except Exception as e:
        log(f"   ECR Error: {e}")

    # 7. DynamoDB Status
    dynamodb = session.client("dynamodb")
    log("\nDynamoDB Tables:")
    try:
        tables = dynamodb.list_tables().get("TableNames", [])
        log(f"   - Tables in account: {tables}")
        for tname in tables:
            desc = dynamodb.describe_table(TableName=tname)
            log(f"     * {tname}: Status={desc['Table']['TableStatus']}, Items={desc['Table'].get('ItemCount')}")
    except Exception as e:
        log(f"   DynamoDB Error: {e}")

    # 8. Lambda Functions
    lambda_client = session.client("lambda")
    log("\nLambda Functions:")
    for fname in ["flipline-api", "flipline-webhook-renewer"]:
        try:
            fn = lambda_client.get_function(FunctionName=fname)
            conf = fn["Configuration"]
            log(f"   - {fname}: Runtime={conf.get('Runtime')}, Handler={conf.get('Handler')}, State={conf.get('State')}")
        except Exception as e:
            log(f"   - {fname}: Error: {e}")

    log("\n" + "=" * 60)

if __name__ == "__main__":
    check_status()
