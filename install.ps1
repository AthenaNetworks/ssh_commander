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
$configDir = "$env:USERPROFILE\.config\ssh-commander"

# Create directories if they don't exist
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

# Copy executable
Copy-Item "ssh-commander-windows-x64.exe" -Destination "$installDir\ssh-commander.exe" -Force

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

Write-Host ""
Write-Host "SSH Commander has been installed!"
Write-Host ""
Write-Host "To add a new server, use: ssh-commander add"
Write-Host "To remove a server, use: ssh-commander remove [SERVER]"
Write-Host "To view a list of configured servers, use: ssh-commander list"
Write-Host "For more information, use: ssh-commander --help"
Write-Host ""
