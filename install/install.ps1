# koi-pov-mcp installer for Windows (PowerShell 5.1+ and pwsh)
# - creates an isolated venv in %USERPROFILE%\.koi-pov-mcp
# - installs the package from this checkout
# - registers the MCP server in Claude Desktop's config (no keys in the config)
# - installs the companion skill into %USERPROFILE%\.claude\skills
# - offers to add tenant API keys via the CLI (stored in Windows Credential Manager)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Home_ = $env:USERPROFILE
$InstallDir = Join-Path $Home_ ".koi-pov-mcp"
$VenvDir = Join-Path $InstallDir "venv"
$Bin = Join-Path $VenvDir "Scripts\koi-pov-mcp.exe"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$Cfg = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
$SkillSrc = Join-Path $RepoRoot "skill\koi-pov-deliverables"
$SkillDst = Join-Path $Home_ ".claude\skills\koi-pov-deliverables"

Write-Host "== koi-pov-mcp installer ==" -ForegroundColor Cyan

# 1. Python check
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Write-Error "Python not found in PATH. Install Python 3.10+ first." }
$ver = & python -c "import sys; print(sys.version_info >= (3,10))"
if ($ver.Trim() -ne "True") { Write-Error "Python 3.10+ required." }

# 2. Venv + install
Write-Host "Creating venv in $VenvDir"
python -m venv $VenvDir
& $VenvPython -m pip install --quiet --upgrade pip
Write-Host "Installing koi-pov-mcp"
& (Join-Path $VenvDir "Scripts\pip.exe") install --quiet $RepoRoot
if (-not (Test-Path $Bin)) { Write-Error "Install failed: $Bin not found." }

# 3. Register the MCP server in Claude Desktop's config.
# No keys are written here: keys go to the OS credential store via the CLI.
# JSON handling is delegated to the venv's Python (PowerShell 5.1 compatible),
# and a failed merge is loud, not silent.
New-Item -ItemType Directory -Force -Path (Split-Path $Cfg) | Out-Null
$MergeScript = @'
import json, os, sys
cfg, bin_ = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(cfg):
    with open(cfg, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            sys.exit(f"ERROR: existing config is not valid JSON ({cfg}): {exc}")
servers = data.setdefault("mcpServers", {})
entry = {"command": bin_}
prev = servers.get("koi-pov")
if isinstance(prev, dict) and prev.get("env"):
    entry["env"] = prev["env"]  # keep env-configured keys from older setups
servers["koi-pov"] = entry
with open(cfg, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
print(f"MCP server registered in {cfg}")
'@
$MergeFile = Join-Path $env:TEMP "koi_pov_merge_cfg.py"
Set-Content -Path $MergeFile -Value $MergeScript -Encoding UTF8
try {
    & $VenvPython $MergeFile $Cfg $Bin
    if ($LASTEXITCODE -ne 0) { Write-Error "Config merge failed (see message above)." }
}
finally {
    Remove-Item $MergeFile -ErrorAction SilentlyContinue
}

# 4. Skill
New-Item -ItemType Directory -Force -Path (Split-Path $SkillDst) | Out-Null
if (Test-Path $SkillDst) { Remove-Item -Recurse -Force $SkillDst }
Copy-Item -Recurse $SkillSrc $SkillDst
Write-Host "Skill installed in $SkillDst"

# 5. Tenants (keys stored in Windows Credential Manager, hidden input)
Write-Host ""
Write-Host "Tenant setup. One alias per Koi tenant (e.g. acme)." -ForegroundColor Cyan
while ($true) {
    $alias = Read-Host "Add a tenant alias (Enter to finish)"
    if ([string]::IsNullOrWhiteSpace($alias)) { break }
    & $Bin tenants add $alias.Trim().ToLower() --test
}

Write-Host ""
Write-Host "Done. Restart Claude Desktop completely (quit from the tray)," -ForegroundColor Green
Write-Host "then ask Claude: 'Use the koi_tenants tool' to verify." -ForegroundColor Green
Write-Host "Add more tenants anytime (no restart needed):" -ForegroundColor Green
Write-Host "  $Bin tenants add <alias>" -ForegroundColor Green
