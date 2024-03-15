""" Defines information about the repository, any changes made to it and the containing projects.
`mpyl.utilities.repo.Repository` is a facade for the Version Control System.
At this moment Git is the only supported VCS.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from git import Git, Repo, Remote
from git.objects import Commit
from gitdb.exc import BadName

from ...project import Project
from ...utilities.pyaml_env import parse_config


@dataclass(frozen=True)
class Changeset:
    sha: str
    """Git hash for this revision"""
    files_touched: set[str]
    """Paths to files that were altered in this hash"""
    BREAK_WORD = "hash "

    @staticmethod
    def empty(sha: str):
        return Changeset(sha=sha, files_touched=set())

    @staticmethod
    def from_git_output(git_log_output: str, git_diff_output: str):
        """
        :param git_diff_output: output of `git log --pretty=format:"hash %H" --name-only
        --no-abbrev-commit <from>..<until>`
        :param git_log_output: output of `git diff --name-only <from>..<until>`
        """
        change_set = set(git_diff_output.splitlines())

        sections = []
        current_section: list[str] = []
        lines = git_log_output.splitlines()
        for line in lines:
            if line.startswith(Changeset.BREAK_WORD):
                if current_section:
                    sections.append(current_section)
                current_section = [line.replace(Changeset.BREAK_WORD, "")]
            else:
                current_section.append(line)

        if current_section:
            sections.append(current_section)

        revisions = [
            Changeset(
                section[0],
                {line for line in section[1:] if line in change_set},
            )
            for section in reversed(sections)
        ]
        return revisions


@dataclass(frozen=True)
class RepoCredentials:
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
    repo_credentials: Optional[RepoCredentials]

    @staticmethod
    def from_config(config: dict):
        git_config = config["vcs"]["git"]
        return RepoConfig.from_git_config(git_config=git_config)

    @staticmethod
    def from_git_config(git_config: dict):
        maybe_remote_config = git_config.get("remote", None)
        return RepoConfig(
            main_branch=git_config["mainBranch"],
            ignore_patterns=git_config.get("ignorePatterns", []),
            repo_credentials=RepoCredentials.from_config(maybe_remote_config)
            if maybe_remote_config
            else None,
        )


class Repository:  # pylint: disable=too-many-public-methods
    def __init__(self, config: RepoConfig, repo_path: Optional[Path] = None):
        self._config = config
        self._root_dir = repo_path or Git().rev_parse("--show-toplevel")
        self._repo = Repo(
            path=self._root_dir
        )  # pylint: disable=attribute-defined-outside-init

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._repo.close()
        if exc_val:
            raise exc_val
        return self

    @staticmethod
    def from_clone(config: RepoConfig, repo_path: Path):
        creds = config.repo_credentials
        if not creds:
            raise ValueError("Cannot clone repository without credentials")

        repo = Repo.clone_from(
            url=creds.to_url_with_credentials,
            to_path=repo_path,
        )
        user_name = creds.user_name
        with repo.config_writer() as writer:
            writer.set_value("user", "name", user_name)
            writer.set_value("user", "email", creds.email or "somebody@somwhere.com")

        return Repository(config=config, repo_path=repo_path)

    @staticmethod
    def from_shallow_diff_clone(
        branch_name: str, url: str, base_branch: str, config_path: Path, path: Path
    ):
        Repo.clone_from(
            url,
            path,
            allow_unsafe_protocols=True,
            shallow_exclude=base_branch,
            single_branch=True,
            branch=branch_name,
        )
        return Repository(RepoConfig.from_config(parse_config(config_path)))

    @property
    def has_valid_head(self):
        return self._repo.head.is_valid()

    @property
    def get_sha(self):
        return self._repo.head.commit.hexsha

    @property
    def get_branch(self) -> Optional[str]:
        if self._repo.head.is_detached:
            return None
        return self._repo.active_branch.name

    def _safe_ref_parse(self, branch: str) -> Optional[Commit]:
        try:
            return self._repo.rev_parse(branch)
        except BadName as exc:
            logging.debug(f"Does not exist: {exc}")
            return None

    @property
    def root_commit_hex(self) -> str:
        return self._repo.git.rev_list("--max-parents=0", "HEAD").splitlines()[-1]

    @property
    def base_revision(self) -> Optional[Commit]:
        main = self.main_origin_branch
        return self._safe_ref_parse(main)

    @property
    def get_tag(self) -> Optional[str]:
        current_revision = self._repo.head.commit
        current_tag = self._repo.git.tag(current_revision, points_at=True)
        logging.debug(f"Current revision: {current_revision} tag: {current_tag}")
        return current_tag

    @property
    def remote_url(self) -> Optional[str]:
        if self._repo.remotes:
            return self._repo.remote().url
        return None

    @property
    def root_dir(self) -> Path:
        return Path(self._root_dir)

    @property
    def main_branch(self) -> str:
        return self._config.main_branch.split("/")[-1]

    @property
    def main_origin_branch(self) -> str:
        parts = self._config.main_branch.split("/")
        if len(parts) > 1:
            return "/".join(parts)
        return f"origin/{self.main_branch}"

    def fit_for_tag_build(self, tag: str) -> bool:
        return len(self.changes_in_tagged_commit(tag).files_touched) > 0

    def __get_filter_patterns(self):
        return ["--"] + [f":!{pattern}" for pattern in self._config.ignore_patterns]

    # Only used in the repo status command, can be deleted later
    def changes_between(
        self, base_revision: str, head_revision: str
    ) -> list[Changeset]:
        command = [
            f'--pretty=format:"{Changeset.BREAK_WORD}%H"',
            "--name-only",
            "--no-abbrev-commit",
            f"{base_revision}..{head_revision}",
            self.__get_filter_patterns(),
        ]

        revs = self._repo.git.log(*command).replace('"', "")
        changed_files = self._repo.git.diff(
            f"{base_revision}..{head_revision}", name_only=True
        )
        return Changeset.from_git_output(revs, changed_files)

    def changes_in_branch(self) -> Changeset:
        return Changeset(self.get_sha, self.changed_files_in_branch())

    def changed_files_in_branch(self) -> set[str]:
        # TODO pass the base_branch as a build parameter, not all branches  # pylint: disable=fixme
        #  are created from the main branch
        base_branch = self.main_origin_branch
        changed_files = self._repo.git.diff(
            f"{base_branch}...HEAD", name_only=True
        ).splitlines()
        return set(changed_files)

    def unversioned_files(self) -> set[str]:
        changed: set[str] = set(
            self._repo.git.diff(
                self.__get_filter_patterns(), None, name_only=True
            ).splitlines()
        )
        return changed.union(self._repo.untracked_files)

    def changes_in_branch_including_unversioned_files(self) -> Changeset:
        return Changeset(
            sha=self.get_sha,
            files_touched=(self.changed_files_in_branch() | self.unversioned_files()),
        )

    def changes_in_tagged_commit(self, current_tag: str) -> Changeset:
        curr_rev_tag = self.get_tag

        if curr_rev_tag != current_tag:
            logging.error(f"HEAD is at {curr_rev_tag} not at expected `{current_tag}`")
            return Changeset.empty(self.get_sha)

        return self.changes_in_merge_commit()

    def changes_in_merge_commit(self) -> Changeset:
        parent_revs = self._repo.head.commit.parents
        if not parent_revs:
            logging.error(
                "HEAD is not at merge commit, cannot determine changed files."
            )
            return Changeset.empty(self.get_sha)
        logging.debug(f"Parent revisions: {parent_revs}")
        files_changed = self._repo.git.diff(
            f"{str(self._repo.head.commit)}..{str(parent_revs[0])}", name_only=True
        ).splitlines()
        return Changeset(sha=str(self.get_sha), files_touched=files_changed)

    def init_remote(self, url: Optional[str]) -> Remote:
        if url:
            return self._repo.create_remote("origin", url=url)

        return self._repo.remote()

    def fetch_main_branch(self):
        return self._repo.remote().fetch(
            f"{self.main_branch}:refs/remotes/{self.main_origin_branch}"
        )

    def fetch_pr(self, pr_number: int):
        return self._repo.remote().fetch(f"pull/{pr_number}/head:PR-{pr_number}")

    def create_branch(self, branch_name: str):
        return self._repo.git.checkout("-b", f"{branch_name}")

    @property
    def has_changes(self) -> bool:
        return self._repo.is_dirty(untracked_files=True)

    def stage(self, path: str):
        return self._repo.git.add(path)

    def commit(self, message: str):
        return self._repo.git.commit("-m", message)

    def pull(self):
        return self._repo.git.pull()

    def push(self, branch: str):
        return self._repo.git.push("--set-upstream", "origin", branch)

    def checkout_branch(self, branch_name: str):
        self._repo.git.switch(branch_name)

    def local_branch_exists(self, branch_name: str) -> bool:
        local_branches = [
            branch.strip(" ") for branch in self._repo.git.branch("--list").splitlines()
        ]
        logging.debug(f"Found local branches: {local_branches}")
        return branch_name in local_branches

    def remote_branch_exists(self, branch_name: str) -> bool:
        return self._repo.git.ls_remote("origin", branch_name) != ""

    def delete_local_branch(self, branch_name: str):
        self._repo.git.branch("-D", branch_name)

    def find_projects(self, folder_pattern: str = "") -> list[str]:
        """returns a set of all project.yml files
        :type folder_pattern: project paths are filtered on this pattern
        """
        projects = set(
            self._repo.git.ls_files(
                f"*{folder_pattern}*/{Project.project_yaml_path()}"
            ).splitlines()
        ) | set(
            self._repo.git.ls_files(
                f"*{folder_pattern}*/{Project.project_overrides_yml_pattern()}"
            ).splitlines()
        )
        return sorted(projects)
