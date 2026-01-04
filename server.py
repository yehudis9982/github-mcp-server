"""
GitHub MCP Server (FastMCP)
"""

from __future__ import annotations
import base64
import os
import re
from typing import Any, Optional
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pathlib import Path


# --- Load .env for local development only ---
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

# Configuration from environment
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# SSL/Certificate configuration
SSL_VERIFY = os.getenv("GITHUB_SSL_VERIFY", "true").lower() not in ("false", "0", "no")
SSL_CERT_FILE = os.getenv("SSL_CERT_FILE")  # Custom CA bundle path

# Constants
SERVER_NAME = "github-mcp"
HTTP_TIMEOUT = 30.0
USER_AGENT = "mcp-server/1.0"

mcp = FastMCP(SERVER_NAME)
GITHUB_API_BASE = "https://api.github.com"

_OWNER_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


# -------------------------
# Repo resolution
# -------------------------
def parse_owner_repo(repo_or_url: str) -> str:
    s = (repo_or_url or "").strip()
    if _OWNER_REPO.fullmatch(s):
        return s

    m = re.fullmatch(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?", s)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    m = re.fullmatch(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?", s)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    raise ValueError("repo must be 'owner/repo' or a GitHub URL/SSH remote")

def _clean_path(p: str) -> str:
    return os.path.normpath(p.strip().strip('"').strip("'"))

def _find_git_dir(start: Path) -> Optional[Path]:
    """
    Walk up from start to find .git (directory) or .git file (worktree).
    Returns the actual git directory path that contains config.
    """
    cur = start
    while True:
        git_path = cur / ".git"
        if git_path.is_dir():
            return git_path
        if git_path.is_file():
            # worktree: .git is a file containing "gitdir: <path>"
            try:
                content = git_path.read_text(encoding="utf-8", errors="ignore").strip()
                # expected: "gitdir: C:/.../something"
                if content.lower().startswith("gitdir:"):
                    gitdir = content.split(":", 1)[1].strip()
                    # resolve relative paths against current directory
                    gitdir_path = (cur / gitdir).resolve() if not Path(gitdir).is_absolute() else Path(gitdir).resolve()
                    return gitdir_path if gitdir_path.exists() else None
            except Exception:
                return None

        parent = cur.parent
        if parent == cur:
            return None
        cur = parent

def _parse_git_config_remote_url(config_text: str, remote_name: str = "origin") -> Optional[str]:
    """
    Very small parser for .git/config
    Returns the url for the given remote if found, else None.
    """
    lines = config_text.splitlines()
    in_remote = False
    target_header = f'[remote "{remote_name}"]'

    # First pass: exact remote_name (origin)
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            in_remote = (s.lower() == target_header.lower())
            continue
        if in_remote and s.lower().startswith("url"):
            # url = ...
            parts = s.split("=", 1)
            if len(parts) == 2:
                return parts[1].strip()

    # Second pass: fallback to first remote if origin not found
    in_any_remote = False
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            # detect any remote section
            m = re.fullmatch(r'\[remote\s+"([^"]+)"\]', s, flags=re.IGNORECASE)
            if m:
                in_any_remote = True
            else:
                in_any_remote = False
            continue
        if in_any_remote and s.lower().startswith("url"):
            parts = s.split("=", 1)
            if len(parts) == 2:
                return parts[1].strip()

    return None

def infer_repo_from_git(root_path: Optional[str]) -> Optional[str]:
    """
    Filesystem-based inference: reads .git/config and extracts remote url.
    No subprocess calls -> no hanging in MCP/stdio.
    """
    try:
        cwd = Path(_clean_path(root_path)) if root_path else Path(os.getcwd())
        if not cwd.exists():
            return None

        git_dir = _find_git_dir(cwd)
        if not git_dir:
            return None

        config_path = git_dir / "config"
        if not config_path.exists():
            return None

        cfg = config_path.read_text(encoding="utf-8", errors="ignore")
        remote_url = _parse_git_config_remote_url(cfg, remote_name="origin")
        if not remote_url:
            return None

        return parse_owner_repo(remote_url)
    except Exception:
        return None

