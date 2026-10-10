# Run the review engine on one lab case (main..branch); saves workspace\lab-results\<case>-ocr.json
param(
    [Parameter(Mandatory = $true)][string]$Branch,
    [Parameter(Mandatory = $true)][string]$Case,
    [long]$TokenBudget = 1500000
)
$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$repo = Join-Path $root "workspace\lab-repo"
$outDir = Join-Path $root "workspace\lab-results"
New-Item -ItemType Directory -Force $outDir | Out-Null
$out = Join-Path $outDir "$Case-ocr.json"
$log = Join-Path $outDir "$Case-ocr.log"

$exe = Get-ChildItem "$env:APPDATA\npm\node_modules\@alibaba-group" -Recurse -Filter opencodereview.exe |
    Select-Object -First 1 -ExpandProperty FullName

Push-Location $repo
try {
    & $exe review --from main --to $Branch --format json --output $out --audience agent `
        --max-tokens-budget $TokenBudget --color never *> $log
    Write-Output "ocr exit code: $LASTEXITCODE"
}
finally {
    Pop-Location
}
if (Test-Path $out) { Write-Output "result: $out ($((Get-Item $out).Length) bytes)" } else { Write-Output "no result file; see $log" }
