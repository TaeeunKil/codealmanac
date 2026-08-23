# Agent Work Memory

**Agent Work Memory (AWM)** is a private local memory and Markdown Wiki for work
performed with Codex, Claude, Cursor, local LLMs, and other coding agents.

AWM retains agent sessions across repositories and explicitly registered SSH
machines, keeps the evidence searchable, and promotes selected work into durable
pages for projects, decisions, systems, problems, procedures, and unfinished
work.

> AWM is currently an alpha installed from this source repository. Automatic
> sync and automatic distillation are implemented for Windows (Task Scheduler)
> and Linux (systemd user timers). On macOS, scheduled commands must still be
> run manually.

## What gets installed

AWM has three separate layers:

| Layer | Default location on Windows | Contains |
| --- | --- | --- |
| Application | uv's isolated tool directory | AWM and all Python packages |
| Private state | `%LOCALAPPDATA%\AgentWorkMemory` | SQLite, retained events, logs, locks, SSH snapshots |
| Markdown Vault | chosen during `awm setup` | durable Wiki and retained session pages |

The source checkout is shareable application code. The state directory and
Vault are private data and must not be committed to this repository.

## Windows quick start

These commands are intended for a normal, non-administrator PowerShell unless a
step says otherwise.

### 1. Install the two required tools

AWM users need **Git** and **uv**. Install both with Windows Package Manager:

```powershell
winget install --id Git.Git -e --source winget
winget install --id astral-sh.uv -e --source winget
```

Close and reopen PowerShell, then verify them:

```powershell
git --version
uv --version
```

Official alternatives are available from the [Git for Windows installer][git]
and the [uv installation guide][uv-install].

You do **not** need to install Python separately. AWM requires Python 3.12 or
newer, and uv downloads a compatible Python automatically when necessary. On a
managed or offline machine, preinstall it explicitly with:

```powershell
uv python install 3.12
```

