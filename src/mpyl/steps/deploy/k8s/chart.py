"""
Data classes for the composition of Custom Resource Definitions.
More info: https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/
"""

import itertools
from dataclasses import dataclass
from typing import Optional

from kubernetes.client import (
    V1Deployment,
    V1Container,
    V1DeploymentSpec,
    V1ObjectMeta,
    V1PodSpec,
    V1LabelSelector,
    V1ContainerPort,
    V1EnvVar,
    V1Service,
    V1ServiceSpec,
    V1ServicePort,
    V1ServiceAccount,
    V1LocalObjectReference,
    V1EnvVarSource,
    V1SecretKeySelector,
    V1Probe,
    ApiClient,
    V1HTTPGetAction,
    V1ResourceRequirements,
    V1PodTemplateSpec,
    V1DeploymentStrategy,
    V1Job,
    V1JobSpec,
    V1CronJob,
    V1CronJobSpec,
    V1JobTemplateSpec,
    V1Role,
    V1RoleBinding,
    V1PolicyRule,
    V1RoleRef,
    RbacV1Subject,
)

from . import substitute_namespaces
from .resources import (
    CustomResourceDefinition,
    to_dict,
)
from .resources.prometheus import V1PrometheusRule, V1ServiceMonitor
from .resources.sealed_secret import V1SealedSecret
from .resources.traefik import (
    V1AlphaIngressRoute,
    V1AlphaMiddleware,
    HostWrapper,
)
from ... import deploy
from ...input import Input
from ....constants import (
    PR_NUMBER_PLACEHOLDER,
    SERVICE_NAME_PLACEHOLDER,
    NAMESPACE_PLACEHOLDER,
)
from ....project import (
    Project,
    KeyValueProperty,
    Probe,
    Deployment,
    TargetProperty,
    Resources,
    Target,
    Traefik,
    TraefikHost,
    Alert,
    KeyValueRef,
    Metrics,
    TraefikAdditionalRoute,
)
from ....utilities import replace_item

# Determined (unscientifically) to be sensible factors.
# Based on actual CPU usage, pods rarely use more than 10% of the allocated CPU. 60% usage is healthy, so we
# scale down to 20% in order to keep some slack.
# Memory is cheaper, but poses a harder limit (OOM when exceeding limit), so we are more generous than with CPU.
CPU_REQUEST_SCALE_FACTOR = 0.2
MEM_REQUEST_SCALE_FACTOR = 0.5


def try_parse_target(value: object, target: Target):
    if isinstance(value, dict):
        maybe_value = TargetProperty.from_config(value).get_value(target)
        if maybe_value:
            return maybe_value

    return value


def with_target(dictionary: dict, target: Target) -> dict:
    def with_targets_parsed(obj):
        if isinstance(obj, dict):
            return type(obj)(
                (k, try_parse_target(with_targets_parsed(v), target))
                for k, v in obj.items()
            )

        return obj

    return with_targets_parsed(dictionary)


@dataclass(frozen=True)
class ResourceDefaults:
    instances: TargetProperty[int]
    cpus: TargetProperty[float]
    mem: TargetProperty[int]

    @staticmethod
    def from_config(resources: dict):
        limit = resources["limit"]
        return ResourceDefaults(
            instances=TargetProperty.from_config(resources["instances"]),
            cpus=TargetProperty.from_config(limit["cpus"]),
            mem=TargetProperty.from_config(limit["mem"]),
        )


@dataclass(frozen=True)
class DefaultWhitelistAddress:
    name: str
    host: TargetProperty[list[str]]

    @staticmethod
    def from_config(values: dict):
        return DefaultWhitelistAddress(
            name=values["name"],
            host=TargetProperty.from_config(values),
        )


@dataclass(frozen=True)
class DefaultWhitelists:
    default: list[str]
    addresses: list[DefaultWhitelistAddress]

    @staticmethod
    def from_config(values: Optional[dict]):
        if values is None:
            return None
        return DefaultWhitelists(
            default=values["default"],
            addresses=[
                DefaultWhitelistAddress.from_config(address)
                for address in values["addresses"]
            ],
        )


@dataclass(frozen=True)
class TraefikConfig:
    http_middleware: str
    tls: str

    @staticmethod
    def from_config(values: Optional[dict]):
        if not values:
            return None
        return TraefikConfig(
            http_middleware=values["httpMiddleware"],
            tls=values["tls"],
        )


