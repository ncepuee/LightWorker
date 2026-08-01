$ErrorActionPreference = "Stop"

$env:LIGHTWORKER_HOME = Join-Path $env:LOCALAPPDATA "LightWorker"
$env:PYTHONPATH = $PSScriptRoot
$env:PYTHONUTF8 = "1"

$python = (Get-Command python -ErrorAction Stop).Source
& $python -m lightworker web @args
