import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
import boto3

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

TABLE_NAME = "Flipline_Videos"

def create_dynamodb_table():
    """Creates the DynamoDB table with the required GSI for sorting."""
    print("Initializing AWS Boto3 Client...")
    try:
        dynamodb = boto3.resource(
            'dynamodb',
            region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        client = dynamodb.meta.client

        # Check if table already exists
        try:
            client.describe_table(TableName=TABLE_NAME)
            print(f"✅ Table '{TABLE_NAME}' already exists!")
            return
        except client.exceptions.ResourceNotFoundException:
            pass # Table doesn't exist, proceed to create

        print(f"Creating Table '{TABLE_NAME}'... This might take a few seconds.")
        
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {
                    'AttributeName': 'video_id',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'video_id',
                    'AttributeType': 'S' # String
                },
                {
                    'AttributeName': 'record_type',
                    'AttributeType': 'S' # String (Always "video")
                },
                {
                    'AttributeName': 'created_at',
                    'AttributeType': 'S' # String (ISO Timestamp)
                }
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'ByDateIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'record_type',
                            'KeyType': 'HASH'  # Partition key for the GSI
                        },
                        {
                            'AttributeName': 'created_at',
                            'KeyType': 'RANGE'  # Sort key for the GSI
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL' # Return all attributes when queried
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

        # Wait for the table to be created
        table.wait_until_exists()
        print(f"🎉 Success! DynamoDB Table '{TABLE_NAME}' created and ready.")
        
    except Exception as e:
        print(f"❌ Error creating table: {e}")

if __name__ == "__main__":
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        print("❌ AWS_ACCESS_KEY_ID is missing in .env file.")
        sys.exit(1)
        
    create_dynamodb_table()