@dataclass(frozen=True)
class DeploymentDefaults:
    resources_defaults: ResourceDefaults
    liveness_probe_defaults: dict
    startup_probe_defaults: dict
    job_defaults: dict
    traefik_defaults: Traefik
    white_lists: DefaultWhitelists
    deployment_strategy: dict
    additional_routes: list[TraefikAdditionalRoute]
    traefik_config: TraefikConfig

    @staticmethod
    def from_config(config: dict):
        deployment_values = config.get("project", {}).get("deployment", {})
        if deployment_values is None:
            raise KeyError("Configuration should have project.deployment section")
        kubernetes = deployment_values.get("kubernetes", {})
        additional_routes = deployment_values.get("additionalTraefikRoutes", [])
        traefik_config = TraefikConfig.from_config(
            deployment_values.get("traefikDefaults", None)
        )
        return DeploymentDefaults(
            resources_defaults=ResourceDefaults.from_config(kubernetes["resources"]),
            liveness_probe_defaults=kubernetes["livenessProbe"],
            startup_probe_defaults=kubernetes["startupProbe"],
            job_defaults=kubernetes.get("job", {}),
            traefik_defaults=Traefik.from_config(deployment_values.get("traefik", {})),
            white_lists=DefaultWhitelists.from_config(config.get("whiteLists", {})),
            deployment_strategy=config["kubernetes"]["deploymentStrategy"],
            additional_routes=list(
                map(TraefikAdditionalRoute.from_config, additional_routes)
            ),
            traefik_config=traefik_config,
        )


