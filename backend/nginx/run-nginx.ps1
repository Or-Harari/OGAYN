# Runs Nginx in Docker, mapping localhost:8088 to the proxy
# Requires Docker Desktop on Windows

$ErrorActionPreference = "Stop"

# Resolve repo-relative path to config
$repoRoot = Split-Path -Path $PSScriptRoot -Parent
$confPath = Join-Path -Path $PSScriptRoot -ChildPath "nginx.conf"

# Pull nginx image if missing
Write-Host "Starting Nginx reverse proxy (localhost:8088) ..."
docker pull nginx:stable

# Remove previous container if exists
if ((docker ps -a --format '{{.Names}}') -contains 'ft-nginx-proxy') {
    docker rm -f ft-nginx-proxy | Out-Null
}

# Run Nginx with mounted config
$cmd = @(
    "docker", "run", "-d",
    "--name", "ft-nginx-proxy",
    "-p", "127.0.0.1:8088:80",
    "-v", "${confPath}:/etc/nginx/nginx.conf:ro",
    "nginx:stable"
)

& $cmd[0] $cmd[1] $cmd[2] $cmd[3] $cmd[4] $cmd[5] $cmd[6] $cmd[7] $cmd[8] $cmd[9] $cmd[10] $cmd[11]

Write-Host "Nginx is running. Try http://localhost:8088/"
