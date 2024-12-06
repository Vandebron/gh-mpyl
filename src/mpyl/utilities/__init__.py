"""Common utility functions"""

from typing import Optional

from ..constants import PR_NUMBER_PLACEHOLDER


def replace_pr_number(original_value: Optional[str], pr_number: Optional[int]):
    return (
        original_value.replace(PR_NUMBER_PLACEHOLDER, str(pr_number))
        if original_value and pr_number
        else original_value
    )


def replace_item(data, a, b):
    if isinstance(data, str):
        return data.replace(a, b)
    if isinstance(data, dict):
        return {k: replace_item(v, a, b) for k, v in data.items()}
    if isinstance(data, list):
        return [replace_item(v, a, b) for v in data]
    return data
