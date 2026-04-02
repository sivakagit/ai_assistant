Write-Host ""
Write-Host "AI Model Setup"
Write-Host ""

# Detect RAM

$ramBytes = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
$ramGB = [math]::Round($ramBytes / 1GB)

# Detect GPU

$gpu = Get-CimInstance Win32_VideoController

$hasGPU = $false

foreach ($g in $gpu) {

    if ($g.Name -notmatch "Microsoft Basic") {

        $hasGPU = $true

    }

}

Write-Host "Detected RAM:" $ramGB "GB"
Write-Host "GPU detected:" $hasGPU

Write-Host ""

# Suggest model

if ($ramGB -lt 8) {

    $suggested = "phi3:mini"

}
elseif ($ramGB -lt 16) {

    $suggested = "qwen2.5:3b"

}
else {

    if ($hasGPU) {

        $suggested = "llama3:8b"

    }
    else {

        $suggested = "qwen2.5:3b"

    }

}

Write-Host "Suggested model:" $suggested

Write-Host ""
Write-Host "Available models:"
Write-Host "1 - phi3:mini"
Write-Host "2 - qwen2.5:3b"
Write-Host "3 - llama3:8b"
Write-Host ""

$choice = Read-Host "Press Enter to use suggested model or type 1/2/3"

switch ($choice) {

    "1" { $model = "phi3:mini" }

    "2" { $model = "qwen2.5:3b" }

    "3" { $model = "llama3:8b" }

    default { $model = $suggested }

}

Write-Host ""
Write-Host "Selected model:" $model
Write-Host ""

# Check if already installed

$installed = ollama list

if ($installed -match $model) {

    Write-Host "Model already installed."
    exit

}

Write-Host ""
Write-Host "Downloading model..."
Write-Host ""

$start = Get-Date

ollama pull $model

$end = Get-Date

$seconds = ($end - $start).TotalSeconds

Write-Host ""
Write-Host "Download completed"
Write-Host "Time taken:" $seconds "seconds"

Start-Sleep 2