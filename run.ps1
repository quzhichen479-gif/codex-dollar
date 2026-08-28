param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $MeterArgs
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $projectRoot "src"
$env:PYTHONUTF8 = "1"

$candidates = @()
if ($env:CODEX_METER_PYTHON) {
    $candidates += $env:CODEX_METER_PYTHON
}
$candidates += (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")
$candidates += "python"
$candidates += "python3"

$pythonExe = $null
foreach ($candidate in $candidates) {
    if ([System.IO.Path]::IsPathRooted($candidate)) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $pythonExe = $candidate
            break
        }
    } elseif (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $pythonExe = $candidate
        break
    }
}

if (-not $pythonExe) {
    throw "未找到 Python 3.10+。请安装 Python，或设置 CODEX_METER_PYTHON 指向 python.exe。"
}

& $pythonExe -m codex_meter @MeterArgs
exit $LASTEXITCODE
