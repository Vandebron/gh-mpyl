"""Commands related to Backstage"""

import click

from ..backstage.backstage import generate_components


@click.group("backstage")
def backstage():
    """Empty group"""


@backstage.command(help="Generate backstage component files")
@click.option(
    "--output",
    "-o",
    required=True,
    type=str,
    help="The output path",
)
@click.option(
    "--url",
    "-u",
    required=True,
    type=str,
    help="The repository url",
)
@click.option(
    "--repository",
    "-r",
    required=True,
    type=str,
    help="The repository name",
)
def generate(output: str, url: str, repository: str):
    generate_components(output, url, repository)
