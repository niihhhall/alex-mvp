# One-command AACR-Bench runner for Windows.
#
# Examples:
#   .\run.ps1 -Dataset data\pilot.jsonl -RunId pilot
#   .\run.ps1 -Dataset data\pilot.jsonl -RunId pilot-glm -Model accounts/fireworks/models/glm-5p3-flash
#   .\run.ps1 -Dataset data\aacr_bench_full.jsonl -RunId full -Concurrency 4
#   .\run.ps1 -Dataset data\pilot.jsonl -RunId pilot -Stage eval      # re-grade without re-reviewing
param(
    [Parameter(Mandatory = $true)][string]$Dataset,
    [Parameter(Mandatory = $true)][string]$RunId,
    [ValidateSet("all", "review", "eval")][string]$Stage = "all",
    [string]$Model = "",
    [int]$Concurrency = 1,
    [int]$TimeoutMinutes = 20,
    [int]$LineK = 1,
    # Per-PR token cap (input+output). 0 = unlimited. Caps cost but can lower recall on big PRs.
    [long]$TokenBudget = 0
)

$ErrorActionPreference = "Stop"
$evalDir = Join-Path $PSScriptRoot "aacr-bench\evaluation"
$python = Join-Path $evalDir ".venv\Scripts\python.exe"

# The pipeline launches ocr without a shell, so it needs the real .exe, not the npm .cmd shim.
$ocrExe = Get-ChildItem "$env:APPDATA\npm\node_modules\@alibaba-group" -Recurse -Filter opencodereview.exe |
    Select-Object -First 1 -ExpandProperty FullName
if (-not $ocrExe) { throw "opencodereview.exe not found; run: npm install -g @alibaba-group/open-code-review" }

Get-Content (Join-Path $evalDir ".env") | ForEach-Object {
    if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)\s*$') {
        Set-Item -Path "env:$($Matches[1])" -Value $Matches[2].Trim('"')
    }
}
if ($Model) { $env:OCR_LLM_MODEL = $Model }
$env:OCR_MAX_TOKENS_BUDGET = "$TokenBudget"

# Child processes emit UTF-8; force Python to decode it as such on Windows.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# ~/.opencodereview/config.json outranks OCR_LLM_* env vars, so pin the model there
# for the duration of the run and put the original back afterwards.
$cfgPath = Join-Path $env:USERPROFILE ".opencodereview\config.json"
$originalModel = $null
if ((Test-Path $cfgPath) -and $Stage -ne "eval") {
    $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
    $originalModel = $cfg.custom_providers.($cfg.provider).model
    & $ocrExe config set model $env:OCR_LLM_MODEL | Out-Null
}
Write-Host "Reviewer model: $env:OCR_LLM_MODEL | Judge model: $env:JUDGE_MODEL"

Push-Location $evalDir
try {
    & $python -m pipeline run `
        --stage $Stage --reviewer ocr --dataset $Dataset --run-id $RunId `
        --ocr-command $ocrExe --concurrency $Concurrency `
        --timeout-minutes $TimeoutMinutes --line-k $LineK
    if ($LASTEXITCODE -ne 0) { throw "pipeline exited with code $LASTEXITCODE" }
}
finally {
    Pop-Location
    if ($originalModel) { & $ocrExe config set model $originalModel | Out-Null }
}
