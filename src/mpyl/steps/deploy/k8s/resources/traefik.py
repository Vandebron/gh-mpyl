"""
This module contains the traefik ingress route CRD.
"""

from dataclasses import dataclass
from typing import Optional, Union, Any

from kubernetes.client import V1ObjectMeta

from . import CustomResourceDefinition
from .....constants import (
    SERVICE_NAME_PLACEHOLDER,
    NAMESPACE_PLACEHOLDER,
)
from .....project import TraefikHost, Target, TraefikAdditionalRoute
from .....utilities import replace_pr_number


@dataclass(frozen=True)
class HostWrapper:
    traefik_host: TraefikHost
    name: str
    index: int
    service_port: int
    white_lists: dict[str, list[str]]
    tls: Optional[str]
    additional_route: Optional[TraefikAdditionalRoute]
    insecure: bool = False


class V1AlphaIngressRoute(CustomResourceDefinition):
    @classmethod
    def from_hosts(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        cls,
        metadata: V1ObjectMeta,
        host: HostWrapper,
        target: Target,
        release_name: str,
        namespace: str,
        pr_number: Optional[int],
        middlewares_override: list[str],
        entrypoints_override: list[str],
        default_tls: str,
    ):
        def _interpolate_names(host: str) -> str:
            host = host.replace(SERVICE_NAME_PLACEHOLDER, release_name)
            host = host.replace(NAMESPACE_PLACEHOLDER, namespace)
            host = replace_pr_number(host, pr_number)
            return host

        combined_middlewares = (
            [{"name": f"whitelist-{host.index}-{host.name}"}]
            if len(middlewares_override) == 0
            else [{"name": m for m in middlewares_override}]
        )

        route: dict[str, Any] = {
            "kind": "Rule",
            "match": _interpolate_names(host=host.traefik_host.host.get_value(target)),
            "services": [
                {"name": host.name, "kind": "Service", "port": host.service_port}
            ],
            "middlewares": combined_middlewares,
            "syntax": (
                host.traefik_host.syntax.get_value(target)
                if host.traefik_host.syntax
                else None
            ),
        }

        if host.traefik_host.priority:
            route |= {"priority": host.traefik_host.priority.get_value(target)}

        tls: dict[str, Union[str, dict]] = {
            "secretName": host.tls if host.tls else default_tls
        }

        if host.insecure:
            tls |= {"options": {"name": "insecure-ciphers", "namespace": "traefik"}}

        combined_entrypoints = (
            ["websecure"] if len(entrypoints_override) == 0 else entrypoints_override
        )

        return cls(
            api_version="traefik.io/v1alpha1",
            kind="IngressRoute",
            metadata=metadata,
            spec={"routes": [route], "entryPoints": combined_entrypoints, "tls": tls},
            schema="traefik.ingress.schema.yml",
        )

    @classmethod
    def from_spec(cls, metadata: V1ObjectMeta, spec: dict):
        return cls(
            api_version="traefik.io/v1alpha1",
            kind="IngressRoute",
            metadata=metadata,
            spec=spec,
            schema="traefik.ingress.schema.yml",
        )


class V1AlphaMiddleware(CustomResourceDefinition):
    @classmethod
    def from_source_ranges(cls, metadata: V1ObjectMeta, source_ranges: list[str]):
        return cls(
            api_version="traefik.io/v1alpha1",
            kind="Middleware",
            metadata=metadata,
            spec={"ipAllowList": {"sourceRange": source_ranges}},
            schema="traefik.middleware.schema.yml",
        )

    @classmethod
    def from_spec(cls, metadata: V1ObjectMeta, spec: dict):
        return cls(
            api_version="traefik.io/v1alpha1",
            kind="Middleware",
            metadata=metadata,
            spec=spec,
            schema="traefik.middleware.schema.yml",
        )
