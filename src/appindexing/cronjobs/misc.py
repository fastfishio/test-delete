import logging

import click

from libindexing.domain.stock import full_stock_update_for_warehouse

logger = logging.getLogger(__name__)


@click.group()
def cli():
    pass


@cli.command()
@click.argument("wh_code")
def full_reindex(wh_code):
    logger.info(f"starting full reindex for warehouse code: {wh_code}")
    full_stock_update_for_warehouse(wh_code)


if __name__ == "__main__":
    logger.info(f"in misc.py main")
    cli()
