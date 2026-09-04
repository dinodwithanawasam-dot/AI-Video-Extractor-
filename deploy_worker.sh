#!/bin/bash
set -e # Exit immediately if a command fails

echo "🚀 Starting Deployment for flipline-worker..."

# Set AWS Region
REGION="us-east-1"
IMAGE_NAME="flipline-worker"

# 1. Get AWS Account ID
echo "🔍 Fetching AWS Account ID..."
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR_URL="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

echo "✅ AWS Account ID: ${ACCOUNT}"

# 2. Login Docker to ECR
echo "🔑 Logging into AWS ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR_URL}

# 3. Build the worker Docker image
echo "🔨 Building Docker image (this is fast if only python files changed)..."
docker build -t ${IMAGE_NAME} -f Docker/Dockerfile .

# 4. Tag the image
echo "🏷️ Tagging image..."
docker tag ${IMAGE_NAME}:latest "${ECR_URL}/${IMAGE_NAME}:latest"

# 5. Push to ECR
echo "☁️ Pushing image to ECR..."
docker push "${ECR_URL}/${IMAGE_NAME}:latest"

echo "🎉 Deployment Complete! The next SQS message will be processed using this new code."
