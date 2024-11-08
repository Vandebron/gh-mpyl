"""
Defines information about the repository, any changes made to it and the containing projects.
`mpyl.utilities.repo.Repository` is a facade for the Version Control System.
At this moment Git is the only supported VCS.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

from git import Git, Repo

from ...project import Project


@dataclass(frozen=True)
class Changeset:
    sha: str
    """Git hash for this revision"""
    _files_touched: dict[str, str]

    def files_touched(self, status: Optional[set[str]] = None):
        if not status or len(status) == 0:
            return set(self._files_touched.keys())

        return {file for file, s in self._files_touched.items() if s in status}

    @staticmethod
    def from_diff(sha: str, diff: set[str]):
        changes = {}
        for line in diff:
            parts = line.split("\t")
            if len(parts) == 2:
                changes[parts[1]] = parts[0]
            elif len(parts) == 3 and parts[0].startswith("R"):
                changes[parts[2]] = "R"
            else:
                logging.warning(f"Skipping unparseable diff output line {line}")

        return Changeset(sha, changes)

    @staticmethod
    def empty(sha: str):
        return Changeset(sha=sha, _files_touched={})


@dataclass(frozen=True)
class RepoCredentials:
    name: str
    url: str
    ssh_url: str
    user_name: str
    email: str
    password: str

    @property
    def to_url_with_credentials(self):
        parsed = urlparse(self.url)

        repo = f"{parsed.netloc}{parsed.path}"
        if not self.user_name:
            return f"{parsed.scheme}://{repo}"

        return f"{parsed.scheme}://{self.user_name or ''}{f':{self.password}' if self.password else ''}@{repo}"

    @staticmethod
    def from_config(config: dict):
        url = config["url"]
        ssh_url = f"{url.replace('https://', 'git@').replace('.com/', '.com:')}"
        return RepoCredentials(
            name=url.removeprefix("https://github.com/").removesuffix(".git"),
            url=url,
            ssh_url=ssh_url,
            user_name=config["userName"],
            email=config["email"],
            password=config["password"],
        )


@dataclass(frozen=True)
class RepoConfig:
    main_branch: str
    ignore_patterns: list[str]
    project_sub_folder: str
    repo_credentials: RepoCredentials

    @staticmethod
    def from_config(config: dict):
        git_config = config["vcs"]["git"]
        return RepoConfig.from_git_config(git_config=git_config)

    @staticmethod
    def from_git_config(git_config: dict):
        maybe_remote_config = git_config.get("remote", {})
        return RepoConfig(
            main_branch=git_config["mainBranch"],
            ignore_patterns=git_config.get("ignorePatterns", []),
            project_sub_folder=git_config.get("projectSubFolder", "deployment"),
            repo_credentials=(
                RepoCredentials.from_config(maybe_remote_config)
                if maybe_remote_config
                else None
            ),
        )


class Repository:
    def __init__(self, config: RepoConfig, repo: Union[Repo, None] = None):
        self.config = config
        self._repo = repo or Repo(path=Git().rev_parse("--show-toplevel"))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._repo.close()
        if exc_val:
            raise exc_val
        return self

    @property
    def root_dir(self) -> Path:
        return Path(self._repo.git_dir).parent

    def changes_from_file(
        self, logger: logging.Logger, changed_files_path: str
    ) -> Changeset:
        with open(changed_files_path, encoding="utf-8") as file:
            logger.debug(
                f"Creating Changeset based on changed files in {changed_files_path}"
            )
            changed_files = json.load(file)
            return Changeset(
                sha=self._repo.head.commit.hexsha,
                _files_touched=changed_files,
            )

    def find_projects(self, folder_pattern: str = "") -> list[str]:
        """
        returns a set of all project.yml files
        :param folder_pattern: project paths are filtered on this pattern
        """
        folder = f"*{folder_pattern}*/{self.config.project_sub_folder}"
        projects_pattern = f"{folder}/{Project.project_yaml_file_name()}"
        overrides_pattern = f"{folder}/{Project.project_overrides_yaml_file_pattern()}"

        def files(pattern: str):
            return set(self._repo.git.ls_files(pattern).splitlines())

        def deleted(pattern: str):
            return set(self._repo.git.ls_files("-d", pattern).splitlines())

        projects = files(projects_pattern) | files(overrides_pattern)
        deleted = deleted(projects_pattern) | deleted(overrides_pattern)

        return sorted(projects - deleted)
