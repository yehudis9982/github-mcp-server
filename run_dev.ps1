# MCP Server - Development Mode
# Runs the server with MCP Inspector for testing

$env:Path = "C:\Users\01\.local\bin;$env:Path"
Write-Host "Starting MCP Server in Development Mode..." -ForegroundColor Green
Write-Host "MCP Inspector will open in your browser" -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

cd $PSScriptRoot
uv run mcp dev server.py
