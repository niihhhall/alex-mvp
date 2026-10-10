# Render the Alex card for a lab case locally, using the live card model.
# Reads the API key from evals\aacr\aacr-bench\evaluation\.env (never printed).
param(
    [Parameter(Mandatory = $true)][string]$Case,
    [Parameter(Mandatory = $true)][string]$Branch,
    [string]$Title = "Lab case",
    [switch]$NoLlm
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    $lab = "workspace\lab-repo"
    $results = "workspace\lab-results"
    $diff = "$results\$Case.diff"
    git -C $lab diff main $Branch | Out-File -Encoding utf8NoBOM $diff
    $envFile = "evals\aacr\aacr-bench\evaluation\.env"
    $line = Select-String -Path $envFile -Pattern '^OCR_LLM_TOKEN=' | Select-Object -First 1
    $env:ALEX_LLM_KEY = $line.Line.Split('=', 2)[1].Trim()
    $env:ALEX_MODEL = "accounts/fireworks/models/deepseek-v4p1-flash"
    $pyArgs = @("-m", "alex.main", "preview", "--ocr-json", "$results\$Case-ocr.json", "--diff", $diff,
        "--title", $Title, "--head", (git -C $lab rev-parse $Branch), "--out", "workspace\previews\$Case")
    if ($NoLlm) { $pyArgs += "--no-llm" }
    python @pyArgs *>&1 | ForEach-Object { "$_" }
}
finally {
    Pop-Location
}
