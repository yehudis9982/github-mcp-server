# MCP Server - Run Script
# This script runs the MCP server with proper environment setup

$env:Path = "C:\Users\01\.local\bin;$env:Path"
Write-Host "Starting MCP Server..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

cd $PSScriptRoot
uv run server.py
