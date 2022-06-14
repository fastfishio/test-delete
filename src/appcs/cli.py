import logging

import click

logger = logging.getLogger(__name__)


@click.group()
def cli():
    pass


@cli.group()
def db():
    pass


@db.command()
def create():
    pass


if __name__ == "__main__":
    cli()
