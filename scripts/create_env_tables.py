import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import boto3

# Ensure UTF-8 output on Windows console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

TABLES_TO_CREATE = [
    "Flipline_Videos_release",
    "Flipline_Videos_dev"
]

def create_table_if_not_exists(dynamodb, table_name: str):
    client = dynamodb.meta.client
    try:
        desc = client.describe_table(TableName=table_name)
        status = desc['Table']['TableStatus']
        print(f"[INFO] Table '{table_name}' already exists (Status: {status}).", flush=True)
        return
    except client.exceptions.ResourceNotFoundException:
        pass

    print(f"[CREATING] Creating table '{table_name}'...", flush=True)
    table = dynamodb.create_table(
        TableName=table_name,
        KeySchema=[
            {
                'AttributeName': 'video_id',
                'KeyType': 'HASH'
            }
        ],
        AttributeDefinitions=[
            {
                'AttributeName': 'video_id',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'record_type',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'created_at',
                'AttributeType': 'S'
            }
        ],
        GlobalSecondaryIndexes=[
            {
                'IndexName': 'ByDateIndex',
                'KeySchema': [
                    {
                        'AttributeName': 'record_type',
                        'KeyType': 'HASH'
                    },
                    {
                        'AttributeName': 'created_at',
                        'KeyType': 'RANGE'
                    }
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                },
                'ProvisionedThroughput': {
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            }
        ],
        ProvisionedThroughput={
            'ReadCapacityUnits': 5,
            'WriteCapacityUnits': 5
        }
    )

    print(f"[WAITING] Waiting for '{table_name}' to become ACTIVE...", flush=True)
    table.wait_until_exists()
    print(f"[SUCCESS] Table '{table_name}' is now ACTIVE and ready.", flush=True)

def main():
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    region_name = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    if not aws_access_key_id or not aws_secret_access_key:
        print("[ERROR] AWS credentials missing in .env", flush=True)
        sys.exit(1)

    print(f"[INFO] Connecting to AWS DynamoDB in region '{region_name}'...", flush=True)
    dynamodb = boto3.resource(
        'dynamodb',
        region_name=region_name,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key
    )

    for tbl_name in TABLES_TO_CREATE:
        create_table_if_not_exists(dynamodb, tbl_name)

    print("\n[COMPLETE] All requested DynamoDB tables are set up!", flush=True)

if __name__ == "__main__":
    main()
