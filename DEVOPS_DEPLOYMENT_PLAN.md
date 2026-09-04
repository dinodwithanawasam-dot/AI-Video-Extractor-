# 🚀 DevOps Deployment Implementation Plan
### Production Serverless Pipeline — AWS Infrastructure & Deployment Guide

> **Note for DevOps Engineer:**
> All application code modifications (`api.py`, `src/worker.py`, `src/webhook_renewer.py`, `src/utils/drive_utils.py`, `requirements.txt`, etc.) have **already been implemented and verified** in this repository.
> 
> Your scope is to:
> 1. Provision the required AWS serverless infrastructure (IAM, Secrets Manager, SQS, ECR, ECS Fargate, EventBridge Pipes, Lambda, API Gateway, EventBridge Scheduler).
> 2. Build and push the Docker worker image to AWS ECR.
> 3. Package and deploy the serverless Lambda functions.
> 4. Populate and configure the environment variables across all services.
> 5. Run the one-time Google Drive webhook registration script and verify the pipeline.

---

## 🗺️ Architecture Overview

```
                      ┌────────────────────────────┐
                      │  Google Drive Input Folder  │
                      └─────────────┬──────────────┘
                                    │ (Webhook Push on upload)
                                    ▼
                      ┌────────────────────────────┐
                      │    Amazon API Gateway      │
                      │  (Public HTTPS Endpoint)   │
                      └─────────────┬──────────────┘
                                    │ Proxy ANY /{proxy+}
                                    ▼
                      ┌────────────────────────────┐
                      │   AWS Lambda: flipline-api  │
                      │ (FastAPI via Mangum, 512MB)│
                      └─────────────┬──────────────┘
                                    │ Sends message with file_id
                                    ▼
                      ┌────────────────────────────┐
                      │    Amazon SQS Queue        │
                      │      Flipline_Jobs         │
                      │ (Visibility Timeout: 3600s)│
                      └─────────────┬──────────────┘
                                    │ Auto-trigger (Batch size: 1)
                                    ▼
                      ┌────────────────────────────┐
                      │    EventBridge Pipe        │
                      │ (Launches task on demand)  │
                      └─────────────┬──────────────┘
                                    │ RunTask (FARGATE)
                                    ▼
                      ┌────────────────────────────┐
                      │    ECS Fargate Worker      │
                      │  4 vCPU / 8 GB RAM         │
                      │  - Downloads Video         │
                      │  - FFmpeg + Whisper AI     │
                      │  - Uploads to Cloudinary   │
                      │  - Saves to DynamoDB       │
                      │  - Deletes SQS Message     │
                      │  - Container Auto-Exits    │
                      └────────────────────────────┘

  [EventBridge Scheduler] ──(Every 6 Days)──► [Lambda: flipline-webhook-renewer] ──► [Google Drive API]
                                               (Auto-renews expiring 7-day webhook)
```

---

