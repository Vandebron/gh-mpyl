"""Class that handles remote caching of build artifacts"""
import abc
import os
import shutil
import time
from abc import ABC
from logging import Logger
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

from git import GitCommandError
from github import Github

from ..cli.commands.build.jenkins import get_token
from ..constants import BUILD_ARTIFACTS_FOLDER
from ..project import Project, Target, load_project
from ..steps.deploy.k8s.deploy_config import DeployConfig, get_namespace
from ..steps.models import RunProperties
from ..utilities.github import GithubConfig
from ..utilities.repo import Repository, RepoConfig


class PathTransformer(ABC):
    @abc.abstractmethod
    def artifact_type(self) -> str:
        pass

    @abc.abstractmethod
    def transform_for_read(self, project_path: str) -> Path:
        pass

    @abc.abstractmethod
    def transform_for_write(self, artifact_path: str, project: Project) -> Path:
        pass


class BuildCacheTransformer(PathTransformer):
    def artifact_type(self) -> str:
        return "build_artifacts"

    def transform_for_read(self, project_path: str) -> Path:
        return Path(
            project_path.replace(
                Project.project_yaml_path(), f"deployment/{BUILD_ARTIFACTS_FOLDER}"
            )
        )

    def transform_for_write(self, artifact_path: str, project: Project) -> Path:
        return Path(artifact_path)


class ManifestPathTransformer(PathTransformer):
    deploy_config: DeployConfig
    run_properties: RunProperties

    def artifact_type(self) -> str:
        return "argo"

    def __init__(self, deploy_config: DeployConfig, run_properties: RunProperties):
        self.deploy_config = deploy_config
        self.run_properties = run_properties

    def transform_for_read(self, project_path: str) -> Path:
        return Path(
            project_path.replace(
                Project.project_yaml_path(), self.deploy_config.output_path
            )
        )

    def transform_for_write(self, artifact_path: str, project: Project) -> Path:
        argo_folder_name = self.__get_argo_folder_name()
        namespace = get_namespace(run_properties=self.run_properties, project=project)
        return Path(
            "k8s-manifests",
            project.name,
            argo_folder_name,
            namespace,
        )

    def __get_argo_folder_name(self) -> str:
        if self.run_properties.target in (
            Target.PULL_REQUEST_BASE,
            Target.PULL_REQUEST,
        ):
            return "test"
        return self.run_properties.target.name.lower()


class ArtifactsRepository:
    logger: Logger
    codebase_repo: Repository
    artifact_repo_config: RepoConfig
    path_within_artifact_repo: Path

    def __init__(
        self,
        logger: Logger,
        codebase_repo: Repository,
        artifact_repo_config: RepoConfig,
        path_within_artifact_repo: Path,
    ):
        self.logger = logger
        self.codebase_repo = codebase_repo
        self.artifact_repo_config = artifact_repo_config
        self.path_within_artifact_repo = path_within_artifact_repo

    def pull(self, branch: str) -> None:
        with TemporaryDirectory() as tmp_repo_dir:
            repo_path = Path(tmp_repo_dir)
            with Repository.from_clone(
                config=self.artifact_repo_config, repo_path=Path(tmp_repo_dir)
            ) as artifact_repo:
                if not artifact_repo.remote_branch_exists(branch_name=branch):
                    self.logger.info(
                        f"Not pulling artifacts since branch {branch} does not exist in remote"
                    )
                    return

                self.logger.info(f"Fetching branch '{branch}' from remote")
                artifact_repo.checkout_branch(branch_name=branch)
                path_in_repo = repo_path / self.path_within_artifact_repo
                shutil.copytree(
                    src=path_in_repo,
                    dst=self.codebase_repo.root_dir.absolute(),
                    dirs_exist_ok=True,
                )

    def push(
        self,
        branch: str,
        revision: str,
        repository_url: str,
        project_paths: list[str],
        path_transformer: PathTransformer,
        github_config: Optional[GithubConfig] = None,
    ) -> None:
        with TemporaryDirectory() as tmp_repo_dir:
            repo_path = Path(tmp_repo_dir)
            with Repository.from_clone(
                config=self.artifact_repo_config, repo_path=repo_path
            ) as artifact_repo:
                remote_branch_exists = artifact_repo.remote_branch_exists(
                    branch_name=branch
                )
                if remote_branch_exists:
                    self.logger.info(f"Fetching branch '{branch}' from remote")
                    artifact_repo.checkout_branch(branch_name=branch)
                else:
                    artifact_repo.create_branch(branch_name=branch)

                copied_paths = self.copy_files(
                    project_paths, repo_path, path_transformer
                )

                if not artifact_repo.has_changes:
                    self.logger.info("No changes detected, nothing to push")
                    return

                artifact_repo.stage(".")
                artifact_repo.commit(f"Revision {revision} at {repository_url}")

                try:  # to prevent issues with parallel runs pushing to the same branch
                    self.logger.info("Pushing changes to remote")
                    artifact_repo.push(branch)
                except GitCommandError:
                    self.logger.info("Retrying push after pulling from remote..")
                    time.sleep(1)
                    artifact_repo.pull()
                    artifact_repo.push(branch)

                self.logger.info(
                    f"Pushed {branch} with {copied_paths} copied paths to {artifact_repo.remote_url}"
                )

                if path_transformer.artifact_type() == "argo" and github_config:
                    github = Github(login_or_token=get_token(github_config))
                    repo = github.get_repo(github_config.repository)
                    repo.create_pull(
                        title=branch,
                        body=f"Manifests from {branch} at {repository_url}",
                        head=branch,
                        base="main",
                    )

    def copy_files(
        self,
        project_paths: list[str],
        repo_path: Path,
        transformer: PathTransformer,
    ) -> int:
        path_in_repo = repo_path / self.path_within_artifact_repo
        artifact_paths: dict[Path, Path] = {
            Path(project_path): transformer.transform_for_read(project_path)
            for project_path in project_paths
        }
        existing: dict[Path, Path] = {
            project_path: artifact_path
            for project_path, artifact_path in artifact_paths.items()
            if artifact_path.exists() and artifact_path.is_dir()
        }
        for project_path, file_path in existing.items():
            project = load_project(Path(""), project_path)
            repo_transformed = path_in_repo / transformer.transform_for_write(
                artifact_path=str(file_path), project=project
            )
            self.logger.debug(f"Copying {file_path} to {repo_transformed}")
            os.makedirs(repo_transformed.parent, exist_ok=True)
            shutil.copytree(
                src=self.codebase_repo.root_dir.absolute() / file_path,
                dst=repo_transformed,
                dirs_exist_ok=True,
            )
        return len(existing)
