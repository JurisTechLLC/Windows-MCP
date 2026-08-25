# Start Windows-MCP Server
# This script launches the Windows-MCP MCP server for desktop automation.
# 
# Usage:
#   .\start-windows-mcp.ps1
#
# Optional parameters:
#   -Transport   : Communication transport (stdio, sse, streamable-http). Default: stdio
#   -Host        : Host to bind (for sse/streamable-http). Default: localhost
#   -Port        : Port to bind (for sse/streamable-http). Default: 8000
#   -Debug       : Enable debug logging. Default: $false
#   -Token       : Bearer token for HTTP authentication. Default: none
#
# Examples:
#   .\start-windows-mcp.ps1                          # Default: stdio transport
#   .\start-windows-mcp.ps1 -Transport sse           # SSE transport on localhost:8000
#   .\start-windows-mcp.ps1 -Transport sse -Port 9000 -Debug
#   .\start-windows-mcp.ps1 -Transport sse -Token "your-secret-token"

param(
    [string]$Transport = "stdio",
    [string]$Host = "localhost",
    [int]$Port = 8000,
    [switch]$Debug,
    [string]$Token
)

# Build command arguments
$args = @("run", "windows-mcp", "serve", "--transport", $Transport)

if ($Transport -ne "stdio") {
    $args += "--host", $Host, "--port", $Port
}

if ($Debug) {
    $args += "--debug"
}

if ($Token) {
    $args += "--token", $Token
}

# Run the server
Write-Host "Starting Windows-MCP server..."
Write-Host "Transport: $Transport"
if ($Transport -ne "stdio") {
    Write-Host "Address: $Host`:$Port"
}
if ($Debug) {
    Write-Host "Debug mode: enabled"
}
Write-Host ""

& uv @args
