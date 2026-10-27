"""
GitHub API Service for fetching repositories and branches.
"""
import logging
import re
import aiohttp
from typing import List, Dict, Any

logger = logging.getLogger("runtimeforce.service.git.github_api")

class GitHubApiError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code

class GitHubApiService:
    def __init__(self):
        self.timeout = 15.0
        self.max_repo_pages = 5
        self.max_branch_pages = 3

    def _get_headers(self, token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RuntimeForce"
        }

    def _validate_repo_name(self, owner: str, repo: str):
        pattern = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
        if not pattern.match(owner) or not pattern.match(repo):
            raise GitHubApiError(code="invalid_repo_name")

    def _handle_error(self, status: int, headers: Any):
        if status == 401:
            raise GitHubApiError(code="github_token_invalid")
        if status in (403, 429):
            remaining = headers.get("x-ratelimit-remaining", "1")
            try:
                if int(remaining) == 0:
                    raise GitHubApiError(code="github_rate_limited")
            except (ValueError, TypeError):
                pass
            if status == 403:
                raise GitHubApiError(code="github_rate_limited")
        if status == 404:
            raise GitHubApiError(code="github_not_found")
        raise GitHubApiError(code="github_unavailable")

    async def _get_json(self, session: aiohttp.ClientSession, url: str, headers: Dict[str, str], path_for_log: str) -> Any:
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=self.timeout)) as response:
                logger.info(f"GitHub API GET {path_for_log} status {response.status}")
                if response.status != 200:
                    self._handle_error(response.status, response.headers)
                return await response.json()
        except GitHubApiError:
            raise
        except Exception as e:
            logger.error(f"GitHub API request failed for {path_for_log}: {e}")
            raise GitHubApiError(code="github_unavailable")

    async def list_repos(self, token: str) -> List[Dict[str, Any]]:
        repos = []
        headers = self._get_headers(token)
        async with aiohttp.ClientSession() as session:
            for page in range(1, self.max_repo_pages + 1):
                url = f"https://api.github.com/user/repos?per_page=100&sort=updated&affiliation=owner,collaborator,organization_member&page={page}"
                path_log = f"/user/repos (page {page})"
                data = await self._get_json(session, url, headers, path_log)
                if not isinstance(data, list):
                    break
                for repo in data:
                    repos.append({
                        "full_name": repo.get("full_name"),
                        "private": bool(repo.get("private")),
                        "default_branch": repo.get("default_branch"),
                        "clone_url": repo.get("clone_url"),
                        "html_url": repo.get("html_url"),
                        "updated_at": repo.get("updated_at")
                    })
                if len(data) < 100:
                    break
        return repos

    async def list_branches(self, token: str, owner: str, repo: str) -> Dict[str, Any]:
        self._validate_repo_name(owner, repo)
        headers = self._get_headers(token)
        async with aiohttp.ClientSession() as session:
            repo_url = f"https://api.github.com/repos/{owner}/{repo}"
            repo_data = await self._get_json(session, repo_url, headers, f"/repos/{owner}/{repo}")
            default_branch = repo_data.get("default_branch", "main")

            branches = []
            for page in range(1, self.max_branch_pages + 1):
                branches_url = f"https://api.github.com/repos/{owner}/{repo}/branches?per_page=100&page={page}"
                path_log = f"/repos/{owner}/{repo}/branches (page {page})"
                data = await self._get_json(session, branches_url, headers, path_log)
                if not isinstance(data, list):
                    break
                for branch in data:
                    name = branch.get("name")
                    if name:
                        branches.append(name)
                if len(data) < 100:
                    break

        return {
            "default_branch": default_branch,
            "branches": branches
        }
