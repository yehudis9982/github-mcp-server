# GitHub MCP Server

**Transform your AI coding assistant into a powerful GitHub intelligence platform.** This production-ready MCP server unlocks comprehensive GitHub capabilities—enabling AI agents to analyze repositories, track development workflows, investigate code evolution, and provide data-driven insights through natural language interaction.

---

## Overview

Empower your AI coding assistant with deep GitHub integration:
- 📦 **Repository Intelligence** – Extract metadata, statistics, and structural insights instantly
- 🔬 **Code Navigation** – Browse file trees, read source code, and understand project architecture
- 📊 **Workflow Monitoring** – Track CI/CD pipelines, workflow runs, and automation status
- 🔍 **Commit History Research** – Investigate code evolution with detailed diff analysis
- 🎯 **Issues & Pull Requests** – Query tickets with full context, labels, comments, and metadata
- ⚡ **Reliable API Access** – GitHub REST API v3 integration with smart error handling

---

## Tools

### `github_repo_info`
Get comprehensive repository information

**Inputs:**
- `repo` (string, optional): Repository in format `owner/repo` or GitHub URL
- `root_path` (string, optional): Local path to infer repository from `.git/config`

**Returns:** Repository metadata including name, description, stars, forks, default branch, languages, topics, license, homepage, and URLs

---

### `github_get_file`
Read file contents from a repository

**Inputs:**
- `repo` (string, optional): Repository in format `owner/repo` or GitHub URL
- `root_path` (string, optional): Local path to infer repository
- `path` (string): File path within repository
- `ref` (string, optional): Branch, tag, or commit SHA (defaults to default branch)

**Returns:** File content as text with metadata (path, ref, size, encoding)

---

### `github_compare_commits`
Compare changes between commits, branches, or tags

**Inputs:**
- `repo` (string, optional): Repository in format `owner/repo` or GitHub URL
- `root_path` (string, optional): Local path to infer repository
- `base` (string): Base commit/branch/tag
- `head` (string): Head commit/branch/tag to compare against base

**Returns:** Comparison summary with commit count, file changes (additions/deletions/modifications), and per-file diff details

---

### `github_list_workflow_runs`
List GitHub Actions workflow runs

**Inputs:**
- `repo` (string, optional): Repository in format `owner/repo` or GitHub URL
- `root_path` (string, optional): Local path to infer repository
- `workflow_id` (string, optional): Workflow file name (e.g., `ci.yml`) or workflow ID
- `branch` (string, optional): Filter by branch name
- `status` (string, optional): Filter by status: `queued`, `in_progress`, `completed`
- `limit` (number, optional): Maximum results to return (1-100, default: 20)

**Returns:** List of workflow runs with ID, name, status, conclusion, branch, commit SHA, author, timestamps, and URL

---

### `github_get_workflow_run`
Get detailed information about a specific workflow run

**Inputs:**
- `run_id` (number): Workflow run ID
- `repo` (string, optional): Repository in format `owner/repo` or GitHub URL
- `root_path` (string, optional): Local path to infer repository

**Returns:** Detailed workflow run data including status, conclusion, duration, triggering actor, jobs summary, and logs URL

---

### `github_list_issues`
List issues from a repository (optionally include pull requests)

**Inputs:**
- `repo` (string, optional): Repository in format `owner/repo` or GitHub URL
- `root_path` (string, optional): Local path to infer repository
- `state` (string, optional): Filter by state: `open`, `closed`, `all` (default: `open`)
- `labels` (string, optional): Comma-separated labels filter
- `limit` (number, optional): Maximum results to return (1-100, default: 20)
- `include_prs` (boolean, optional): Include pull requests in results (default: `true`)

**Returns:** List of issues with number, title, body, state, author, labels, comment count, timestamps, and URL

---

### `github_get_issue`
Get full details of a specific issue or pull request including all comments

**Inputs:**
- `issue_number` (number): Issue or PR number
- `repo` (string, optional): Repository in format `owner/repo` or GitHub URL
- `root_path` (string, optional): Local path to infer repository

**Returns:** Complete issue/PR data with number, title, body, state, author, labels, assignees, comment count, full comment thread (with user, body, timestamps per comment), and URL

---

### `github_list_commits`
List commits from a branch

**Inputs:**
- `repo` (string, optional): Repository in format `owner/repo` or GitHub URL
- `root_path` (string, optional): Local path to infer repository
- `branch` (string, optional): Branch name (defaults to default branch)
- `limit` (number, optional): Maximum commits to return (1-100, default: 10)

**Returns:** List of commits with SHA, message (first line), author name, date, and URL

---

### `github_list_pulls`
List pull requests with detailed information

**Inputs:**
- `repo` (string, optional): Repository in format `owner/repo` or GitHub URL
- `root_path` (string, optional): Local path to infer repository
- `state` (string, optional): Filter by state: `open`, `closed`, `all` (default: `open`)
- `base` (string, optional): Filter by base branch
- `limit` (number, optional): Maximum results to return (1-100, default: 20)