class ChartBuilder:
    step_input: Input
    project: Project
    target: Target
    release_name: str
    config_defaults: DeploymentDefaults
    namespace: str
    deployment_strategy: Optional[dict]

    def __init__(self, step_input: Input):
        self.step_input = step_input
        self.project = self.step_input.project
        self.config_defaults = DeploymentDefaults.from_config(
            step_input.run_properties.config
        )

        if len(self.project.deployments) == 0:
            raise AttributeError("Deployments field should be set")
        self.target = step_input.run_properties.target
        self.release_name = self.project.name.lower()
        self.namespace = (
            step_input.run_properties.versioning.identifier
            if step_input.run_properties.target == Target.PULL_REQUEST
            else self.project.namespace(step_input.run_properties.target)
        )

    def to_labels(self, deployment_name: Optional[str] = None) -> dict:
        run_properties = self.step_input.run_properties

        app_labels = {
            "name": self.release_name,
            "app.kubernetes.io/version": run_properties.versioning.identifier,
            "app.kubernetes.io/name": self.release_name,
            "app.kubernetes.io/instance": self.release_name,
        }

        if deployment_name:
            app_labels.update({"vandebron.nl/deployment": deployment_name.lower()})

        if len(self.project.maintainer) > 0:
            app_labels["maintainers"] = ".".join(self.project.maintainer).replace(
                " ", "_"
            )
            app_labels["maintainer"] = self.project.maintainer[0].replace(" ", "_")

        app_labels["version"] = run_properties.versioning.identifier

        if run_properties.versioning.revision:
            app_labels["revision"] = run_properties.versioning.revision

        return app_labels

    def _to_annotations(self) -> dict:
        return {"description": self.project.description}

    def _to_image_annotation(self) -> dict:
        return {"image": self._get_image()}

    def _to_object_meta(
        self,
        name: Optional[str] = None,
        annotations: Optional[dict] = None,
        deployment_name: Optional[str] = None,
    ) -> V1ObjectMeta:
        return V1ObjectMeta(
            name=name if name else self.release_name,
            labels=self.to_labels(deployment_name=deployment_name),
            annotations=annotations,
        )

    def _to_selector(self, deployment: Deployment):
        return V1LabelSelector(
            match_labels={
                "app.kubernetes.io/instance": self.release_name,
                "app.kubernetes.io/name": self.release_name,
                "vandebron.nl/deployment": deployment.name.lower(),
            }
        )

    @staticmethod
    def _to_k8s_model(values: dict, model_type):
        return ApiClient()._ApiClient__deserialize(  # pylint: disable=protected-access
            values, model_type
        )

    @staticmethod
    def _to_probe(probe: Optional[Probe], defaults: dict, target: Target) -> V1Probe:
        values = defaults.copy()
        if probe:
            values.update(probe.values)
        v1_probe: V1Probe = ChartBuilder._to_k8s_model(values, V1Probe)
        path = probe.path.get_value(target) if probe else None
        v1_probe.http_get = V1HTTPGetAction(
            path="/health" if path is None else path, port="port-0"
        )
        return v1_probe

    def _construct_probes(
        self, deployment: Deployment
    ) -> tuple[Optional[V1Probe], Optional[V1Probe]]:
        """
        Construct kubernetes probes based on project yaml values and default values in mpyl_config.yaml.

        NOTE: If no startup probe was provided in the project yaml, but a liveness probe was,
              this method constructs a startup probe from the default values!
        :return:
        """
        liveness_probe = (
            ChartBuilder._to_probe(
                deployment.kubernetes.liveness_probe,
                self.config_defaults.liveness_probe_defaults,
                self.target,
            )
            if deployment.kubernetes.liveness_probe
            else None
        )

        startup_probe = (
            ChartBuilder._to_probe(
                deployment.kubernetes.startup_probe,
                self.config_defaults.startup_probe_defaults,
                self.target,
            )
            if deployment.kubernetes.liveness_probe  # Should check for startup_probe in the future?
            else None
        )

        return liveness_probe, startup_probe

    def to_service(self, deployment: Deployment) -> V1Service:
        service_ports = list(
            map(
                lambda key: V1ServicePort(
                    port=int(key),
                    target_port=int(deployment.kubernetes.port_mappings[key]),
                    protocol="TCP",
                    name=f"{key}-webservice-port",
                ),
                deployment.kubernetes.port_mappings.keys(),
            )
        )

        return V1Service(
            api_version="v1",
            kind="Service",
            metadata=V1ObjectMeta(
                annotations=self._to_annotations(),
                name=deployment.name.lower(),
                labels=self.to_labels(),
            ),
            spec=V1ServiceSpec(
                type="ClusterIP",
                ports=service_ports,
                selector=self._to_selector(deployment).match_labels,
            ),
        )

    def to_job(self, deployment: Deployment) -> V1Job:
        job_container = V1Container(
            name=self.release_name,
            image=self._get_image(),
            env=self._get_env_vars(deployment),
            image_pull_policy="Always",
            resources=self._get_resources(deployment),
            command=(
                deployment.kubernetes.command.get_value(self.target).split(" ")
                if deployment.kubernetes.command
                else None
            ),
            args=(
                deployment.kubernetes.args.get_value(self.target).split(" ")
                if deployment.kubernetes.args
                else None
            ),
        )

        pod_template = V1PodTemplateSpec(
            metadata=self._to_object_meta(annotations=self._to_image_annotation()),
            spec=V1PodSpec(
                containers=[job_container],
                service_account=self.release_name,
                service_account_name=self.release_name,
                restart_policy="Never",
            ),
        )

        defaults = with_target(self.config_defaults.job_defaults, self.target)
        specified = defaults | (
            with_target(deployment.kubernetes.job.job, self.target)
            if deployment.kubernetes.job
            else {}
        )

        template_dict = to_dict(pod_template)
        specified["template"] = template_dict
        spec: V1JobSpec = ChartBuilder._to_k8s_model(specified, V1JobSpec)

        return V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=self._to_object_meta(
                annotations={
                    "argocd.argoproj.io/sync-options": "Force=true,Replace=true"
                }
            ),
            spec=spec,
        )

    def to_cron_job(self, deployment: Deployment) -> V1CronJob:
        if deployment.kubernetes.job is None:
            raise ValueError("CronJob deployment must have a job configuration")
        values = deployment.kubernetes.job.cron.get_value(self.target)
        job_template = V1JobTemplateSpec(spec=self.to_job(deployment).spec)
        template_dict = to_dict(job_template)
        values["jobTemplate"] = template_dict
        v1_cron_job_spec: V1CronJobSpec = ChartBuilder._to_k8s_model(
            values, V1CronJobSpec
        )
        return V1CronJob(
            api_version="batch/v1",
            kind="CronJob",
            metadata=self._to_object_meta(),
            spec=v1_cron_job_spec,
        )

    def to_prometheus_rule(
        self, alerts: list[Alert], deployment_name: str
    ) -> V1PrometheusRule:
        return V1PrometheusRule(
            metadata=self._to_object_meta(
                name=f"{deployment_name.lower()}-prometheus-rule"
            ),
            alerts=alerts,
        )

    def to_service_monitor(
        self, metrics: Metrics, default_port: int
    ) -> V1ServiceMonitor:
        return V1ServiceMonitor(
            metadata=self._to_object_meta(
                name=f"{self.project.name.lower()}-service-monitor"
            ),
            metrics=metrics,
            default_port=default_port,
            namespace=self.namespace,
            release_name=self.release_name,
        )

    @staticmethod
    def find_default_port(mappings: dict[int, int]) -> int:
        found = next(iter(mappings.keys()))
        if found:
            return int(found)
        raise KeyError("No default port found. Did you define a port mapping?")

    def create_host_wrappers(self, deployment: Deployment) -> list[HostWrapper]:
        hosts: list[TraefikHost] = (
            deployment.traefik.hosts
            if deployment.traefik and deployment.traefik.hosts
            else self.config_defaults.traefik_defaults.hosts
        )
        address_dictionary = {
            address.name: address.host.get_value(self.target)
            for address in self.config_defaults.white_lists.addresses
        }

        def to_white_list(
            configured: Optional[TargetProperty[list[str]]],
        ) -> dict[str, list[str]]:
            white_lists = self.config_defaults.white_lists.default
            if configured and configured.get_value(self.target):
                white_lists = white_lists + configured.get_value(self.target)

            return dict(
                filter(lambda x: x[0] in white_lists, address_dictionary.items())
            )

        return [
            HostWrapper(
                traefik_host=host,
                name=self.release_name,
                index=idx,
                service_port=(
                    host.service_port
                    if host.service_port
                    else ChartBuilder.find_default_port(
                        deployment.kubernetes.port_mappings
                    )
                ),
                white_lists=to_white_list(host.whitelists),
                tls=host.tls.get_value(self.target) if host.tls else None,
                insecure=host.insecure,
                additional_route=(
                    next(
                        (
                            route
                            for route in self.config_defaults.additional_routes
                            if route.name == host.additional_route
                        ),
                        None,
                    )
                    if host.additional_route
                    else None
                ),
            )
            for idx, host in enumerate(hosts)
        ]

    def _replace_traefik_placeholders(self, traefik_object: dict | list):
        traefik_object = replace_item(
            traefik_object,
            PR_NUMBER_PLACEHOLDER,
            str(self.step_input.run_properties.versioning.pr_number),
        )
        traefik_object = replace_item(
            traefik_object, SERVICE_NAME_PLACEHOLDER, self.release_name
        )
        traefik_object = replace_item(
            traefik_object, NAMESPACE_PLACEHOLDER, self.namespace
        )
        return traefik_object

    def to_ingress(self, deployment: Deployment) -> Optional[V1AlphaIngressRoute]:
        """Converts the deployment traefik ingress routes configuration to a V1AlphaIngressRoute object."""
        ingress_route_spec = (
            self._replace_traefik_placeholders(
                deployment.traefik.ingress_routes.get_value(self.target)
            )
            if deployment.traefik and deployment.traefik.ingress_routes
            else None
        )

        if not ingress_route_spec:
            return None

        return V1AlphaIngressRoute.from_spec(
            metadata=self._to_object_meta(name=f"ingress-routes-{self.release_name}"),
            spec=ingress_route_spec,
        )

    def to_ingress_routes(
        self, deployment: Deployment, https: bool
    ) -> list[V1AlphaIngressRoute]:
        hosts = self.create_host_wrappers(deployment)
        return [
            V1AlphaIngressRoute.from_hosts(
                metadata=self._to_object_meta(
                    name=f"{self.release_name}-ingress-{i}-http"
                    + ("s" if https else "")
                ),
                host=host,
                target=self.target,
                namespace=self.namespace,
                pr_number=self.step_input.run_properties.versioning.pr_number,
                https=https,
                middlewares_override=[],
                entrypoints_override=[],
                http_middleware=self.config_defaults.traefik_config.http_middleware,
                default_tls=self.config_defaults.traefik_config.http_middleware,
            )
            for i, host in enumerate(hosts)
        ]

    def to_additional_routes(self, deployment: Deployment) -> list[V1AlphaIngressRoute]:
        hosts = self.create_host_wrappers(deployment)
        return [
            V1AlphaIngressRoute.from_hosts(
                metadata=self._to_object_meta(
                    name=f"{self.release_name}-{host.additional_route.name}-{i}"
                ),
                host=host,
                target=self.target,
                namespace=self.namespace,
                pr_number=self.step_input.run_properties.versioning.pr_number,
                https=True,
                middlewares_override=host.additional_route.middlewares,
                entrypoints_override=host.additional_route.entrypoints,
                http_middleware=self.config_defaults.traefik_config.http_middleware,
                default_tls=self.config_defaults.traefik_config.http_middleware,
            )
            for i, host in enumerate(hosts)
            if host.additional_route
        ]

    def to_middlewares(self, deployment: Deployment) -> dict[str, V1AlphaMiddleware]:
        hosts: list[HostWrapper] = self.create_host_wrappers(deployment)
        middlewares = (
            self._replace_traefik_placeholders(
                deployment.traefik.middlewares.get_value(self.target)
            )
            if deployment.traefik and deployment.traefik.middlewares
            else []
        )
        adjusted_middlewares = {
            f'middleware-{middleware["metadata"]["name"]}': V1AlphaMiddleware.from_spec(
                metadata=self._to_object_meta(name=middleware["metadata"]["name"]),
                spec=middleware["spec"],
            )
            for middleware in middlewares
        }

        def to_metadata(host: HostWrapper) -> V1ObjectMeta:
            metadata = self._to_object_meta(name=host.full_name)
            metadata.annotations = {
                k: ", ".join(v) for k, v in host.white_lists.items()
            }
            return metadata

        return {
            host.full_name: V1AlphaMiddleware.from_source_ranges(
                metadata=to_metadata(host),
                source_ranges=list(itertools.chain(*host.white_lists.values())),
            )
            for host in hosts
        } | adjusted_middlewares

    def to_service_account(self) -> V1ServiceAccount:
        secrets = [
            ChartBuilder._to_k8s_model(
                {"name": "aws-ecr"},
                V1LocalObjectReference,
            )
        ]
        return V1ServiceAccount(
            api_version="v1",
            kind="ServiceAccount",
            metadata=self._to_object_meta(),
            image_pull_secrets=secrets,
        )

    def to_role(self, role: dict) -> V1Role:
        return V1Role(
            api_version="rbac.authorization.k8s.io/v1",
            kind="Role",
            metadata=self._to_object_meta(),
            rules=[
                ChartBuilder._to_k8s_model({"apiGroups": [""]} | role, V1PolicyRule)
            ],
        )

    def to_role_binding(self) -> V1RoleBinding:
        return V1RoleBinding(
            api_version="rbac.authorization.k8s.io/v1",
            kind="RoleBinding",
            metadata=self._to_object_meta(),
            role_ref=V1RoleRef(
                api_group="rbac.authorization.k8s.io",
                kind="Role",
                name=self.release_name,
            ),
            subjects=[
                RbacV1Subject(
                    kind="ServiceAccount",
                    name=self.release_name,
                    namespace=self.namespace,
                )
            ],
        )

    def to_sealed_secrets(
        self, sealed_secrets: list[KeyValueProperty], name: str
    ) -> V1SealedSecret:
        secrets: dict[str, str] = {}
        for secret in sealed_secrets:
            secrets[secret.key] = secret.get_value(self.target)

        return V1SealedSecret(name=name.lower(), secrets=secrets)

    @staticmethod
    def _to_resource_requirements(
        resources: Resources, defaults: ResourceDefaults, target: Target
    ):
        cpus = (
            resources.limit.cpus
            if resources.limit and resources.limit.cpus
            else defaults.cpus
        )

        cpus_limit: float = cpus.get_value(target=target) * 1000.0

        cpus_request: float = (
            resources.request.cpus.get_value(target=target) * 1000.0
            if resources.request and resources.request.cpus
            else cpus_limit * CPU_REQUEST_SCALE_FACTOR
        )

        mem = (
            resources.limit.mem
            if resources.limit and resources.limit.mem
            else defaults.mem
        )
        mem_limit: float = mem.get_value(target=target)

        mem_request: float = (
            resources.request.mem.get_value(target=target)
            if resources.request and resources.request.mem
            else mem_limit * MEM_REQUEST_SCALE_FACTOR
        )

        return V1ResourceRequirements(
            limits={"cpu": f"{int(cpus_limit)}m", "memory": f"{int(mem_limit)}Mi"},
            requests={
                "cpu": f"{int(cpus_request)}m",
                "memory": f"{int(mem_request)}Mi",
            },
        )

    def _get_image(self):
        image = self.step_input.run_properties.deploy_image
        if image:
            return image
        raise ValueError("Unable to generate a Helm chart without a Docker image")

    def _get_resources(self, deployment: Deployment) -> V1ResourceRequirements:
        resources = deployment.kubernetes.resources
        defaults = self.config_defaults.resources_defaults
        return ChartBuilder._to_resource_requirements(resources, defaults, self.target)

    def _create_sealed_secret_env_vars(
        self, secret_list: list[KeyValueProperty], secret_name: str
    ) -> list[V1EnvVar]:
        return [
            V1EnvVar(
                name=e.key,
                value_from=V1EnvVarSource(
                    secret_key_ref=V1SecretKeySelector(
                        key=e.key, name=secret_name.lower(), optional=False
                    )
                ),
            )
            for e in secret_list
        ]

    def _map_key_value_refs(self, ref: KeyValueRef) -> V1EnvVar:
        value_from = self._to_k8s_model(ref.value_from, V1EnvVarSource)

        return V1EnvVar(name=ref.key, value_from=value_from)

    def _create_secret_env_vars(self, secret_list: list[KeyValueRef]) -> list[V1EnvVar]:
        return list(map(self._map_key_value_refs, secret_list))

    @staticmethod
    def extract_raw_env(target: Target, env: list[KeyValueProperty]):
        raw_env_vars = {
            e.key: e.get_value(target) for e in env if e.get_value(target) is not None
        }
        return raw_env_vars

    def get_sealed_secret_as_env_vars(
        self,
        sealed_secrets: list[KeyValueProperty],
        secret_name: str,
    ) -> list[V1EnvVar]:
        sealed_secrets_for_target = list(
            filter(lambda v: v.get_value(self.target) is not None, sealed_secrets)
        )
        return self._create_sealed_secret_env_vars(
            sealed_secrets_for_target, secret_name
        )

    def _get_env_vars(self, deployment: Deployment) -> list[V1EnvVar]:
        raw_env_vars = (
            self.extract_raw_env(self.target, deployment.properties.env)
            if deployment.properties
            else {}
        )
        pr_identifier = (
            None
            if self.step_input.run_properties.versioning.tag
            else self.step_input.run_properties.versioning.pr_number
        )

        processed_env_vars = substitute_namespaces(
            env_vars=raw_env_vars,
            all_projects=self.step_input.run_plan.all_known_projects,
            projects_to_deploy=self.step_input.run_plan.get_projects_for_stage_name(
                deploy.STAGE_NAME, use_full_plan=True
            ),
            target=self.target,
            pr_identifier=pr_identifier,
        )
        env_vars = [
            V1EnvVar(name=key, value=value) for key, value in processed_env_vars.items()
        ]
        secrets = (
            self._create_secret_env_vars(deployment.properties.kubernetes)
            if deployment.properties
            else []
        )
        sealed_secrets = (
            self.get_sealed_secret_as_env_vars(
                deployment.properties.sealed_secrets, deployment.name
            )
            if deployment.properties
            else []
        )

        return env_vars + sealed_secrets + secrets

    def to_deployment(self, deployment: Deployment) -> V1Deployment:
        ports = [
            V1ContainerPort(
                container_port=deployment.kubernetes.port_mappings[key],
                protocol="TCP",
                name=f"port-{idx}",
            )
            for idx, key in enumerate(deployment.kubernetes.port_mappings.keys())
        ]

        resources = deployment.kubernetes.resources
        defaults = self.config_defaults.resources_defaults
        liveness_probe, startup_probe = self._construct_probes(deployment)

        container = V1Container(
            name="service",
            image=self._get_image(),
            env=self._get_env_vars(deployment),
            ports=ports,
            image_pull_policy="Always",
            resources=ChartBuilder._to_resource_requirements(
                resources, defaults, self.target
            ),
            liveness_probe=liveness_probe,
            startup_probe=startup_probe,
            command=(
                deployment.kubernetes.command.get_value(self.target).split(" ")
                if deployment.kubernetes.command
                else None
            ),
            args=(
                deployment.kubernetes.args.get_value(self.target).split(" ")
                if deployment.kubernetes.args
                else None
            ),
        )

        instances = resources.instances if resources.instances else defaults.instances
        merged_config = {
            **self.config_defaults.deployment_strategy,
            **(deployment.kubernetes.deployment_strategy or {}),
        }
        strategy = ChartBuilder._to_k8s_model(merged_config, V1DeploymentStrategy)
        return V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=V1ObjectMeta(
                annotations=self._to_annotations(),
                name=deployment.name.lower(),
                labels=self.to_labels(),
            ),
            spec=V1DeploymentSpec(
                replicas=instances.get_value(target=self.target),
                template=V1PodTemplateSpec(
                    metadata=self._to_object_meta(deployment_name=deployment.name),
                    spec=V1PodSpec(
                        containers=[container],
                        service_account=self.release_name,
                        service_account_name=self.release_name,
                    ),
                ),
                strategy=strategy,
                selector=self._to_selector(deployment),
            ),
        )

    def to_common_chart(
        self, deployment: Deployment
    ) -> dict[str, CustomResourceDefinition]:
        chart = {"service-account": self.to_service_account()}

        if deployment.properties and len(deployment.properties.sealed_secrets) > 0:
            chart[f"sealed-secrets-{deployment.name}"] = self.to_sealed_secrets(
                deployment.properties.sealed_secrets, deployment.name
            )

        # role is only used for Keycloak which only has 1 deployment, can be removed soon
        role = deployment.kubernetes.role or {}
        if role:
            chart["role"] = self.to_role(role)
            chart["rolebinding"] = self.to_role_binding()

        prometheus = _to_prometheus_chart(self, deployment)

        return chart | prometheus


