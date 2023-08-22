"""
This module contains the PrometheusRule CRD
"""
from typing import Optional

from kubernetes.client import V1ObjectMeta

from .....project import Alert
from .. import CustomResourceDefinition


class V1PrometheusRule(CustomResourceDefinition):
    def __init__(self, metadata: V1ObjectMeta, alerts: list[Alert]):
        super().__init__(
            api_version="monitoring.coreos.com/v1",
            kind="PrometheusRule",
            metadata=metadata,
            schema="monitoring.coreos.com_prometheuses.schema.yml",
            spec={
                "groups": [
                    {
                        "name": f"{metadata.name}-group",
                        "rules": _alerts_to_rules(alerts),
                    }
                ]
            },
        )


def _alerts_to_rules(alerts: list[Alert]) -> list[dict]:
    return [
        {
            "alert": alert.name,
            "annotations": {
                # To prevent {{ .. }} being replaced as Helm template -> https://stackoverflow.com/a/64694592/8376486
                "description": alert.description.replace("{{", '{{ "{{" }}'),
            },
            "expr": alert.expr,
            "for": alert.for_duration,
            "labels": {
                "alertname": alert.name,
                "severity": alert.severity,
            },
        }
        for alert in alerts
    ]


class V1ServiceMonitor(CustomResourceDefinition):
    def __init__(
        self, metadata: V1ObjectMeta, endpoint: dict, namespace: Optional[str]
    ):
        super().__init__(
            api_version="monitoring.coreos.com/v1",
            kind="ServiceMonitor",
            metadata=metadata,
            schema="monitoring.coreos.com_servicemonitors.schema.yml",
            spec={
                "endpoints": [endpoint],
                "namespaceSelector": {"matchNames": [namespace]},
                "selector": {"matchLabels": {"app.kubernetes.io/name": metadata.name}},
            },
        )