**Returns:** List of PRs with number, title, body, state, author, draft status, labels, assignees, comment count, commit count, code changes (additions/deletions/changed files), merge status, head/base branches with SHAs, timestamps, and URL

---

## Installation

### Prerequisites
- **Python 3.12+** installed
- **uv** package manager ([installation instructions](https://docs.astral.sh/uv/getting-started/installation/))

### Setup Steps

1. **Clone the repository:**
   ```powershell
   git clone <your-repo-url>
   cd mcp
   ```

2. **Install dependencies:**
   ```powershell
   uv sync
   ```

That's it! The project is ready to use. No additional installation needed - it runs directly from this directory.

---

## Project Structure

```
├── server.py              # Main MCP server - contains all tool implementations
├── pyproject.toml         # Project metadata and dependencies
├── uv.lock               # Locked dependency versions
├── .env.example          # Example environment configuration
├── .gitignore            # Git ignore patterns
├── run_dev.ps1           # PowerShell script to run MCP inspector
├── run_server.ps1        # PowerShell script to run the server
└── README.md             # This file
```

### Key Files

**`server.py`** - The heart of the project:
- **Lines 1-40:** Configuration and imports
- **Lines 42-170:** Repository resolution logic (parses `.git/config` without subprocess)
- **Lines 172-210:** GitHub API helpers (authentication, request handling)
- **Lines 212-770:** Tool implementations (9 GitHub API tools)

**How it works:**
1. Server loads and reads `GITHUB_TOKEN` from environment
2. By default, automatically detects the repository from the `.git` folder in the current directory
3. Can also explicitly specify:
   - `repo` parameter - to query a different repository (e.g., "owner/repo")
   - `root_path` parameter - to specify a different local directory
4. Makes authenticated requests to GitHub REST API v3
5. Returns structured data to the AI agent

**Running the server:**
- **Development/Testing:** `mcp dev server.py` (opens inspector)
- **Production:** Configured in MCP client (Codex, Claude Desktop, etc.)

---

## Configuration

### GitHub Token Setup

#### Step 1: Generate Personal Access Token

1. Go to: https://github.com/settings/tokens
2. Click **"Generate new token"** → **"Generate new token (classic)"**
3. Give it a name (e.g., "MCP Server")
4. **Select required scopes (permissions):**
   - ✅ **`repo`** - Full repository access (read code, issues, PRs, commits, etc.)
   - ✅ **`read:user`** - Read user profile information
   - ✅ **`read:org`** - Access to organizations (if you have any)
   - ✅ **`workflow`** - Access to GitHub Actions workflows (optional but recommended)
5. Click **"Generate token"**
6. **Copy the token immediately!** (It's shown only once)

---

### Usage with Codex (VS Code) 

**Step 1: Configure the server**

Edit (or create) this file:
```
C:\Users\<YourUsername>\.codex\config.toml
```

Add this configuration:
```toml
[mcp_servers.github-mcp]
command = "uv"
args = ["--directory", "C:\\Users\\YourName\\Desktop\\github-mcp", "run", "server.py"]

[mcp_servers.github-mcp.env]
GITHUB_TOKEN = "ghp_your_token_here"  # ← Paste your GitHub token here
```

**Important:**
- Replace `C:\\Users\\YourName\\Desktop\\github-mcp` with your actual project path
- Replace `ghp_your_token_here` with your GitHub token
- Use `\\` (double backslashes) in Windows paths

**Step 2: Restart VS Code**
1. Save the config file
2. Restart VS Code completely (Ctrl+Shift+P → "Reload Window")
3. Open Codex

**Step 3: Verify MCP is connected**

Run in terminal:
```powershell
codex mcp list
```

You should see `github-mcp` in the list.

**Step 4: Test it**

In Codex, open a folder that contains a git repository and try asking:

**Basic queries:**
- "Show me info about this repo"
- "What are the latest commits?"
- "Show me open issues"
- "List recent workflow runs"

**Analysis queries (Codex analyzes the data):**
- "Analyze the changes in the last 10 commits"
- "Summarize all open bugs"
- "What are the most active files in recent commits?"
- "Are there any security-related issues?"

The server will automatically detect the repository from the `.git` folder. You can also specify a different repository explicitly: "Show me info about owner/repo"

---

### Usage with Other AI Agents

This server is compatible with any AI agent that supports MCP (Claude code, Gemini etc.). 

**General configuration example:**
```json
{
  "mcpServers": {
    "github-mcp": {
      "command": "uv",
      "args": ["--directory", "<path-to-mcp-folder>", "run", "server.py"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

---

### Testing with MCP Inspector

To test the server before integrating with an agent:

**Step 1: Setup environment variables**

Copy the example environment file:
```powershell
Copy-Item .env.example .env
```

Then edit `.env` and add your GitHub token:
```
GITHUB_TOKEN=ghp_your_token_here
```

**Step 2: Run the inspector**

```powershell
.\run_dev.ps1
```

Or manually:
```powershell
mcp dev server.py
```

This will open a browser with an interactive interface to test the tools.

---

**Stack:** Python 3.12+ | FastMCP 1.25.0+ | uv 0.5+ | Windows + macOS + Linux