def to_metrics(builder: ChartBuilder, deployment: Deployment):
    default_port = builder.find_default_port(deployment.kubernetes.port_mappings)
    metrics = deployment.kubernetes.metrics
    service_monitor = (
        {
            "service-monitor": builder.to_service_monitor(metrics, default_port),
        }
        if metrics and metrics.enabled
        else {}
    )
    return service_monitor


def to_service_chart(
    builder: ChartBuilder, deployment: Deployment
) -> dict[str, CustomResourceDefinition]:
    return (
        {f"service-{deployment.name}": builder.to_service(deployment)}
        | {f"deployment-{deployment.name}": builder.to_deployment(deployment)}
        | _to_ingress_routes_charts(builder, deployment)
        | builder.to_middlewares(deployment)
        | to_metrics(builder, deployment)
    )


def _to_ingress_routes_charts(builder: ChartBuilder, deployment: Deployment):
    ingress_https = {
        f"{builder.project.name}-ingress-{i}-https": route
        for i, route in enumerate(builder.to_ingress_routes(deployment, https=True))
    }
    ingress_http = {
        f"{builder.project.name}-ingress-{i}-http": route
        for i, route in enumerate(builder.to_ingress_routes(deployment, https=False))
    }
    ingress_routes = (
        {f"ingress-routes-{deployment.name}": builder.to_ingress(deployment)}
        if builder.to_ingress(deployment)
        else {}
    )
    additional_routes = {
        route.metadata.name: route
        for i, route in enumerate(builder.to_additional_routes(deployment))
    }

    return ingress_https | ingress_http | ingress_routes | additional_routes


def _to_prometheus_chart(builder: ChartBuilder, deployment: Deployment):
    metrics = deployment.kubernetes.metrics
    prometheus_chart = (
        {
            f"prometheus-rule-{deployment.name}": builder.to_prometheus_rule(
                alerts=metrics.alerts,
                deployment_name=deployment.name,
            ),
        }
        if metrics and metrics.enabled
        else {}
    )
    return prometheus_chart


def to_job_chart(builder: ChartBuilder, deployment: Deployment) -> dict[str, V1Job]:
    return {f"job-{deployment.name}": builder.to_job(deployment)}


def to_cron_job_chart(
    builder: ChartBuilder, deployment: Deployment
) -> dict[str, V1CronJob]:
    return {f"cronjob-{deployment.name}": builder.to_cron_job(deployment)}
