# Requires -RunAsAdministrator

# Ensure we're in the right directory
if (-not (Test-Path "ssh-commander") -and (Test-Path "ssh-commander-windows-x64.zip")) {
    Expand-Archive "ssh-commander-windows-x64.zip" -DestinationPath .
}

if (-not (Test-Path "ssh-commander")) {
    Write-Error "Error: ssh-commander directory not found. Please ensure you're in the directory where you extracted the archive."
    exit 1
}

Set-Location ssh-commander

# Create installation directories
$installDir = "$env:ProgramFiles\SSH Commander"
$configDir = "$env:ProgramData\SSH Commander"

# Create directories if they don't exist
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

# Copy executable
Copy-Item "ssh-commander-windows-x64.exe" -Destination "$installDir\ssh-commander.exe" -Force

# Copy example config if no config exists
if (-not (Test-Path "$configDir\servers.yaml")) {
    Copy-Item "servers.yaml.example" -Destination "$configDir\servers.yaml" -Force
    Write-Host "Created example config at $configDir\servers.yaml"
}

# Add to PATH if not already there
$currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($currentPath -notlike "*$installDir*") {
    [Environment]::SetEnvironmentVariable(
        "Path",
        "$currentPath;$installDir",
        "Machine"
    )
    Write-Host "Added SSH Commander to system PATH"
}

Write-Host "Installation complete!"
Write-Host "1. Edit your server configuration:"
Write-Host "   notepad $configDir\servers.yaml"
Write-Host ""
Write-Host "2. Test the installation:"
Write-Host "   ssh-commander --config $configDir\servers.yaml list"
