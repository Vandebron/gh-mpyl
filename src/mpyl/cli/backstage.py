"""Commands related to Backstage"""

import click

from ..backstage.backstage import generate_components


@click.group("backstage")
def backstage():
    """Empty group"""


@backstage.command(help="Generate backstage component files")
@click.option(
    "--repository",
    "-r",
    required=True,
    type=str,
    help="Repository path",
)
def generate(repository: str):
    generate_components(repository)
