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
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
)

def inspect():
    lam = session.client("lambda")
    fn = lam.get_function_configuration(FunctionName="flipline-api")
    print("=== flipline-api Lambda Environment Variables ===", flush=True)
    for k, v in fn.get("Environment", {}).get("Variables", {}).items():
        if "KEY" in k or "SECRET" in k:
            print(f"  {k} = ***REDACTED***", flush=True)
        else:
            print(f"  {k} = {v}", flush=True)

    ecs = session.client("ecs")
    task_def = ecs.describe_task_definition(taskDefinition="flipline-worker-task:2")
    container = task_def["taskDefinition"]["containerDefinitions"][0]
    print("\n=== ECS Worker Container Environment Variables ===", flush=True)
    for env_item in container.get("environment", []):
        k = env_item.get("name")
        v = env_item.get("value")
        if "KEY" in k or "SECRET" in k:
            print(f"  {k} = ***REDACTED***", flush=True)
        else:
            print(f"  {k} = {v}", flush=True)

if __name__ == "__main__":
    inspect()
