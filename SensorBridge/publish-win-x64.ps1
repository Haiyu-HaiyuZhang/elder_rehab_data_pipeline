Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$project = Join-Path $PSScriptRoot "src/SensorBridge/SensorBridge.csproj"
$output = Join-Path $PSScriptRoot "release/win-x64"
dotnet publish $project -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o $output

Write-Host ""
Write-Host "Published SensorBridge.exe under:"
Write-Host "  release/win-x64"
