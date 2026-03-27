param(
    [Parameter(Position = 0)]
    [string]$Task = "help",
    [string]$BaseUrl = "http://localhost:38000",
    [string]$GitSha = "local",
    [string]$GitRef = "refs/heads/main",
    [string]$Owner = "local",
    [string]$PythonBaseImage = "python:3.13-slim",
    [string]$NodeBaseImage = "node:22-alpine"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv Python. Run 'uv venv .venv --python 3.13' and install dependencies first."
}

$staticTargets = @(
    "scripts/export_openapi_snapshot.py",
    "scripts/export_release_manifest.py",
    "scripts/release_harness_scorecard.py",
    "scripts/export_support_bundle.py",
    "scripts/export_sse_contract_snapshot.py",
    "scripts/runtime_backup.py",
    "scripts/runtime_data_utils.py",
    "scripts/runtime_doctor.py",
    "scripts/runtime_prune.py",
    "scripts/runtime_restore.py",
    "web/moyuan_web/app_meta.py",
    "web/moyuan_web/main.py",
    "web/moyuan_web/middleware/__init__.py",
    "web/moyuan_web/observability.py",
    "web/moyuan_web/routes/chat.py",
    "web/moyuan_web/routes/health.py",
    "web/moyuan_web/services/share_service.py",
    "web/moyuan_web/startup_checks.py"
)

function Show-Help {
    @"
Usage:
  .\dev.ps1 <task> [options]

Tasks:
  help                   Show this help.
  backend-unit           Run backend unit tests.
  backend-local          Run backend local smoke tests.
  frontend-lint          Run frontend type/lint checks.
  frontend-test          Run frontend unit tests.
  frontend-build         Build the frontend.
  test                   Run backend + frontend verification slices.
  ruff                   Run local Ruff checks on infra/runtime targets.
  mypy                   Run local mypy checks on infra/runtime targets.
  docstring              Run Python docstring audit.
  complexity             Run hotspot complexity budget gate.
  decision-records       Run ADR / RFC / design-review audit.
  snapshots              Export OpenAPI and SSE contract snapshots.
  release-manifest       Export a local release manifest.
  support-bundle         Export a runtime support bundle.
  infra-check            Run local infra-quality checks, exports, and compose validation when Docker is available.
  backend-image-smoke    Build the backend image locally.
  frontend-image-smoke   Build the frontend image locally.
  container-smoke        Build both backend and frontend images locally.
  compose-up             Run docker compose up --build.
  compose-observability  Run docker compose with the observability profile.
  compose-config         Render compose config for default and observability profiles.

Options:
  -BaseUrl   Base URL used by support-bundle. Default: http://localhost:38000
  -GitSha    Git SHA used by release-manifest. Default: local
  -GitRef    Git ref used by release-manifest. Default: refs/heads/main
  -Owner     Image owner used by release-manifest. Default: local
  -PythonBaseImage  Base image reference used by backend compose/build tasks. Default: python:3.13-slim
  -NodeBaseImage    Base image reference used by frontend compose/build tasks. Default: node:22-alpine
"@ | Write-Host
}

function Test-DockerAvailable {
    return $null -ne (Get-Command docker -ErrorAction SilentlyContinue)
}

function Ensure-PythonModule {
    param(
        [string]$ModuleName,
        [string]$PackageName = $ModuleName
    )

    & $python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$ModuleName') else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Missing Python module '$PackageName'. Install dev dependencies with 'uv pip install -r requirements-dev.txt'."
    }
}

function Invoke-FrontendCommand {
    param([string[]]$Arguments)
    Push-Location (Join-Path $PSScriptRoot "frontend")
    try {
        & npm @Arguments
    }
    finally {
        Pop-Location
    }
}

function Run-Ruff {
    Ensure-PythonModule -ModuleName "ruff" -PackageName "ruff"
    & $python -m ruff check --config ruff.toml @staticTargets
}

function Run-Mypy {
    Ensure-PythonModule -ModuleName "mypy" -PackageName "mypy"
    & $python -m mypy --config-file mypy.ini @staticTargets
}

function Run-Docstring {
    & $python scripts/docstring_audit.py --strict
}

function Run-Complexity {
    & $python scripts/complexity_budget.py --strict
}

function Run-DecisionRecords {
    & $python scripts/decision_record_audit.py --strict
}

function Run-Snapshots {
    & $python scripts/export_openapi_snapshot.py
    & $python scripts/export_sse_contract_snapshot.py
}

function Run-ReleaseManifest {
    & $python scripts/export_release_manifest.py --git-sha $GitSha --git-ref $GitRef --owner $Owner
}