def resolve_repo(repo: Optional[str], root_path: Optional[str]) -> str:
    if repo:
        return parse_owner_repo(repo.strip())

    rp = _clean_path(root_path) if root_path else None
    inferred = infer_repo_from_git(rp)
    if inferred:
        return inferred

    raise ValueError("Cannot resolve repo: provide 'repo' parameter or run inside a git repository")


# -------------------------
# GitHub HTTP helpers
# -------------------------
def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers

async def github_request_json(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    url = f"{GITHUB_API_BASE}{path}"
    
    # Configure SSL verification
    verify: bool | str = SSL_VERIFY
    if SSL_VERIFY and SSL_CERT_FILE:
        verify = SSL_CERT_FILE
    
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, verify=verify) as client:
        r = await client.request(method, url, headers=_github_headers(), params=params)
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub API error {r.status_code}: {r.text[:300]}")
        return r.json()

def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


# -------------------------
# Tools 
# -------------------------

@mcp.tool()
async def github_repo_info(repo: Optional[str] = None, root_path: Optional[str] = None) -> dict[str, Any]:
    """
    Get basic repository info.

    Args:
        repo: optional 'owner/repo' or GitHub URL
        root_path: optional local path to infer repo from git origin
    """
    try:
        r = resolve_repo(repo, root_path)
        data = await github_request_json("GET", f"/repos/{r}")
        # Return dict directly - FastMCP handles serialization
        return {
            "full_name": data.get("full_name"),
            "description": data.get("description"),
            "default_branch": data.get("default_branch"),
            "language": data.get("language"),
            "license": (data.get("license") or {}).get("name"),
            "topics": data.get("topics") or [],
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "open_issues": data.get("open_issues_count"),
            "html_url": data.get("html_url"),
            "clone_url": data.get("clone_url"),
            "updated_at": data.get("updated_at"),
        }
    except Exception as e:
        return {"error": str(e), "tool": "github_repo_info"}


@mcp.tool()
async def github_get_file(
    path: str,
    repo: Optional[str] = None,
    root_path: Optional[str] = None,
    ref: str = "",
    max_chars: int = 20000,
) -> dict[str, Any] | str:
    """
    Get a text file from a GitHub repo (Contents API).

    Args:
        path: file path in repo (e.g. "README.md", ".github/workflows/ci.yml")
        repo: optional 'owner/repo' or GitHub URL
        root_path: optional local path to infer repo
        ref: optional branch/tag/sha
        max_chars: max characters to return from decoded content
    """
    try:
        r = resolve_repo(repo, root_path)
        clean_path = path.strip().lstrip("/")
        if not clean_path:
            return {"error": "path is required", "tool": "github_get_file"}

        params: dict[str, Any] = {}
        if ref.strip():
            params["ref"] = ref.strip()

        data = await github_request_json("GET", f"/repos/{r}/contents/{clean_path}", params=params)

        # If path is a directory, GitHub returns a list
        if isinstance(data, list):
            items = [{
                "type": it.get("type"),
                "name": it.get("name"),
                "path": it.get("path"),
                "sha": it.get("sha"),
                "size": it.get("size"),
            } for it in data]
            return {"repo": r, "path": clean_path, "type": "dir", "items": items}

        # File
        if (data.get("type") or "") != "file":
            return {"repo": r, "path": clean_path, "raw": data}

        encoding = (data.get("encoding") or "").lower()
        content = data.get("content") or ""
        sha = data.get("sha")
        size = data.get("size")

        text_out = ""
        truncated = False

        if encoding == "base64" and content:
            b = base64.b64decode(content.encode("utf-8"), validate=False)
            try:
                text_out = b.decode("utf-8")
            except UnicodeDecodeError:
                text_out = b.decode("latin-1", errors="replace")

            if len(text_out) > max_chars:
                text_out = text_out[:max_chars]
                truncated = True
        else:
            return {
                "repo": r,
                "path": clean_path,
                "sha": sha,
                "size": size,
                "note": "No inline content returned (file may be too large). Use download_url.",
                "download_url": data.get("download_url"),
                "html_url": data.get("html_url"),
            }

        return {
            "repo": r,
            "path": clean_path,
            "sha": sha,
            "size": size,
            "ref": ref.strip() or None,
            "truncated": truncated,
            "text": text_out,
            "download_url": data.get("download_url"),
            "html_url": data.get("html_url"),
        }
    except Exception as e:
        return {"error": str(e), "tool": "github_get_file"}


