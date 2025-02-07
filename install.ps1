# Requires -RunAsAdministrator

# Function to write colored output
function Write-Color {
    param (
        [string]$Text,
        [string]$Color = "White"
    )
    Write-Host $Text -ForegroundColor $Color
}

# Check for Visual C++ Redistributable
Write-Color "Checking system dependencies..." "Cyan"
$vcRedistKey = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" -ErrorAction SilentlyContinue
if (-not $vcRedistKey) {
    Write-Color "Microsoft Visual C++ Redistributable is required." "Yellow"
    Write-Color "Please download and install it from:" "Yellow"
    Write-Color "https://aka.ms/vs/17/release/vc_redist.x64.exe" "Blue"
    Write-Host ""
}

# Check for executable
$executable = "ssh-commander-windows-x64.exe"
if (-not (Test-Path $executable) -and (Test-Path "$executable.zip")) {
    Expand-Archive "$executable.zip" -DestinationPath .
}

if (-not (Test-Path $executable)) {
    Write-Color "Error: Executable not found. Please ensure you're in the directory with $executable or its zip file." "Red"
    exit 1
}

# Create installation directories
$installDir = "$env:ProgramFiles\SSH Commander"
$configDir = "$env:USERPROFILE\.config\ssh-commander"

# Create directories if they don't exist
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
New-Item -ItemType Directory -Force -Path $configDir | Out-Null

# Copy executable
Copy-Item $executable -Destination "$installDir\ssh-commander.exe" -Force

# Add to PATH if not already there
$currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($currentPath -notlike "*$installDir*") {
    [Environment]::SetEnvironmentVariable(
        "Path",
        "$currentPath;$installDir",
        "Machine"
    )
    Write-Color "Added SSH Commander to system PATH" "Green"
}

Write-Host ""
Write-Color "✓ SSH Commander has been installed!" "Green"
Write-Host ""
Write-Color "Available commands:" "Cyan"
Write-Host "  " -NoNewline
Write-Color "ssh-commander add" "Yellow" -NoNewline
Write-Host "             - Add a new server"
Write-Host "  " -NoNewline
Write-Color "ssh-commander remove" "Yellow" -NoNewline
Write-Host " SERVER  - Remove a server"
Write-Host "  " -NoNewline
Write-Color "ssh-commander list" "Yellow" -NoNewline
Write-Host "           - View configured servers"
Write-Host "  " -NoNewline
Write-Color "ssh-commander --help" "Yellow" -NoNewline
Write-Host "         - Show help and examples"
Write-Host ""
