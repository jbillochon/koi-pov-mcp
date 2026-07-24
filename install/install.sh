#!/usr/bin/env bash
# koi-pov-mcp installer for Linux and macOS
# - creates an isolated venv in ~/.koi-pov-mcp
# - installs the package from this checkout
# - registers the MCP server in Claude Desktop's config
# - installs the companion skill into ~/.claude/skills
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

# 3. API key (hidden input, optional)
printf "Koi API key (Enter to skip and set later): "
read -r -s KOI_KEY || KOI_KEY=""
echo

# 4. Merge Claude Desktop config (via Python for safe JSON handling)
mkdir -p "$(dirname "$CFG")"
KOI_KEY="$KOI_KEY" "$VENV/bin/python" - "$CFG" "$BIN" <<'EOF'
import json, os, sys
cfg, bin_ = sys.argv[1], sys.argv[2]
key = os.environ.get("KOI_KEY", "")
data = {}
if os.path.exists(cfg):
    with open(cfg, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            sys.exit(f"ERROR: existing config is not valid JSON ({cfg}): {exc}")
servers = data.setdefault("mcpServers", {})
entry = {"command": bin_}
if key:
    entry["env"] = {"KOI_API_KEY": key}
elif isinstance(servers.get("koi-pov"), dict) and "env" in servers["koi-pov"]:
    entry["env"] = servers["koi-pov"]["env"]  # keep a previously configured key
servers["koi-pov"] = entry
with open(cfg, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
print(f"MCP server registered in {cfg}")
EOF

# 5. Skill
mkdir -p "$(dirname "$SKILL_DST")"
rm -rf "$SKILL_DST"
cp -R "$SKILL_SRC" "$SKILL_DST"
echo "Skill installed in $SKILL_DST"

echo
echo "Done. Restart Claude Desktop completely, then ask Claude:"
echo "  'Use the koi_ping tool'  to verify."
if [ -z "$KOI_KEY" ]; then
  echo "No API key set: add KOI_API_KEY to the 'koi-pov' env block in $CFG"
fi