function Run-ReleaseHarnessScorecard {
    & $python scripts/release_harness_scorecard.py --strict
}

function Run-SupportBundle {
    & $python scripts/export_support_bundle.py --base-url $BaseUrl
}

function Invoke-ComposeCommand {
    param([string[]]$Arguments)

    $originalPythonBaseImage = $env:PYTHON_BASE_IMAGE
    $originalNodeBaseImage = $env:NODE_BASE_IMAGE
    $hadPythonBaseImage = Test-Path Env:PYTHON_BASE_IMAGE
    $hadNodeBaseImage = Test-Path Env:NODE_BASE_IMAGE

    $env:PYTHON_BASE_IMAGE = $PythonBaseImage
    $env:NODE_BASE_IMAGE = $NodeBaseImage

    try {
        & docker compose @Arguments
    }
    finally {
        if ($hadPythonBaseImage) {
            $env:PYTHON_BASE_IMAGE = $originalPythonBaseImage
        }
        else {
            Remove-Item Env:PYTHON_BASE_IMAGE -ErrorAction SilentlyContinue
        }

        if ($hadNodeBaseImage) {
            $env:NODE_BASE_IMAGE = $originalNodeBaseImage
        }
        else {
            Remove-Item Env:NODE_BASE_IMAGE -ErrorAction SilentlyContinue
        }
    }
}

function Run-ComposeConfig {
    Invoke-ComposeCommand @("config")
    Invoke-ComposeCommand @("--profile", "observability", "config")
}

function Get-BuildCreatedAt {
    return (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Run-BackendImageSmoke {
    docker build `
        --file Dockerfile.backend `
        --build-arg "PYTHON_BASE_IMAGE=$PythonBaseImage" `
        --build-arg "APP_BUILD_SHA=$GitSha" `
        --build-arg "APP_BUILD_CREATED_AT=$(Get-BuildCreatedAt)" `
        --tag moyuan-backend:local .
}

function Run-FrontendImageSmoke {
    docker build `
        --file frontend/Dockerfile `
        --build-arg "NODE_BASE_IMAGE=$NodeBaseImage" `
        --build-arg "NEXT_PUBLIC_API_BASE=http://localhost:38000" `
        --build-arg "INTERNAL_API_BASE=http://backend:38000" `
        --build-arg "APP_BUILD_SHA=$GitSha" `
        --build-arg "APP_BUILD_CREATED_AT=$(Get-BuildCreatedAt)" `
        --tag moyuan-frontend:local ./frontend
}

switch ($Task.ToLowerInvariant()) {
    "help" { Show-Help }
    "backend-unit" { & $python -m pytest tests -m "unit and not local and not external_api" -q }
    "backend-local" { & $python -m pytest tests -m "local and not external_api" -q }
    "frontend-lint" { Invoke-FrontendCommand @("run", "lint") }
    "frontend-test" { Invoke-FrontendCommand @("run", "test:run") }
    "frontend-build" { Invoke-FrontendCommand @("run", "build") }
    "test" {
        & $python -m pytest tests -m "unit and not local and not external_api" -q
        & $python -m pytest tests -m "local and not external_api" -q
        Invoke-FrontendCommand @("run", "lint")
        Invoke-FrontendCommand @("run", "test:run")
        Invoke-FrontendCommand @("run", "build")
    }
    "ruff" { Run-Ruff }
    "mypy" { Run-Mypy }
    "docstring" { Run-Docstring }
    "complexity" { Run-Complexity }
    "decision-records" { Run-DecisionRecords }
    "snapshots" { Run-Snapshots }
    "release-manifest" { Run-ReleaseManifest }
    "support-bundle" { Run-SupportBundle }
    "infra-check" {
        Run-Ruff
        Run-Mypy
        Run-Docstring
        Run-Complexity
        Run-DecisionRecords
        & $python scripts/runtime_doctor.py --json
        Run-Snapshots
        Run-ReleaseHarnessScorecard
        Run-ReleaseManifest
        if (Test-DockerAvailable) {
            Run-ComposeConfig
        }
        else {
            Write-Warning "Docker is not available. Skipping compose validation during infra-check."
        }
    }
    "backend-image-smoke" { Run-BackendImageSmoke }
    "frontend-image-smoke" { Run-FrontendImageSmoke }
    "container-smoke" {
        Run-BackendImageSmoke
        Run-FrontendImageSmoke
    }
    "compose-up" { Invoke-ComposeCommand @("up", "--build") }
    "compose-observability" { Invoke-ComposeCommand @("--profile", "observability", "up", "--build") }
    "compose-config" { Run-ComposeConfig }
    default {
        throw "Unknown task '$Task'. Run '.\dev.ps1 help' to see available tasks."
    }
}
