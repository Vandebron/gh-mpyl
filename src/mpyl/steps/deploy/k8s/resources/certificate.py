"""
This module contains the Certificate CRD.
"""

from kubernetes.client import V1ObjectMeta

from .....constants import PR_NUMBER_PLACEHOLDER
from .....steps.deploy.k8s import CustomResourceDefinition
from .....utilities import replace_item


class V1Certificate(CustomResourceDefinition):
    def __init__(self, pr_number: str):
        super().__init__(
            api_version="cert-manager.io/v1",
            kind="Certificate",
            metadata=V1ObjectMeta(name="pr-cert"),
            schema="certificates.cert-manager.io.schema.yml",
            spec=replace_item(
                {
                    "secretName": "pr-cert",
                    "privateKey": {
                        "algorithm": "RSA",
                        "encoding": "PKCS1",
                        "size": 2048,
                    },
                    "duration": "2160h0m0s",  # 90d
                    "renewBefore": "360h0m0s",  # 15d
                    "usages": ["server auth", "client auth"],
                    "subject": {
                        "organizations": ["Vandebron Energie B.V."],
                    },
                    "dnsNames": [
                        "*.test-{PR-NUMBER}.test.vdbinfra.nl",
                        "*.test.vdbinfra.nl",
                    ],
                    "issuerRef": {
                        "name": "pr-issuer",
                        "kind": "ClusterIssuer",
                    },
                },
                PR_NUMBER_PLACEHOLDER,
                pr_number,
            ),
        )
