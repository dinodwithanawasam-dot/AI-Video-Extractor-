#!/bin/bash
set -e

echo ">> [1/4] Cleaning previous packaging artifacts..."
rm -rf lambda_package lambda_deployment.zip

echo ">> [2/4] Installing lightweight Lambda dependencies (Target: Linux x86_64, Python 3.11)..."
if command -v uv &> /dev/null; then
    uv pip install --python-platform x86_64-manylinux2014 --python-version 3.11 -r requirements_lambda.txt --target lambda_package/
else
    pip install --platform manylinux2014_x86_64 --target lambda_package/ --implementation cp --python-version 3.11 --only-binary=:all: -r requirements_lambda.txt
fi

echo ">> [3/4] Copying Lambda source code files..."
cp -r src lambda_package/src
cp -r config lambda_package/config
cp lambda_api.py lambda_package/
cp api.py lambda_package/
cp config.py lambda_package/
cp log.py lambda_package/ 2>/dev/null || true

echo ">> [4/4] Packaging into zip..."
cd lambda_package && zip -rq ../lambda_deployment.zip . && cd ..

ZIP_SIZE=$(du -h lambda_deployment.zip | cut -f1)
echo "✅ Generated lambda_deployment.zip successfully! (Size: $ZIP_SIZE)"
echo ">> Handlers for AWS Lambda:"
echo "   - flipline-api:              lambda_api.lambda_handler"
echo "   - flipline-webhook-renewer:  src.webhook_renewer.lambda_handler"
