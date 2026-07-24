# koi-pov-mcp

MCP server + Claude skill to run **Cortex AES (Koi) Proofs of Value** end to
end, entirely from the Claude interface:

- **Multi-tenant**: one isolated environment (data, history, deliverables)
  per Koi tenant; an SE can run 5-6 PoVs in parallel.
- **Natural-language driven**: "add a tenant", "sync tenant acme", "what's
  new for my follow-up", "generate the report and deck" work in any language.
- **Credential-safe by construction**: API keys are entered in native OS
  dialog windows and stored in the OS credential store; they never transit
  through a Claude conversation.
- **Deterministic threat intel**: NVD, OSV.dev, CISA KEV, FIRST EPSS, and a
  human-curated MITRE ATT&CK mapping. No model-generated intel, everything
  dated and traceable.
- **Optional XSIAM cross-referencing**: link a Cortex XSIAM tenant to a Koi
  tenant (same dialog approach) and correlate agent coverage and incidents.
- **Rendered deliverables**: report.docx and deck.pptx everywhere (pure
  Python), report.pdf where WeasyPrint is available. Missing narrative shows
  as a visible `[[TO BE PROVIDED]]`, never as an invented figure.

Standalone and cross-platform: **Windows, Linux, macOS**. No Docker, no
database, no running service.

> Deployment-independent rewrite of the collection layer of
> [povplatform](https://github.com/jbillochon/povplatform). The Koi client,
> collector and TI design are ported from it; nothing here imports it.

## Documentation

| Document | Content |
|---|---|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Day-to-day usage: commands, workflows, follow-up prep, deliverables |
| [docs/TOOLS.md](docs/TOOLS.md) | Complete reference of the 14 MCP tools and the CLI |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flow, per-tenant layout, design decisions |
| [docs/SECURITY.md](docs/SECURITY.md) | Credential model, what never transits through the chat |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Errors and fixes |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

## Requirements

- Python **3.10+** and `git`
- Claude Desktop or Claude Code (MCP support)
- One Koi API key per tenant (read access); optionally XSIAM API credentials

## Quick install

**Windows (PowerShell 5.1+ or pwsh):**

```powershell
git clone https://github.com/jbillochon/koi-pov-mcp.git
cd koi-pov-mcp
powershell -ExecutionPolicy Bypass -File install\install.ps1
```

**Linux / macOS:**

```bash
git clone https://github.com/jbillochon/koi-pov-mcp.git
cd koi-pov-mcp
bash install/install.sh
```

The installer creates a venv in `~/.koi-pov-mcp`, registers the MCP server in
Claude Desktop's config (no keys in the config), installs the skill into
`~/.claude/skills/`, and walks you through adding tenants (hidden input,
tested live). Then **restart Claude Desktop completely** (quit from the
tray/menu bar).

### Verify

In a new Claude conversation: *"Use the koi_tenants tool"* should list your
aliases; *"ping tenant &lt;alias&gt;"* should answer OK. From there, everything is
conversational; see the [User Guide](docs/USER_GUIDE.md).

## Updating

```bash
cd <your clone> && git pull
~/.koi-pov-mcp/venv/bin/pip install --upgrade .
cp -R skill/koi-pov-deliverables ~/.claude/skills/
```

(Windows: `%USERPROFILE%\.koi-pov-mcp\venv\Scripts\pip.exe install --upgrade .`
and copy the skill folder.) Restart Claude Desktop after updating: tenant
keys and collected data are untouched by updates.

## License

MIT
