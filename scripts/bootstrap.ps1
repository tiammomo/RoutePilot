param(
    [string]$PythonVersion = "3.13",
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "[bootstrap] $Message" -ForegroundColor Cyan
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

# Resolve uv executable
$uvPath = $null
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) {
    $uvPath = $uvCmd.Source
} else {
    $fallback = Join-Path $env:USERPROFILE ".local\\bin\\uv.exe"
    if (Test-Path $fallback) {
        $uvPath = $fallback
    }
}

if (-not $uvPath) {
    throw "uv not found. Install uv or add it to PATH."
}

Write-Step "Using uv at: $uvPath"
& $uvPath --version

Write-Step "Ensure Python $PythonVersion is installed"
& $uvPath python install $PythonVersion

$venvPython = Join-Path $RepoRoot ".venv\\Scripts\\python.exe"
$needRecreate = $false

if (Test-Path $venvPython) {
    $venvVersion = (& $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($venvVersion -ne $PythonVersion) {
        Write-Step "Existing .venv uses Python $venvVersion, recreating with Python $PythonVersion"
        $needRecreate = $true
    }
} else {
    $needRecreate = $true
}

if ($needRecreate) {
    & $uvPath venv .venv --python $PythonVersion --clear
}

if (-not (Test-Path $venvPython)) {
    throw "Failed to create .venv at $venvPython"
}

Write-Step "Install Python dependencies"
& $uvPath pip install --python $venvPython -r requirements.txt

if (-not $SkipFrontend) {
    Write-Step "Install frontend dependencies"
    Push-Location frontend
    npm install
    Pop-Location
}

$llmConfig = Join-Path $RepoRoot "config\\llm_config.yaml"
$llmTemplate = Join-Path $RepoRoot "config\\llm_config.yaml.example"
if (-not (Test-Path $llmConfig)) {
    if (Test-Path $llmTemplate) {
        Copy-Item $llmTemplate $llmConfig
        Write-Step "Created config/llm_config.yaml from template. Fill in API keys before running API."
    } else {
        Write-Warning "Missing config/llm_config.yaml and template config/llm_config.yaml.example"
    }
} else {
    Write-Step "Config check passed: config/llm_config.yaml exists"
}

Write-Step "Bootstrap complete"
Write-Host "Activate venv: .\\.venv\\Scripts\\activate" -ForegroundColor Green
Write-Host "Run tests: .\\.venv\\Scripts\\python.exe -m pytest tests -q" -ForegroundColor Green