See [uv's Python management guide][uv-python] for download and system-Python
controls.

### 2. Clone and install AWM

```powershell
git clone https://github.com/TaeeunKil/agent-work-memory.git
Set-Location agent-work-memory
uv tool install . --force
awm --help
```

`uv tool install` creates a persistent isolated environment and installs all
packages declared in `pyproject.toml`. Do not manually install FastAPI, SQLite,
Pydantic, PyYAML, or the other Python libraries.

If PowerShell cannot find `awm`, add uv's tool executable directory to `PATH`,
then open a new terminal:

```powershell
uv tool update-shell
uv tool dir --bin
```

### 3. Install only the agent integrations you use

No individual agent is mandatory for session storage, but you need at least one
session source to collect useful records. Wiki distillation additionally needs
one ready curator runtime.

| Integration | Needed for | Required? |
| --- | --- | --- |
| ChatGPT desktop app with Codex, or Codex CLI | Codex sessions and recommended remote curator | Optional |
| Claude Code | Claude sessions and Claude curator | Optional |
| Cursor | Cursor Composer sessions | Optional |
| Ollama | fully local curator | Optional |
| OpenSSH client | explicitly registered remote machines | Optional |
| Obsidian | editing the Vault outside AWM's local viewer | Optional |

#### Codex curator and sessions

On Windows, the recommended route is the ChatGPT desktop app, which includes
Codex:

```powershell
winget install --id 9PLM9XGG6VKS -s msstore
```

Open it and sign in with the personal or workspace account whose data policy you
intend to use. If you installed the standalone Codex CLI instead, authenticate
it with:

```powershell
codex login
codex login status
```

AWM discovers either the installed desktop runtime or a `codex` executable on
`PATH`. OpenAI documents the [desktop quickstart][codex-windows] and
[authentication choices][codex-auth]. A ChatGPT sign-in follows that workspace's
permissions and data controls; API-key sign-in follows the API organization's
controls and billing.

#### Claude Code curator and sessions

Native Claude Code on Windows requires Git for Windows and Node.js 18 or newer:

```powershell
winget install --id OpenJS.NodeJS.LTS -e --source winget
npm install -g @anthropic-ai/claude-code
claude
claude doctor
```

Complete the account sign-in shown by `claude`. See Anthropic's
[Claude Code setup guide][claude-code] for native Windows and WSL options.

#### Local Ollama curator

Install Ollama using its [official Windows installer][ollama-windows], start it,
and pull a model before asking AWM to use it:

```powershell
ollama pull qwen3:8b
```

AWM accepts Ollama only through a loopback HTTP endpoint. It does not give the
local model shell or direct filesystem access.

#### Cursor sessions

Install and run [Cursor][cursor-install] normally. AWM reads Cursor Composer's
local SQLite store; there is no Cursor plugin to install. Codex sessions created
through the Cursor Codex extension remain Codex sessions, so AWM does not import
them twice.

### 4. Initialize the private Vault

Choose a private directory that is not inside this application checkout:

```powershell
$vault = Join-Path $HOME 'Documents\AgentWorkMemoryVault'
awm setup $vault --include-content --auto --every 5
```

This command:

1. creates the Markdown Vault;
2. collects Codex, Claude, and Cursor records found under your user profile;
3. retains transcript bodies because `--include-content` was explicit; and
4. installs the Windows `AWM Sync` task every five minutes.

Without `--include-content`, AWM collects metadata only. Transcript bodies can
contain source code, terminal output, internal paths, customer information, and
secrets. Automatic sync stores evidence locally and **never invokes a model**.

Verify the installation:

```powershell
awm doctor --runtimes
awm auto status
awm sessions
awm serve
```

The viewer opens at `http://127.0.0.1:3928` and binds only to loopback.

## Distill sessions into the Wiki

First test a small manual run. Remote curator access to selected transcript
bodies must be explicit:

```powershell
awm distill --pending --limit 1 `
  --using codex `
  --allow-remote-content
```

For Claude, replace `codex` with `claude`. For local Ollama:

```powershell
awm distill --pending --limit 1 `
  --using ollama `
  --model qwen3:8b `
  --allow-local-content
```

After a manual run succeeds, automatic distillation can be installed separately:

```powershell
awm auto-distill install `
  --every 60 `
  --limit 1 `
  --for-days 2 `
  --max-total 6 `
  --using codex `
  --allow-remote-content
```

The standing grant is bounded by time and reserved-session count. A curator
attempt consumes its reservation even when the model output later fails
validation. Inspect or remove it with:

```powershell
awm auto-distill status
awm auto-distill run
awm auto-distill remove
```

## Collect from SSH machines

SSH collection is optional. The local machine needs the Windows OpenSSH client.
Check it first:

```powershell
ssh -V
Get-WindowsCapability -Online | Where-Object Name -Like 'OpenSSH.Client*'
```

If it is missing, run PowerShell as Administrator and install only the client:

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
```

The remote host must have `python3`, an existing trusted `known_hosts` entry,
and non-interactive key authentication. Confirm that before registering it:

```powershell
ssh agent-box python3 --version
awm remote add agent-box
awm remote status agent-box
awm remote sync agent-box --include-content
```

Use an alias from `~/.ssh/config` or `user@host`. AWM uses OpenSSH batch mode,
reads only bounded Codex and Claude transcript manifests, and does not write to
the remote machine. See Microsoft's [OpenSSH client instructions][openssh].

## Keep the Vault in a private Git repository

Git is already a base prerequisite. Configure a commit identity once if this is
a new machine:

```powershell
git config --global user.name 'Your Name'
git config --global user.email 'you@example.com'
```

Create an empty **private** repository, then publish the configured Vault:

```powershell
awm vault publish https://github.com/YOUR-NAME/YOUR-PRIVATE-VAULT.git
```

On another machine, install AWM first and clone the Vault during setup:

```powershell
awm setup "$HOME\Documents\AgentWorkMemoryVault" `
  --vault-repo https://github.com/YOUR-NAME/YOUR-PRIVATE-VAULT.git `
  --include-content
```

Normal Git-backed Vault commands are:

```powershell
awm vault status
awm vault sync
awm vault push --message 'Update personal memory'
awm vault pull
```

`awm vault sync` commits all Vault changes, pulls with rebase, and pushes without
force. Keep the repository private because `inbox/agent-sessions` can contain
complete transcript evidence. AWM keeps a stable session index and automatically
splits large retained sessions into numbered Markdown parts. Publication stops
before staging if any Vault file still exceeds the 48 MiB safety limit; run a
content sync to rebuild that session record before retrying.

Vault Git operations use the same state-root synchronization lock as transcript
collection. If `AWM Sync` is running, `awm vault sync` waits for it to finish
before refreshing the Wiki/search views or touching Git, so the two operations do
not race on SQLite or generated Vault files.

## Daily use

```powershell
awm sync --from codex --from claude --from cursor --include-content
awm sessions
awm search 'why we chose sqlite'
awm serve
```

The viewer provides four local surfaces:

- **Today**: retained sessions, Wiki pages, and pending distillation;
- **Sessions**: evidence from agents, imports, SSH, and manual notes;
- **Knowledge**: durable Markdown promoted from selected evidence; and
- **Activity**: running work, scheduled work, receipts, and logs.

The Vault is ordinary Markdown. [Obsidian][obsidian] is optional; open the Vault
folder and then `Home.md`. Do not manually edit generated `Home.md` or `_index.md`
files.

## Update or uninstall

Update the source checkout and reinstall the isolated tool:

```powershell
Set-Location C:\path\to\agent-work-memory
git pull --ff-only
uv tool install . --force
awm doctor --runtimes
```

Remove scheduled work before uninstalling the command:

```powershell
awm auto-distill remove
awm auto remove
uv tool uninstall agent-work-memory
```

Uninstalling the tool does not delete the configured Vault or
`%LOCALAPPDATA%\AgentWorkMemory`.

## Troubleshooting

### `awm` is not recognized

```powershell
uv tool update-shell
uv tool dir --bin
uv tool list
```

Open a new PowerShell after updating `PATH`.

### A curator is unavailable

```powershell
awm runtimes
awm doctor --runtimes
```

For Codex, confirm the intended account with `codex login status` when the CLI
is on `PATH`. For Claude, run `claude doctor`. For Ollama, start the application
and confirm that `ollama list` shows the requested model.

### Automatic sync is unavailable

Windows uses Task Scheduler tasks named `AWM Sync` and `AWM Auto Distill`.
Linux uses systemd user timers named `awm-sync.timer` and
`awm-auto-distill.timer`. Automatic scheduling is not implemented on macOS; run
`awm sync` and `awm auto-distill run` from your own scheduler there.

Inspect status on any supported platform:

```powershell
# Windows
Get-ScheduledTask -TaskName 'AWM Sync','AWM Auto Distill' -ErrorAction SilentlyContinue
awm auto status
awm auto-distill status
```

```bash
# Linux
systemctl --user list-timers 'awm-*'
awm auto status
awm auto-distill status
```

On Linux, `awm auto install` and `awm auto-distill install` write units under
`~/.config/systemd/user/` and enable them with `systemctl --user`. Linger may be
required for timers to run while you are logged out:

```bash
loginctl enable-linger "$USER"
```

Always install AWM with `uv tool install`. On Windows, AWM validates that
background tasks use a real GUI-subsystem Python runtime and refuses
console-backed launchers that would flash a terminal window.

## Contributor setup

Normal AWM users can stop above. Contributors need the locked development
environment:

```powershell
git clone https://github.com/TaeeunKil/agent-work-memory.git
Set-Location agent-work-memory
uv sync --locked
uv run awm --help
```

Python test and lint dependencies come from the `dev` dependency group. Unless
you also chose Claude Code, contributors use Node.js only for the JavaScript
syntax gate; this repository itself has no npm package installation step.
Install Node.js LTS if `node` is unavailable:

```powershell
winget install --id OpenJS.NodeJS.LTS -e --source winget
```

Run the repository gates:

```powershell
uv run pytest
uv run ruff check src/agentworkmemory tests
node --check src/agentworkmemory/viewer/assets/app.js
```

The active product is under `src/agentworkmemory/`. The upstream
`src/codealmanac/` tree is unshipped reference source.

## What is not required

AWM itself does not require Docker, WSL, npm packages, a separate database
server, a browser extension, an Obsidian plugin, or one installation per
project. The optional Claude Code installation above is the only documented npm
use. AWM is one local application that collects the configured user's agent
records across workspaces.

See the [full user guide](docs/agent-work-memory-user-guide.md) for imports,
recovery, privacy boundaries, and detailed workflows.

License: Apache-2.0.

[git]: https://git-scm.com/install/windows.html
[uv-install]: https://docs.astral.sh/uv/getting-started/installation/
[uv-python]: https://docs.astral.sh/uv/guides/install-python/
[codex-windows]: https://learn.chatgpt.com/docs/quickstart?setup=app
[codex-auth]: https://learn.chatgpt.com/docs/auth
[claude-code]: https://docs.anthropic.com/en/docs/claude-code/getting-started
[ollama-windows]: https://docs.ollama.com/windows
[cursor-install]: https://docs.cursor.com/get-started/installation
[openssh]: https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse
[obsidian]: https://obsidian.md/download
