#!/usr/bin/env bash
# koi-pov-mcp installer for Linux and macOS
# - creates an isolated venv in ~/.koi-pov-mcp
# - installs the package from this checkout
# - registers the MCP server in Claude Desktop's config (no keys in the config)
# - installs the companion skill into ~/.claude/skills
# - offers to add tenant API keys via the CLI (OS keyring, or restricted file)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_DIR="$HOME/.koi-pov-mcp"
VENV="$INSTALL_DIR/venv"
BIN="$VENV/bin/koi-pov-mcp"
SKILL_SRC="$REPO_ROOT/skill/koi-pov-deliverables"
SKILL_DST="$HOME/.claude/skills/koi-pov-deliverables"

case "$(uname -s)" in
  Darwin) CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
  *)      CFG="$HOME/.config/Claude/claude_desktop_config.json" ;;
esac

echo "== koi-pov-mcp installer =="

# 1. Python check
PY="$(command -v python3 || true)"
[ -n "$PY" ] || { echo "ERROR: python3 not found." >&2; exit 1; }
"$PY" - <<'EOF' || { echo "ERROR: Python 3.10+ required." >&2; exit 1; }
import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)
EOF

# 2. Venv + install
echo "Creating venv in $VENV"
"$PY" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
echo "Installing koi-pov-mcp"
"$VENV/bin/pip" install --quiet "$REPO_ROOT"
[ -x "$BIN" ] || { echo "ERROR: install failed, $BIN not found." >&2; exit 1; }

# 3. Register the MCP server (no keys written; keys live in the OS keyring)
mkdir -p "$(dirname "$CFG")"
"$VENV/bin/python" - "$CFG" "$BIN" <<'EOF'
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
EOF

# 4. Skill
mkdir -p "$(dirname "$SKILL_DST")"
rm -rf "$SKILL_DST"
cp -R "$SKILL_SRC" "$SKILL_DST"
echo "Skill installed in $SKILL_DST"

# 5. Tenants (hidden input, stored via keyring or restricted file)
echo
echo "Tenant setup. One alias per Koi tenant (e.g. acme)."
while true; do
  printf "Add a tenant alias (Enter to finish): "
  read -r alias || alias=""
  [ -n "$alias" ] || break
  "$BIN" tenants add "$(printf '%s' "$alias" | tr '[:upper:]' '[:lower:]')" --test || true
done

echo
echo "Done. Restart Claude Desktop completely, then ask Claude:"
echo "  'Use the koi_tenants tool'  to verify."
echo "Add more tenants anytime (no restart needed):"
echo "  $BIN tenants add <alias>"