## 📋 Table of Contents
1. [Prerequisites & Target Region](#1-prerequisites--target-region)
2. [Local Environment Setup (Using `uv`)](#2-local-environment-setup-using-uv)
3. [Environment Variables Master Specification](#3-environment-variables-master-specification)
4. [AWS Step-by-Step Infrastructure Provisioning](#4-aws-step-by-step-infrastructure-provisioning)
   - [Step 1: IAM Roles & Policies](#step-1-iam-roles--policies)
   - [Step 2: AWS Secrets Manager](#step-2-aws-secrets-manager)
   - [Step 3: Amazon SQS Queue](#step-3-amazon-sqs-queue)
   - [Step 4: Amazon ECR Repository](#step-4-amazon-ecr-repository)
   - [Step 5: CloudWatch Log Group](#step-5-cloudwatch-log-group)
   - [Step 6: Amazon ECS Cluster](#step-6-amazon-ecs-cluster)
   - [Step 7: Build & Push Docker Worker Image](#step-7-build--push-docker-worker-image)
   - [Step 8: ECS Fargate Task Definition (4 vCPU / 8 GB RAM)](#step-8-ecs-fargate-task-definition)
   - [Step 9: Amazon EventBridge Pipe](#step-9-amazon-eventbridge-pipe)
   - [Step 10: AWS Lambda — flipline-api](#step-10-aws-lambda--flipline-api)
   - [Step 11: Amazon API Gateway (HTTP API)](#step-11-amazon-api-gateway)
   - [Step 12: AWS Lambda — flipline-webhook-renewer](#step-12-aws-lambda--flipline-webhook-renewer)
   - [Step 13: Amazon EventBridge Scheduler (Webhook Auto-Renewal)](#step-13-amazon-eventbridge-scheduler)
5. [Packaging & Deployment Commands](#5-packaging--deployment-commands)
6. [Post-Deployment Initial Webhook Activation](#6-post-deployment-initial-webhook-activation)
7. [End-to-End Verification & Monitoring](#7-end-to-end-verification--monitoring)
8. [DevOps Sign-Off Checklist](#8-devops-sign-off-checklist)

---

## 1. Prerequisites & Target Region

* **Target AWS Region**: `us-east-1` (US East, N. Virginia) — keep all resources in the same region.
* **CLI Tools Required**:
  - `aws-cli` v2 (configured with administrator privileges: `aws configure`)
  - `docker` (engine running with buildx/compose support)
  - `uv` (Astral's fast Python package manager) or `python` 3.11 + `pip`
* **Local Repo State**: Git repository cloned and on the target deployment branch.

---

## 2. Local Environment Setup (Using `uv`)

To run auxiliary scripts (such as `register_webhook.py`, packaging Lambda artifacts, or local verification tests), configure the local Python environment using **`uv`** (ultra-fast dependency resolver and installer).

### 2.1 Install `uv` (if not already installed)
- **Windows (PowerShell)**:
  ```powershell
  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- **Linux / macOS / WSL**:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Via standard pip**:
  ```bash
  pip install uv
  ```

### 2.2 Create and Activate Virtual Environment
From the project root:
```bash
# Create a Python 3.11 virtual environment (.venv)
uv venv --python 3.11

# Activate on Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Activate on Linux / macOS / WSL:
source .venv/bin/activate
```

### 2.3 Install Dependencies via `uv`
Install all dependencies in seconds:
```bash
uv pip install -r requirements.txt
```

### 2.4 (Optional) Verify Local Execution
To verify that the application and cloud connections work cleanly before deploying to AWS:
```bash
# Run the automated unit & integration test suite (16 tests + cloud checks)
python test/run_all_tests.py

# (Optional) Launch the API locally
uvicorn api:app --reload --port 8000
curl http://localhost:8000/health
# Expected output: {"status":"ok"}
```

---

## 3. Environment Variables Master Specification

Several environment variables are shared across the ECS Fargate Worker and the two Lambda functions.

### 🔑 Master Variables Table

| Environment Variable | Where Used | Description / Source |
|---|---|---|
| `OPENAI_API_KEY` | ECS Worker | OpenAI API key for video summarization / title extraction |
| `CLOUDINARY_CLOUD_NAME` | ECS Worker | Cloudinary cloud identifier (e.g., `dakae2qgl`) |
| `CLOUDINARY_API_KEY` | ECS Worker | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | ECS Worker | Cloudinary API secret |
| `AWS_DEFAULT_REGION` | Worker, Lambdas, Local | Set to `us-east-1` |
| `AWS_ACCESS_KEY_ID` | Worker, Local | AWS IAM Access Key (or inherited from IAM execution role) |
| `AWS_SECRET_ACCESS_KEY` | Worker, Local | AWS IAM Secret Key (or inherited from IAM execution role) |
| `AWS_SQS_QUEUE_URL` | Worker, `flipline-api`, Local | URL obtained in **Step 3** (`https://sqs.us-east-1.amazonaws.com/<ACC_ID>/Flipline_Jobs`) |
| `GOOGLE_CREDENTIALS_SECRET_ARN` | Worker, Lambdas, Local | ARN of the secret created in **Step 2** (`arn:aws:secretsmanager:us-east-1:<ACC_ID>:secret:flipline/google-credentials-xxxxxx`) |
| `GDRIVE_INPUT_FOLDER_ID` | Worker, `flipline-api`, Renewer, Local | Target Google Drive folder ID to monitor for video uploads |
| `GDRIVE_ARCHIVE_FOLDER_ID` | Worker | Google Drive archive destination folder ID |
| `PUBLIC_WEBHOOK_TOKEN` | `flipline-api`, Renewer, Local | A secure random alphanumeric string (e.g. `flipline_prod_token_2026_xyz`) |
| `PUBLIC_API_URL` | Renewer, Local | The API Gateway Invoke URL from **Step 11** (`https://<api-id>.execute-api.us-east-1.amazonaws.com/prod`) |

> ⚠️ **Action Required for DevOps**:
> As you provision the AWS resources below, update your deployment `.env` file with the newly generated `AWS_SQS_QUEUE_URL`, `GOOGLE_CREDENTIALS_SECRET_ARN`, and `PUBLIC_API_URL`.

---

## 4. AWS Step-by-Step Infrastructure Provisioning

---

### Step 1: IAM Roles & Policies

You will create 3 IAM roles:

#### 1.1 `flipline-lambda-role`
* **Trusted Entity**: AWS Service → `Lambda`
* **Attach Policies**:
  - `AWSLambdaBasicExecutionRole` (AWS managed)
  - `AmazonSQSFullAccess` (AWS managed)
  - `AmazonDynamoDBFullAccess` (AWS managed)
  - `SecretsManagerReadWrite` (AWS managed)
* **Role Name**: `flipline-lambda-role`

#### 1.2 `flipline-ecs-task-role`
* **Trusted Entity**: AWS Service → `Elastic Container Service` → `Elastic Container Service Task`
* **Attach Policies**:
  - `AmazonSQSFullAccess`
  - `AmazonDynamoDBFullAccess`
  - `SecretsManagerReadWrite`
  - `CloudWatchLogsFullAccess`
* **Role Name**: `flipline-ecs-task-role`

#### 1.3 `ecsTaskExecutionRole`
* **Trusted Entity**: AWS Service → `Elastic Container Service Task`
* **Attach Policies**:
  - `AmazonECSTaskExecutionRolePolicy`
  - `AmazonEC2ContainerRegistryReadOnly`
* **Role Name**: `ecsTaskExecutionRole` *(Verify if this role already exists in the AWS account before creating)*.

---

### Step 2: AWS Secrets Manager

Store the Google Service Account credentials securely so that Lambda and Fargate can retrieve them at runtime without baking keys into Docker images.

1. Navigate to **Secrets Manager** → Click **Store a new secret**.
2. **Secret Type**: Choose **Other type of secret**.
3. Under Key/Value pairs, click the **Plaintext** tab.
4. Paste the entire contents of `credentials.json` (valid Google Service Account JSON).
5. Click **Next**.
6. **Secret Name**: `flipline/google-credentials`
7. Click **Next** → Leave automatic rotation disabled → Click **Store**.
8. Record the **Secret ARN**:
   ```
   arn:aws:secretsmanager:us-east-1:<YOUR_ACCOUNT_ID>:secret:flipline/google-credentials-xxxxxx
   ```
   👉 Add this to `.env` as `GOOGLE_CREDENTIALS_SECRET_ARN`.

---

### Step 3: Amazon SQS Queue

1. Navigate to **Simple Queue Service (SQS)** → Click **Create queue**.
2. **Type**: **Standard** (do not select FIFO).
3. **Name**: `Flipline_Jobs`
4. **Configuration Settings**:
   - **Visibility timeout**: `3600` seconds (1 hour — prevents duplicate processing while Fargate runs).
   - **Message retention period**: `345600` seconds (4 days).
   - **Receive message wait time**: `5` seconds (long polling).
5. Click **Create queue**.
6. Record the **Queue URL**:
   ```
   https://sqs.us-east-1.amazonaws.com/<YOUR_ACCOUNT_ID>/Flipline_Jobs
   ```
   👉 Add this to `.env` as `AWS_SQS_QUEUE_URL`.

---

### Step 4: Amazon ECR Repository

1. Navigate to **Elastic Container Registry (ECR)** → Click **Create repository**.
2. **Visibility**: **Private**.
3. **Repository Name**: `flipline-worker`.
4. Click **Create repository**.
5. Record the **Repository URI**:
   ```
   <YOUR_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/flipline-worker
   ```

---

### Step 5: CloudWatch Log Group

1. Navigate to **CloudWatch** → **Log groups** → Click **Create log group**.
2. **Log group name**: `/ecs/flipline-worker`
3. **Retention setting**: `7 days` (keeps costs minimal).
4. Click **Create**.

---

### Step 6: Amazon ECS Cluster

1. Navigate to **Elastic Container Service (ECS)** → **Clusters** → Click **Create cluster**.
2. **Cluster Name**: `Flipline-Cluster`
3. **Infrastructure**: Select **AWS Fargate (serverless)**. Ensure Amazon EC2 is unchecked.
4. Click **Create**.

---

### Step 7: Build & Push Docker Worker Image

You can use the included `deploy_worker.sh` bash script or run the standard Docker commands:

#### Option A: Using bash script
```bash
chmod +x deploy_worker.sh
./deploy_worker.sh
```

#### Option B: Manual CLI Commands (PowerShell / Bash)
```bash
# 1. Fetch AWS Account ID
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"
ECR_URI="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/flipline-worker"

# 2. Login Docker to ECR
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

# 3. Build Worker Docker Image
docker build -t flipline-worker -f Docker/Dockerfile .

# 4. Tag Image
docker tag flipline-worker:latest "${ECR_URI}:latest"

# 5. Push to ECR
docker push "${ECR_URI}:latest"
```

---

### Step 8: ECS Fargate Task Definition

1. Navigate to **ECS** → **Task definitions** → Click **Create new task definition**.
2. Configure **Infrastructure requirements**:
   - **Task definition family**: `flipline-worker-task`
   - **Launch type**: `AWS Fargate`
   - **Operating system / Architecture**: `Linux/X86_64`
   - **Task CPU**: `4 vCPU`
   - **Task Memory**: `8 GB`
   - **Task role**: `flipline-ecs-task-role`
   - **Task execution role**: `ecsTaskExecutionRole`
3. Configure **Container - 1**:
   - **Name**: `flipline-worker`
   - **Image URI**: `<YOUR_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/flipline-worker:latest`
   - **Essential container**: `Yes`
4. Configure **Environment variables**:
   Add the following key-value pairs:
   - `OPENAI_API_KEY` = `<Your OpenAI Key>`
   - `CLOUDINARY_CLOUD_NAME` = `dakae2qgl`
   - `CLOUDINARY_API_KEY` = `<Your Cloudinary API Key>`
   - `CLOUDINARY_API_SECRET` = `<Your Cloudinary API Secret>`
   - `GDRIVE_INPUT_FOLDER_ID` = `1f-WCZqbKkQfzXAClTXT_BaWCinD6skr1`
   - `GDRIVE_ARCHIVE_FOLDER_ID` = `1VAnelO9VFFlG6zOJOHrVlVYIT_I4t6xh`
   - `AWS_SQS_QUEUE_URL` = `<SQS URL from Step 3>`
   - `AWS_DEFAULT_REGION` = `us-east-1`
   - `GOOGLE_CREDENTIALS_SECRET_ARN` = `<Secret ARN from Step 2>`
   *(Note: AWS_ACCESS_KEY_ID & AWS_SECRET_ACCESS_KEY are not required if using IAM task roles, but can be added if required).*
5. Configure **Logging**:
   - **Log driver**: `awslogs`
   - **awslogs-group**: `/ecs/flipline-worker`
   - **awslogs-region**: `us-east-1`
   - **awslogs-stream-prefix**: `ecs`
6. Click **Create**.

---

### Step 9: Amazon EventBridge Pipe

The EventBridge Pipe connects SQS to ECS Fargate, launching tasks dynamically on arrival of messages.

1. Navigate to **Amazon EventBridge** → **Pipes** → Click **Create pipe**.
2. **Pipe settings**:
   - **Pipe name**: `flipline-sqs-to-fargate`
3. **Source**:
   - **Source**: `SQS`
   - **SQS queue**: `Flipline_Jobs`
   - **Batch size**: `1` (ensures 1 video per container)
   - **Batch window**: `0`
4. **Target**:
   - **Target service**: `ECS cluster`
   - **Cluster**: `Flipline-Cluster`
   - **Task definition**: `flipline-worker-task`
   - **Launch type**: `FARGATE`
   - **Platform version**: `LATEST`
   - **Task count**: `1`
5. **Target Networking** (Under ECS Target settings):
   - **Subnets**: Select any 2 default public subnets in `us-east-1`.
   - **Assign public IP**: **ENABLED** ⚠️ *(CRITICAL: Required for Fargate to reach AWS SQS, Secrets Manager, Cloudinary, and Google Drive).*
6. Click **Create pipe**.

---

### Step 10: AWS Lambda — `flipline-api`

1. Navigate to **Lambda** → Click **Create function**.
2. Settings:
   - **Function name**: `flipline-api`
   - **Runtime**: `Python 3.11`
   - **Execution role**: `Use an existing role` → Select `flipline-lambda-role`
3. Click **Create function**.
4. Configure the function:
   - **Code**: Upload `lambda_deployment.zip` (see [Section 5](#5-packaging--deployment-commands)).
   - **Runtime settings**: Edit handler to `lambda_api.lambda_handler`.
   - **General configuration**: Memory: `512 MB`, Timeout: `30 seconds`.
   - **Environment variables**:
     - `AWS_DEFAULT_REGION` = `us-east-1`
     - `AWS_SQS_QUEUE_URL` = `<SQS URL from Step 3>`
     - `GOOGLE_CREDENTIALS_SECRET_ARN` = `<Secret ARN from Step 2>`
     - `GDRIVE_INPUT_FOLDER_ID` = `1f-WCZqbKkQfzXAClTXT_BaWCinD6skr1`
     - `PUBLIC_WEBHOOK_TOKEN` = `mySecretToken_flipline_2026` (or your chosen token)

---

### Step 11: Amazon API Gateway

1. Navigate to **API Gateway** → Click **Create API**.
2. Under **HTTP API**, click **Build**.
3. Configure API:
   - Click **Add integration** → Choose **Lambda**.
   - **Lambda function**: Select `flipline-api`.
   - **API name**: `flipline-api-gateway`.
4. Configure Routes:
   - **Method**: `ANY`
   - **Resource path**: `/{proxy+}`
   - **Integration target**: `flipline-api`
5. Configure Stages:
   - **Stage name**: `prod`
   - **Auto-deploy**: Enabled.
6. Click **Create**.
7. **Obtain Public URL**:
   - Go to **Stages** → Click **prod** → Copy the **Invoke URL**.
   - Example: `https://<api-id>.execute-api.us-east-1.amazonaws.com/prod`
   👉 Add this to `.env` as `PUBLIC_API_URL`.
8. **Grant Invoke Permission**:
   - In Lambda `flipline-api` → **Configuration** → **Resource-based policy statements** → Add permission:
     - Principal: `apigateway.amazonaws.com`
     - Action: `lambda:InvokeFunction`

---

### Step 12: AWS Lambda — `flipline-webhook-renewer`

Google Drive webhook push subscriptions expire every 7 days. This Lambda automatically renews the subscription.

1. Navigate to **Lambda** → Click **Create function**.
2. Settings:
   - **Function name**: `flipline-webhook-renewer`
   - **Runtime**: `Python 3.11`
   - **Execution role**: `Use an existing role` → Select `flipline-lambda-role`
3. Click **Create function**.
4. Configure the function:
   - **Code**: Upload the **same** `lambda_deployment.zip`.
   - **Runtime settings**: Edit handler to `src.webhook_renewer.lambda_handler`.
   - **General configuration**: Memory: `512 MB`, Timeout: `30 seconds`.
   - **Environment variables**:
     - `AWS_DEFAULT_REGION` = `us-east-1`
     - `GOOGLE_CREDENTIALS_SECRET_ARN` = `<Secret ARN from Step 2>`
     - `GDRIVE_INPUT_FOLDER_ID` = `1f-WCZqbKkQfzXAClTXT_BaWCinD6skr1`
     - `PUBLIC_WEBHOOK_TOKEN` = `mySecretToken_flipline_2026`
     - `PUBLIC_API_URL` = `<Invoke URL from Step 11>`

---

### Step 13: Amazon EventBridge Scheduler

1. Navigate to **Amazon EventBridge** → **Scheduler** → **Schedules** → Click **Create schedule**.
2. **Schedule details**:
   - **Schedule name**: `flipline-webhook-renewal`
   - **Schedule type**: `Recurring schedule`
   - **Schedule pattern**: `Rate-based schedule`
   - **Rate expression**: `6 days`
   - **Flexible time window**: `Off`
3. **Target**:
   - **Target API**: `AWS Lambda Invoke`
   - **Lambda function**: `flipline-webhook-renewer`
4. Click **Next** → Complete review → Click **Create schedule**.

---

## 5. Packaging & Deployment Commands

Run these packaging commands in your terminal (Linux/macOS bash or Windows PowerShell) from the project root to generate the Lambda deployment archive.

### Linux / macOS / WSL Bash:
```bash
# Simply run the automated build script:
./build_lambda.sh

# Or manually:
rm -rf lambda_package lambda_deployment.zip
uv pip install -r requirements_lambda.txt --target lambda_package/
cp -r src lambda_package/src
cp -r config lambda_package/config
cp lambda_api.py lambda_package/
cp api.py lambda_package/
cp config.py lambda_package/
cp log.py lambda_package/ 2>/dev/null || true
cd lambda_package && zip -rq ../lambda_deployment.zip . && cd ..
echo "✅ Generated lightweight lambda_deployment.zip (~40MB) successfully!"
```

### Windows PowerShell:
```powershell
# Clean up
Remove-Item -Recurse -Force lambda_package, lambda_deployment.zip -ErrorAction SilentlyContinue

# Install dependencies (using uv or pip)
uv pip install -r requirements.txt --target lambda_package/
if (-not $?) { pip install -r requirements.txt -t lambda_package/ --quiet }

# Copy files
Copy-Item -Recurse src lambda_package/src
Copy-Item -Recurse config lambda_package/config
Copy-Item api.py lambda_package/
Copy-Item config.py lambda_package/
Copy-Item log.py lambda_package/ -ErrorAction SilentlyContinue

# Create ZIP
Compress-Archive -Path lambda_package\* -DestinationPath lambda_deployment.zip -Force

Write-Host "✅ Generated lambda_deployment.zip successfully!"
```

### Uploading to AWS Lambda:
Upload `lambda_deployment.zip` to **both** Lambda functions using the AWS CLI or AWS Console:
```bash
aws lambda update-function-code --function-name flipline-api --zip-file fileb://lambda_deployment.zip --region us-east-1
aws lambda update-function-code --function-name flipline-webhook-renewer --zip-file fileb://lambda_deployment.zip --region us-east-1
```

---

## 6. Post-Deployment Initial Webhook Activation

Once both Lambdas and API Gateway are deployed:

1. Ensure your local `.env` has:
   ```env
   PUBLIC_API_URL=https://<your-api-id>.execute-api.us-east-1.amazonaws.com/prod
   PUBLIC_WEBHOOK_TOKEN=mySecretToken_flipline_2026
   GDRIVE_INPUT_FOLDER_ID=1f-WCZqbKkQfzXAClTXT_BaWCinD6skr1
   GOOGLE_CREDENTIALS_SECRET_ARN=arn:aws:secretsmanager:us-east-1:<ACC>:secret:flipline/google-credentials-xxx
   ```
2. Execute the webhook registration script:
   ```bash
   python register_webhook.py
   ```
3. Output confirms registration:
   ```
   ✅ Initial webhook registered successfully! Channel ID: 3e82fc91-xxxx-xxxx-xxxx-xxxxxxxxxxxx
      Expires: 1726050000000
      🔄 Automatic renewal is active via EventBridge Scheduler (every 6 days). No manual re-runs needed!
   ```

> 💡 **Why no manual re-run?**
> In Step 12 & 13, you deployed `flipline-webhook-renewer` Lambda and an EventBridge Scheduler that automatically calls it every 6 days. This permanently auto-renews the webhook with Google Drive before the 7-day expiration. You only run `register_webhook.py` **once** during setup!

---

## 7. End-to-End Verification & Monitoring

### 1. Test Health Endpoint
```bash
curl https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/health
# Expected Response: {"status": "ok"}
```

### 2. Monitor ECS Fargate Logs Live
```bash
aws logs tail /ecs/flipline-worker --follow
```

### 3. Trigger End-to-End Test
1. Upload a short sample `.mp4` video to the Google Drive Input folder (`GDRIVE_INPUT_FOLDER_ID`).
2. Verify Google Drive triggers API Gateway → Lambda `flipline-api` puts job on `Flipline_Jobs` SQS.
3. EventBridge Pipe triggers ECS Fargate `flipline-worker-task`.
4. The worker processes the video, writes highlights to DynamoDB, uploads results to Cloudinary, deletes the SQS message, and safely shuts down.

---

## 8. DevOps Sign-Off Checklist

- [ ] **IAM Roles Provisioned**:
  - [ ] `flipline-lambda-role`
  - [ ] `flipline-ecs-task-role`
  - [ ] `ecsTaskExecutionRole`
- [ ] **Secrets Manager Created**:
  - [ ] `flipline/google-credentials` contains valid JSON.
- [ ] **SQS Created**:
  - [ ] `Flipline_Jobs` (Visibility timeout: 3600s).
- [ ] **ECR & Worker Container**:
  - [ ] Repository `flipline-worker` created.
  - [ ] Docker image built and pushed to ECR.
- [ ] **ECS & Fargate Configured**:
  - [ ] Cluster `Flipline-Cluster` active.
  - [ ] Task definition `flipline-worker-task` created (4 vCPU / 8 GB RAM, logging, env vars).
  - [ ] EventBridge Pipe `flipline-sqs-to-fargate` active (public IP enabled).
- [ ] **Serverless API Deployed**:
  - [ ] Lambda `flipline-api` uploaded and configured (`api.lambda_handler`).
  - [ ] API Gateway HTTP API integrated and stage `prod` deployed.
  - [ ] Invoke permission granted from API Gateway to Lambda.
- [ ] **Webhook Auto-Renewal Deployed**:
  - [ ] Lambda `flipline-webhook-renewer` uploaded (`src.webhook_renewer.lambda_handler`).
  - [ ] EventBridge Scheduler running recurring rule every 6 days.
- [ ] **Initial Registration Completed**:
  - [ ] `python register_webhook.py` executed successfully.
- [ ] **Pipeline Verified**:
  - [ ] Test video processed end-to-end with clean CloudWatch logs.
