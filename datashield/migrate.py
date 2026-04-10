from __future__ import annotations

import click

from .controlplane import init_db


@click.command()
def main():
    """Initialize or upgrade control-plane schema."""
    init_db()
    click.echo("schema_ok")


if __name__ == "__main__":
    main()
