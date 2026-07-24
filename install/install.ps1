# koi-pov-mcp installer for Windows (PowerShell)
# - creates an isolated venv in %USERPROFILE%\.koi-pov-mcp
# - installs the package from this checkout
# - registers the MCP server in Claude Desktop's config
# - installs the companion skill into %USERPROFILE%\.claude\skills

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Home_ = $env:USERPROFILE
$InstallDir = Join-Path $Home_ ".koi-pov-mcp"
$VenvDir = Join-Path $InstallDir "venv"
$Bin = Join-Path $VenvDir "Scripts\koi-pov-mcp.exe"
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
& (Join-Path $VenvDir "Scripts\python.exe") -m pip install --quiet --upgrade pip
Write-Host "Installing koi-pov-mcp"
& (Join-Path $VenvDir "Scripts\pip.exe") install --quiet $RepoRoot
if (-not (Test-Path $Bin)) { Write-Error "Install failed: $Bin not found." }

# 3. API key (hidden input, optional)
$Key = Read-Host -AsSecureString "Koi API key (Enter to skip and set later)"
$KeyPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Key))

# 4. Merge Claude Desktop config
New-Item -ItemType Directory -Force -Path (Split-Path $Cfg) | Out-Null
$data = @{}
if (Test-Path $Cfg) {
    try { $data = Get-Content $Cfg -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable }
    catch { Write-Error "Existing config is not valid JSON: $Cfg. Fix it and re-run." }
}
if (-not $data.ContainsKey("mcpServers")) { $data["mcpServers"] = @{} }
$entry = @{ command = $Bin }
if ($KeyPlain) { $entry["env"] = @{ KOI_API_KEY = $KeyPlain } }
elseif ($data["mcpServers"].ContainsKey("koi-pov") -and $data["mcpServers"]["koi-pov"].ContainsKey("env")) {
    # keep a previously configured key
    $entry["env"] = $data["mcpServers"]["koi-pov"]["env"]
}
$data["mcpServers"]["koi-pov"] = $entry
$data | ConvertTo-Json -Depth 10 | Set-Content -Path $Cfg -Encoding UTF8
Write-Host "MCP server registered in $Cfg"

# 5. Skill
New-Item -ItemType Directory -Force -Path (Split-Path $SkillDst) | Out-Null
if (Test-Path $SkillDst) { Remove-Item -Recurse -Force $SkillDst }
Copy-Item -Recurse $SkillSrc $SkillDst
Write-Host "Skill installed in $SkillDst"

Write-Host ""
Write-Host "Done. Restart Claude Desktop completely (quit from the tray)," -ForegroundColor Green
Write-Host "then ask Claude: 'Use the koi_ping tool' to verify." -ForegroundColor Green
if (-not $KeyPlain) {
    Write-Host "No API key set: add KOI_API_KEY to the 'koi-pov' env block in $Cfg" -ForegroundColor Yellow
}
