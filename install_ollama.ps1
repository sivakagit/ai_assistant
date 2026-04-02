Write-Host "Checking Ollama installation..."

$ollama = Get-Command ollama -ErrorAction SilentlyContinue

if (-not $ollama) {

    Write-Host "Installing Ollama..."

    Start-Process `
        -FilePath "ollama_installer.exe" `
        -ArgumentList "/S" `
        -Wait

}

Write-Host "Starting Ollama service..."

Start-Process "ollama" "serve"

Start-Sleep 5

Write-Host "Ollama ready."