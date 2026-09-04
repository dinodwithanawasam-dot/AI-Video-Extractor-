$ErrorActionPreference = "Stop"

# Load AWS credentials from .env if present
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)\s*=\s*(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($name -like "AWS_*") {
                [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
            }
        }
    }
}

Write-Host ">> Starting Deployment for flipline-worker..." -ForegroundColor Cyan

$REGION = "us-east-1"
$IMAGE_NAME = "flipline-worker"

# 1. Get AWS Account ID
Write-Host ">> [1/5] Fetching AWS Account ID..." -ForegroundColor Yellow
$ACCOUNT = (aws sts get-caller-identity --query Account --output text).Trim()
$ECR_URL = "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

Write-Host ">> AWS Account ID: $ACCOUNT" -ForegroundColor Green

# 2. Login Docker to ECR
Write-Host ">> [2/5] Logging into AWS ECR..." -ForegroundColor Yellow
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_URL
if ($LASTEXITCODE -ne 0) { Write-Error "ECR Login failed"; exit 1 }

# 3. Build the worker Docker image
Write-Host ">> [3/5] Building Docker image (this may take a few minutes)..." -ForegroundColor Yellow
docker build -t $IMAGE_NAME -f Docker/Dockerfile .
if ($LASTEXITCODE -ne 0) { Write-Error "Docker build failed! Make sure Docker Desktop is running."; exit 1 }

# 4. Tag the image
Write-Host ">> [4/5] Tagging image..." -ForegroundColor Yellow
docker tag "${IMAGE_NAME}:latest" "${ECR_URL}/${IMAGE_NAME}:latest"
if ($LASTEXITCODE -ne 0) { Write-Error "Docker tag failed"; exit 1 }

# 5. Push to ECR
Write-Host ">> [5/5] Pushing image to ECR..." -ForegroundColor Yellow
docker push "${ECR_URL}/${IMAGE_NAME}:latest"
if ($LASTEXITCODE -ne 0) { Write-Error "Docker push failed"; exit 1 }

Write-Host ">> [SUCCESS] Deployment Complete! Image successfully pushed to ECR." -ForegroundColor Green
