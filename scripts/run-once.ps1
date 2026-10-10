# Review one PR right now as the Alex GitHub App, from this machine (no Render needed).
# Secrets are read from local files and never printed.
param(
    [Parameter(Mandatory = $true)][string]$Repo,
    [Parameter(Mandatory = $true)][int]$Pr
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    $pem = Get-ChildItem workspace\secrets -Filter *.pem | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $line = Select-String -Path evals\aacr\aacr-bench\evaluation\.env -Pattern '^OCR_LLM_TOKEN=' | Select-Object -First 1
    $env:ALEX_APP_ID = "5263028"
    $env:ALEX_APP_PRIVATE_KEY_FILE = $pem.FullName
    $env:ALEX_LLM_API_KEY = $line.Line.Split('=', 2)[1].Trim()
    $env:ALEX_ALLOWED_ACCOUNTS = "niihhhall"
    $env:ALEX_DATA_DIR = "$root\workspace\server-data"
    $env:ALEX_OPENSSL = "C:\Program Files\Git\usr\bin\openssl.exe"
    $env:ALEX_ENGINE_CMD = (Get-ChildItem "$env:APPDATA\npm\node_modules\@alibaba-group" -Recurse -Filter opencodereview.exe |
        Select-Object -First 1 -ExpandProperty FullName)
    $env:PYTHONIOENCODING = "utf-8"
    python -m alex.server once --repo $Repo --pr $Pr *>&1 | ForEach-Object { "$_" }
}
finally {
    Pop-Location
}
