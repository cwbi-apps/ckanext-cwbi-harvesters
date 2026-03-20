import click


@click.group(short_help="cwbi_harvesters CLI.")
def cwbi_harvesters():
    """cwbi_harvesters CLI.
    """
    pass


@cwbi_harvesters.command()
@click.argument("name", default="cwbi_harvesters")
def command(name):
    """Docs.
    """
    click.echo("Hello, {name}!".format(name=name))


def get_commands():
    return [cwbi_harvesters]
