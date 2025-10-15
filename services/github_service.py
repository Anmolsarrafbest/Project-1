"""GitHub repository creation and Pages deployment."""
import logging
import asyncio
from typing import Dict
from github import Github, GithubException
import httpx

logger = logging.getLogger(__name__)


class GitHubService:
    """Handle GitHub repository operations and Pages deployment."""
    
    def __init__(self, token: str, username: str, pages_timeout: int = 300):
        """Initialize GitHub client."""
        self.github = Github(token)
        self.token = token  # Store token for API calls
        self.username = username
        self.user = self.github.get_user()
        self.pages_timeout = pages_timeout
    
    async def create_and_deploy(
        self,
        repo_name: str,
        files: Dict[str, str],
        task_id: str
    ) -> Dict[str, str]:
        """
        Create repository and deploy to GitHub Pages.
        
        Args:
            repo_name: Repository name (based on task ID)
            files: Dictionary of {filename: content}
            task_id: Task identifier for description
        
        Returns:
            Dict with repo_url, commit_sha, pages_url
        """
        logger.info(f"Creating repository: {repo_name}")
        
        try:
            # Create repository
            repo = self.user.create_repo(
                name=repo_name,
                description=f"Auto-generated application: {task_id}",
                private=False,
                auto_init=False
            )
            
            logger.info(f"Repository created: {repo.html_url}")
            
            # Upload files
            commit_sha = self._upload_files(repo, files)
            
            # Enable GitHub Pages
            pages_url = self._enable_pages(repo)
            
            # Wait for Pages to be ready (async)
            await self._wait_for_pages(pages_url)
            
            return {
                "repo_url": repo.html_url,
                "commit_sha": commit_sha,
                "pages_url": pages_url
            }
            
        except GithubException as e:
            logger.error(f"GitHub API error: {e}")
            raise
    
    async def update_repository(
        self,
        repo_name: str,
        files: Dict[str, str]
    ) -> Dict[str, str]:
        """
        Update existing repository (for Round 2).
        
        Args:
            repo_name: Repository name
            files: Dictionary of {filename: content} - updated/new files only
        
        Returns:
            Dict with repo_url, commit_sha, pages_url
        """
        logger.info(f"Updating repository: {repo_name}")
        
        try:
            # Get existing repository
            repo = self.user.get_repo(repo_name)
            
            # Upload/update only the files that changed
            commit_sha = self._upload_files(repo, files, "Update application (Round 2)")
            
            # Pages should already be enabled
            pages_url = f"https://{self.username}.github.io/{repo_name}/"
            
            # Wait for Pages to rebuild (async)
            logger.info("Waiting for Pages to rebuild...")
            await asyncio.sleep(15)
            await self._wait_for_pages(pages_url)
            
            return {
                "repo_url": repo.html_url,
                "commit_sha": commit_sha,
                "pages_url": pages_url
            }
            
        except GithubException as e:
            if e.status == 404:
                logger.warning("Repository not found, creating new one")
                return self.create_and_deploy(repo_name, files, repo_name)
            else:
                raise
    
    def get_repository_files(self, repo_name: str) -> Dict[str, str]:
        """
        Fetch all files from an existing repository.
        
        Args:
            repo_name: Repository name
        
        Returns:
            Dictionary of {filename: content}
        """
        logger.info(f"Fetching files from repository: {repo_name}")
        
        try:
            repo = self.user.get_repo(repo_name)
            files = {}
            
            # Get all contents recursively
            contents = repo.get_contents("")
            
            while contents:
                file_content = contents.pop(0)
                
                if file_content.type == "dir":
                    # Add directory contents to queue
                    contents.extend(repo.get_contents(file_content.path))
                else:
                    # Read file content
                    try:
                        # Decode content
                        content = file_content.decoded_content
                        
                        # Try to decode as UTF-8 text
                        try:
                            files[file_content.path] = content.decode('utf-8')
                            logger.info(f"  Fetched: {file_content.path} (text)")
                        except UnicodeDecodeError:
                            # Keep as bytes for binary files
                            files[file_content.path] = content
                            logger.info(f"  Fetched: {file_content.path} (binary)")
                    
                    except Exception as e:
                        logger.warning(f"Could not read {file_content.path}: {e}")
            
            logger.info(f"Fetched {len(files)} files from {repo_name}")
            return files
            
        except GithubException as e:
            if e.status == 404:
                logger.error(f"Repository {repo_name} not found")
                return {}
            else:
                raise
    
    def _upload_files(
        self,
        repo,
        files: Dict[str, str],
        commit_message: str = "Initial commit"
    ) -> str:
        """Upload files to repository."""
        logger.info(f"Uploading {len(files)} files...")
        
        # Determine branch name
        try:
            default_branch = repo.default_branch
        except:
            default_branch = "main"
        
        # Upload each file
        for filename, content in files.items():
            try:
                # Check if file exists
                try:
                    existing = repo.get_contents(filename, ref=default_branch)
                    
                    # Update existing file
                    repo.update_file(
                        path=existing.path,
                        message=commit_message,
                        content=content if isinstance(content, (str, bytes)) else str(content),
                        sha=existing.sha,
                        branch=default_branch
                    )
                    logger.info(f"  Updated: {filename}")
                    
                except GithubException as e:
                    if e.status == 404:
                        # Create new file
                        repo.create_file(
                            path=filename,
                            message=commit_message,
                            content=content if isinstance(content, (str, bytes)) else str(content),
                            branch=default_branch
                        )
                        logger.info(f"  Created: {filename}")
                    else:
                        raise
                        
            except Exception as e:
                logger.error(f"Error uploading {filename}: {e}")
                raise
        
        # Get latest commit SHA
        commits = repo.get_commits(sha=default_branch)
        commit_sha = commits[0].sha
        
        logger.info(f"Commit SHA: {commit_sha}")
        return commit_sha
    
    def _enable_pages(self, repo) -> str:
        """Enable GitHub Pages for the repository."""
        logger.info("Enabling GitHub Pages...")
        
        # Determine branch
        try:
            branch = repo.default_branch
        except:
            branch = "main"
        
        # Use GitHub REST API directly (PyGithub has limited Pages support)
        try:
            url = f"https://api.github.com/repos/{self.username}/{repo.name}/pages"
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json"
            }
            data = {
                "source": {
                    "branch": branch,
                    "path": "/"
                }
            }
            
            with httpx.Client() as client:
                response = client.post(url, json=data, headers=headers)
                
                if response.status_code in [201, 409]:  # 201=created, 409=already exists
                    pages_url = f"https://{self.username}.github.io/{repo.name}/"
                    logger.info(f"GitHub Pages enabled: {pages_url}")
                    return pages_url
                else:
                    logger.warning(f"Pages API response {response.status_code}: {response.text}")
                    # Return expected URL anyway
                    return f"https://{self.username}.github.io/{repo.name}/"
                    
        except Exception as e:
            logger.error(f"Error enabling Pages: {e}")
            # Return expected URL
            return f"https://{self.username}.github.io/{repo.name}/"
    
    async def _wait_for_pages(self, pages_url: str):
        """Wait for GitHub Pages to become available."""
        logger.info(f"Waiting for Pages to be ready: {pages_url}")
        
        import time
        start_time = time.time()
        
        while time.time() - start_time < self.pages_timeout:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(pages_url)
                    
                    if response.status_code == 200:
                        logger.info(f"✓ GitHub Pages is live!")
                        return
                        
            except Exception as e:
                logger.debug(f"Pages not ready yet: {e}")
            
            await asyncio.sleep(10)
        
        logger.warning(
            f"Timeout waiting for Pages (waited {self.pages_timeout}s). "
            f"It may still be deploying..."
        )
