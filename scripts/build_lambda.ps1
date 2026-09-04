# ==============================================================================
# Build Script for Flipline AWS Lambda Deployment Package
# Packages a lightweight (~15MB) zip archive for:
#   1. flipline-api (Handler: lambda_api.lambda_handler)
#   2. flipline-webhook-renewer (Handler: src.webhook_renewer.lambda_handler)
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host ">> [1/4] Cleaning previous packaging artifacts..." -ForegroundColor Cyan
if (Test-Path lambda_package) {
    cmd /c "rmdir /s /q lambda_package"
}
Remove-Item -Force lambda_deployment.zip -ErrorAction SilentlyContinue

Write-Host ">> [2/4] Installing lightweight Lambda dependencies via uv (Target: Linux x86_64, Python 3.11)..." -ForegroundColor Cyan
uv pip install --python-platform x86_64-manylinux2014 --python-version 3.11 -r requirements_lambda.txt --target lambda_package/
if ($LASTEXITCODE -ne 0) {
    pip install --platform manylinux2014_x86_64 --target lambda_package/ --implementation cp --python-version 3.11 --only-binary=:all: -r requirements_lambda.txt
}

Write-Host ">> Pruning redundant files (AWS Lambda already includes boto3/botocore)..." -ForegroundColor Cyan
Remove-Item -Recurse -Force lambda_package/boto3*, lambda_package/botocore*, lambda_package/s3transfer* -ErrorAction SilentlyContinue
if (Test-Path lambda_package/googleapiclient/discovery_cache/documents) {
    Get-ChildItem lambda_package/googleapiclient/discovery_cache/documents -Exclude "drive*" | Remove-Item -Force -ErrorAction SilentlyContinue
}
Get-ChildItem -Path lambda_package -Include "*dist-info", "__pycache__" -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ">> [3/4] Copying Lambda source code files..." -ForegroundColor Cyan
Copy-Item -Recurse src lambda_package/src
Copy-Item -Recurse config lambda_package/config
Copy-Item lambda_api.py lambda_package/
Copy-Item api.py lambda_package/
Copy-Item config.py lambda_package/
Copy-Item log.py lambda_package/ -ErrorAction SilentlyContinue

Write-Host ">> [4/4] Fast compressing deployment archive via Python..." -ForegroundColor Cyan
.venv\Scripts\python.exe -c @"
import zipfile, os
from pathlib import Path

pkg_dir = Path('lambda_package')
zip_path = Path('lambda_deployment.zip')

with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
    for root, dirs, files in os.walk(pkg_dir):
        for file in files:
            full_path = Path(root) / file
            rel_path = full_path.relative_to(pkg_dir)
            zipf.write(full_path, arcname=str(rel_path))
"@

$zipSize = (Get-Item lambda_deployment.zip).Length / 1MB
Write-Host ("`n[SUCCESS] Generated lambda_deployment.zip successfully! Size: {0:N2} MB" -f $zipSize) -ForegroundColor Green
Write-Host ">> Handlers to configure in AWS Lambda Console:" -ForegroundColor Yellow
Write-Host "   - flipline-api:              lambda_api.lambda_handler" -ForegroundColor White
Write-Host "   - flipline-webhook-renewer:  src.webhook_renewer.lambda_handler`n" -ForegroundColor White
