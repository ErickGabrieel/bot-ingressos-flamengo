param(
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$temporaryPath = Join-Path $projectRoot ".build-temp"

Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Ambiente .venv não encontrado. Crie-o antes de gerar o aplicativo."
}

New-Item -ItemType Directory -Force -Path $temporaryPath | Out-Null
$env:TEMP = $temporaryPath
$env:TMP = $temporaryPath
$env:PIP_CACHE_DIR = Join-Path $temporaryPath "pip-cache"

& $pythonPath -c "import PyInstaller"

if ($LASTEXITCODE -ne 0) {
    & $pythonPath -m pip install --no-cache-dir pyinstaller

    if ($LASTEXITCODE -ne 0) {
        throw "Não foi possível instalar o PyInstaller."
    }
}

$bundleMode = "--onedir"

if ($OneFile) {
    $bundleMode = "--onefile"
}

& $pythonPath -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name TicketBOT `
    --collect-all playwright `
    $bundleMode `
    app.py

if ($LASTEXITCODE -ne 0) {
    throw "O PyInstaller não conseguiu gerar o aplicativo."
}

if ($OneFile) {
    if (-not (Test-Path -LiteralPath "dist\TicketBOT.exe")) {
        throw "O executável final não foi encontrado."
    }

    Write-Host "Aplicativo gerado em dist\TicketBOT.exe"
}
else {
    if (-not (Test-Path -LiteralPath "dist\TicketBOT\TicketBOT.exe")) {
        throw "O executável final não foi encontrado."
    }

    Copy-Item `
        -LiteralPath "LEIA-ME.txt" `
        -Destination "dist\TicketBOT\LEIA-ME.txt" `
        -Force
    Write-Host "Aplicativo gerado em dist\TicketBOT\TicketBOT.exe"
}
