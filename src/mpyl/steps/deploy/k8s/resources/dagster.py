"""
This module contains the Dagster user-code-deployment values conversion
"""

from dataclasses import dataclass
from typing import Optional

from . import to_dict
from ..chart import ChartBuilder
from .....project import Project, Target, KeyValueProperty, KeyValueRef
from .....steps.models import RunProperties
from .....utilities.helm import shorten_name


@dataclass(frozen=True)
class Constants:
    HELM_CHART_REPO = "https://dagster-io.github.io/helm"


def to_user_code_values(
    builder: ChartBuilder,
    release_name: str,
    name_suffix: str,
    run_properties: RunProperties,
    service_account_override: Optional[str],
) -> dict:
    project = builder.project

    global_override = {}
    if not service_account_override is None:
        global_override = {"global": {"serviceAccountName": service_account_override}}

    combined_sealed_secrets: list[KeyValueProperty] = []
    for deployment in builder.project.deployments:
        combined_sealed_secrets = combined_sealed_secrets + (
            deployment.properties.sealed_secrets if deployment.properties else []
        )
    sealed_secret_refs = []
    for sealed_secret_env in builder.get_sealed_secret_as_env_vars(
        combined_sealed_secrets, builder.release_name
    ):
        sealed_secret_env.value_from.secret_key_ref.name = release_name
        sealed_secret_refs.append(to_dict(sealed_secret_env, skip_none=True))

    combined_secret_refs: list[KeyValueRef] = []
    for deployment in builder.project.deployments:
        combined_secret_refs = combined_secret_refs + (
            deployment.properties.kubernetes if deployment.properties else []
        )
    secret_refs = builder.create_secret_env_vars(combined_secret_refs)

    sealed_secret_manifest = builder.to_sealed_secrets(
        combined_sealed_secrets, release_name
    )
    sealed_secret_manifest.metadata.name = release_name

    extra_manifests = (
        {"extraManifests": [to_dict(sealed_secret_manifest, skip_none=True)]}
        if len(sealed_secret_refs) > 0
        else {}
    )

    return (
        global_override
        | {
            "serviceAccount": {"create": service_account_override is None},
            # ucd, short for user-code-deployment
            "fullnameOverride": f"ucd-{shorten_name(project.name)}{name_suffix}",
            "deployments": [
                {
                    "dagsterApiGrpcArgs": [
                        "--python-file",
                        project.dagster.repo,
                    ],
                    "env": [
                        {"name": key, "value": value}
                        for key, value in get_env_variables(
                            project, run_properties.target
                        ).items()
                    ]
                    + sealed_secret_refs
                    + secret_refs,
                    "envSecrets": [{"name": s.name} for s in project.dagster.secrets],
                    "image": {
                        "pullPolicy": "Always",
                        # The dagster-user-deployment Helm chart expects (for whatever reason) the container image to
                        # be split between "tag" and "repository", so we have to manually remove the version tag from
                        # deploy_image otherwise it will show up twice in the generated manifests.
                        # See helm/dagster/charts/dagster-user-deployments/templates/deployment-user.yaml#L55
                        # and helm/dagster/charts/dagster-user-deployments/templates/helpers/_helpers.tpl#L31-L39
                        # (I'd love to point to the full URL but the linter complains the line is too long........)
                        "tag": run_properties.versioning.identifier,
                        "repository": str(run_properties.deploy_image).removesuffix(
                            f":{run_properties.versioning.identifier}"
                        ),
                    },
                    "labels": {
                        **{
                            k: v
                            for k, v in builder.to_labels().items()
                            if not k.startswith("app.")
                        },
                        "vandebron.nl/dagster": "user-code-deployment",
                    },
                    "includeConfigInLaunchedRuns": {"enabled": True},
                    "name": release_name,
                    "port": 3030,
                    "resources": {
                        "requests": {"memory": "256Mi", "cpu": "50m"},
                        "limits": {"memory": "1024Mi", "cpu": "1000m"},
                    },
                }
            ],
        }
        | extra_manifests
    )


def get_env_variables(project: Project, target: Target) -> dict[str, str]:
    env_variables: dict[str, str] = {
        env_variable.key: env_variable.get_value(target)
        for deployment in project.deployments
        if deployment.properties
        for env_variable in deployment.properties.env
    }

    return env_variables