@mcp.tool()
async def github_compare_commits(
    base: str,
    head: str,
    repo: Optional[str] = None,
    root_path: Optional[str] = None,
    max_files: int = 50,
    max_patch_chars: int = 2000,
) -> dict[str, Any]:
    """
    Compare commits/branches/tags using GitHub compare endpoint.

    Args:
        base: base ref (e.g. "main")
        head: head ref (e.g. "feature-branch")
        repo: optional 'owner/repo' or GitHub URL
        root_path: optional local path to infer repo
        max_files: max files to include
        max_patch_chars: max patch chars per file
    """
    try:
        r = resolve_repo(repo, root_path)
        
        max_files = _clamp(int(max_files), 1, 300)
        max_patch_chars = _clamp(int(max_patch_chars), 200, 10000)

        data = await github_request_json("GET", f"/repos/{r}/compare/{base}...{head}")

        files = data.get("files") or []
        out_files = []
        for f in files[:max_files]:
            patch = f.get("patch")
            if isinstance(patch, str) and len(patch) > max_patch_chars:
                patch = patch[:max_patch_chars] + "\n...TRUNCATED..."
            out_files.append({
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
                "changes": f.get("changes"),
                "patch": patch,
            })

        return {
            "repo": r,
            "base": base,
            "head": head,
            "status": data.get("status"),
            "ahead_by": data.get("ahead_by"),
            "behind_by": data.get("behind_by"),
            "total_commits": data.get("total_commits"),
            "files_count": len(files),
            "files_returned": len(out_files),
            "files": out_files,
            "html_url": data.get("html_url"),
            "permalink_url": data.get("permalink_url"),
        }
    except Exception as e:
        return {"error": str(e), "tool": "github_compare_commits"}


@mcp.tool()
async def github_list_workflow_runs(
    repo: Optional[str] = None,
    root_path: Optional[str] = None,
    workflow_id: str = "",
    branch: str = "",
    status: str = "",
    event: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """
    List GitHub Actions workflow runs.

    Args:
        repo: optional 'owner/repo' or GitHub URL
        root_path: optional local path to infer repo
        workflow_id: optional workflow file name or id (e.g. "ci.yml" or "123456")
        branch: optional branch filter
        status: optional status filter (e.g. "completed", "in_progress", "queued")
        event: optional event filter (e.g. "push", "pull_request")
        limit: max runs (1..100)
    """
    try:
        r = resolve_repo(repo, root_path)
        n = _clamp(int(limit), 1, 100)

        params: dict[str, Any] = {"per_page": n}
        if branch.strip():
            params["branch"] = branch.strip()
        if status.strip():
            params["status"] = status.strip()
        if event.strip():
            params["event"] = event.strip()

        if workflow_id.strip():
            path = f"/repos/{r}/actions/workflows/{workflow_id.strip()}/runs"
        else:
            path = f"/repos/{r}/actions/runs"

        data = await github_request_json("GET", path, params=params)
        runs = data.get("workflow_runs") or data.get("runs") or []

        out_runs = []
        for run in runs[:n]:
            out_runs.append({
                "id": run.get("id"),
                "name": run.get("name"),
                "display_title": run.get("display_title"),
                "event": run.get("event"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
                "run_number": run.get("run_number"),
                "head_branch": run.get("head_branch"),
                "head_sha": run.get("head_sha"),
                "html_url": run.get("html_url"),
            })

        return {
            "repo": r,
            "workflow_id": workflow_id.strip() or None,
            "count": len(out_runs),
            "runs": out_runs,
        }
    except Exception as e:
        return {"error": str(e), "tool": "github_list_workflow_runs"}


@mcp.tool()
async def github_get_workflow_run(
    run_id: int,
    repo: Optional[str] = None,
    root_path: Optional[str] = None,
    include_jobs: bool = True,
    max_jobs: int = 50,
    max_steps: int = 200,
) -> dict[str, Any]:
    """
    Get workflow run details, optionally include jobs/steps summary.

    Args:
        run_id: workflow run id
        repo: optional 'owner/repo' or GitHub URL
        root_path: optional local path to infer repo
        include_jobs: include jobs and steps summary
        max_jobs: cap jobs returned
        max_steps: cap total steps returned
    """
    try:
        r = resolve_repo(repo, root_path)

        run = await github_request_json("GET", f"/repos/{r}/actions/runs/{int(run_id)}")

        out = {
            "repo": r,
            "run": {
                "id": run.get("id"),
                "name": run.get("name"),
                "display_title": run.get("display_title"),
                "event": run.get("event"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
                "run_number": run.get("run_number"),
                "head_branch": run.get("head_branch"),
                "head_sha": run.get("head_sha"),
                "html_url": run.get("html_url"),
                "attempt": run.get("run_attempt"),
            }
        }

        if not include_jobs:
            return out

        jobs_data = await github_request_json("GET", f"/repos/{r}/actions/runs/{int(run_id)}/jobs", params={"per_page": 100})
        jobs = jobs_data.get("jobs") or []

        out_jobs = []
        steps_count = 0

        for j in jobs[:max_jobs]:
            steps_out = []
            for st in (j.get("steps") or []):
                if steps_count >= max_steps:
                    break
                steps_out.append({
                    "name": st.get("name"),
                    "status": st.get("status"),
                    "conclusion": st.get("conclusion"),
                    "number": st.get("number"),
                    "started_at": st.get("started_at"),
                    "completed_at": st.get("completed_at"),
                })
                steps_count += 1

            out_jobs.append({
                "id": j.get("id"),
                "name": j.get("name"),
                "status": j.get("status"),
                "conclusion": j.get("conclusion"),
                "started_at": j.get("started_at"),
                "completed_at": j.get("completed_at"),
                "runner_name": j.get("runner_name"),
                "labels": j.get("labels"),
                "steps": steps_out,
            })

            if steps_count >= max_steps:
                break

        out["jobs"] = {
            "jobs_count": len(jobs),
            "jobs_returned": len(out_jobs),
            "steps_returned": steps_count,
            "truncated": (len(jobs) > len(out_jobs)) or (steps_count >= max_steps),
            "items": out_jobs,
        }

        return out
    except Exception as e:
        return {"error": str(e), "tool": "github_get_workflow_run"}


@mcp.tool()
async def github_list_issues(
    repo: Optional[str] = None,
    root_path: Optional[str] = None,
    state: str = "open",
    labels: str = "",
    limit: int = 20,
    include_prs: bool = False,
) -> dict[str, Any]:
    """
    List issues from a repo (optionally include PRs).

    Args:
        repo: optional 'owner/repo' or URL
        root_path: optional local path to infer repo
        state: open|closed|all
        labels: comma-separated labels filter
        limit: 1..100
        include_prs: if false, PRs are filtered out
    """
    try:
        r = resolve_repo(repo, root_path)
        n = _clamp(int(limit), 1, 100)
        params: dict[str, Any] = {"state": state, "per_page": n, "sort": "updated", "direction": "desc"}
        if labels.strip():
            params["labels"] = labels.strip()

        items = await github_request_json("GET", f"/repos/{r}/issues", params=params)

        out_items = []
        for it in items:
            is_pr = "pull_request" in it
            if (not include_prs) and is_pr:
                continue
            out_items.append({
                "number": it.get("number"),
                "title": it.get("title"),
                "body": it.get("body") or "",
                "state": it.get("state"),
                "is_pr": is_pr,
                "user": (it.get("user") or {}).get("login"),
                "labels": [lbl.get("name") for lbl in (it.get("labels") or []) if isinstance(lbl, dict)],
                "comments": it.get("comments"),
                "created_at": it.get("created_at"),
                "updated_at": it.get("updated_at"),
                "html_url": it.get("html_url"),
            })

        return {"repo": r, "count": len(out_items), "items": out_items}
    except Exception as e:
        return {"error": str(e), "tool": "github_list_issues"}


@mcp.tool()
async def github_get_issue(
    issue_number: int,
    repo: Optional[str] = None,
    root_path: Optional[str] = None,
) -> dict[str, Any]:
    """
    Get a single issue/PR by number.

    Args:
        issue_number: issue number
        repo: optional 'owner/repo' or URL
        root_path: optional local path to infer repo
    """
    try:
        r = resolve_repo(repo, root_path)
        it = await github_request_json("GET", f"/repos/{r}/issues/{int(issue_number)}")

        # Fetch comments
        comments_data = await github_request_json("GET", f"/repos/{r}/issues/{int(issue_number)}/comments")
        comments_list = [
            {
                "id": c.get("id"),
                "user": (c.get("user") or {}).get("login"),
                "body": c.get("body") or "",
                "created_at": c.get("created_at"),
                "updated_at": c.get("updated_at"),
                "html_url": c.get("html_url"),
            }
            for c in (comments_data or [])
        ]

        out = {
            "number": it.get("number"),
            "title": it.get("title"),
            "state": it.get("state"),
            "is_pr": "pull_request" in it,
            "user": (it.get("user") or {}).get("login"),
            "labels": [lbl.get("name") for lbl in (it.get("labels") or []) if isinstance(lbl, dict)],
            "assignees": [a.get("login") for a in (it.get("assignees") or []) if isinstance(a, dict)],
            "comments_count": it.get("comments"),
            "comments": comments_list,
            "created_at": it.get("created_at"),
            "updated_at": it.get("updated_at"),
            "html_url": it.get("html_url"),
            "body": it.get("body") or "",
        }
        return {"repo": r, "issue": out}
    except Exception as e:
        return {"error": str(e), "tool": "github_get_issue"}


@mcp.tool()
async def github_list_commits(
    repo: Optional[str] = None,
    root_path: Optional[str] = None,
    branch: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """
    List recent commits.

    Args:
        repo: optional 'owner/repo' or URL
        root_path: optional local path to infer repo
        branch: optional branch name
        limit: 1..100
    """
    try:
        r = resolve_repo(repo, root_path)
        n = _clamp(int(limit), 1, 100)
        params: dict[str, Any] = {"per_page": n}
        if branch.strip():
            params["sha"] = branch.strip()

        commits = await github_request_json("GET", f"/repos/{r}/commits", params=params)

        out_items = []
        for c in commits:
            commit = c.get("commit") or {}
            author = (commit.get("author") or {})
            out_items.append({
                "sha": (c.get("sha") or ""),
                "message": (commit.get("message") or "").splitlines()[0] if commit.get("message") else "",
                "author": author.get("name"),
                "date": author.get("date"),
                "html_url": c.get("html_url"),
            })

        return {"repo": r, "count": len(out_items), "commits": out_items}
    except Exception as e:
        return {"error": str(e), "tool": "github_list_commits"}


@mcp.tool()
async def github_list_pulls(
    repo: Optional[str] = None,
    root_path: Optional[str] = None,
    state: str = "open",
    base: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """
    List pull requests.

    Args:
        repo: optional 'owner/repo' or URL
        root_path: optional local path to infer repo
        state: open|closed|all
        base: optional base branch filter
        limit: 1..100
    """
    try:
        r = resolve_repo(repo, root_path)
        n = _clamp(int(limit), 1, 100)
        params: dict[str, Any] = {"state": state, "per_page": n, "sort": "updated", "direction": "desc"}
        if base.strip():
            params["base"] = base.strip()

        prs = await github_request_json("GET", f"/repos/{r}/pulls", params=params)
        out_items = []
        for pr in prs:
            head = pr.get("head") or {}
            base = pr.get("base") or {}
            out_items.append({
                "number": pr.get("number"),
                "title": pr.get("title"),
                "body": pr.get("body") or "",
                "state": pr.get("state"),
                "user": (pr.get("user") or {}).get("login"),
                "draft": pr.get("draft"),
                "labels": [lbl.get("name") for lbl in (pr.get("labels") or []) if isinstance(lbl, dict)],
                "assignees": [a.get("login") for a in (pr.get("assignees") or []) if isinstance(a, dict)],
                "comments": pr.get("comments"),
                "commits": pr.get("commits"),
                "additions": pr.get("additions"),
                "deletions": pr.get("deletions"),
                "changed_files": pr.get("changed_files"),
                "mergeable": pr.get("mergeable"),
                "mergeable_state": pr.get("mergeable_state"),
                "merged": pr.get("merged"),
                "head_branch": head.get("ref"),
                "head_sha": head.get("sha"),
                "base_branch": base.get("ref"),
                "created_at": pr.get("created_at"),
                "updated_at": pr.get("updated_at"),
                "html_url": pr.get("html_url"),
            })
        return {"repo": r, "count": len(out_items), "pulls": out_items}
    except Exception as e:
        return {"error": str(e), "tool": "github_list_pulls"}

def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
