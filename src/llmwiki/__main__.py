"""CLI entry point."""

import typer

app = typer.Typer(
    name="llmwiki",
    help="Portable Ollama-powered LLM Wiki with a Rich CLI",
    no_args_is_help=True,
    add_completion=False,
)


def version_callback(value: bool):
    if value:
        from llmwiki import __version__
        typer.echo(f"llmwiki version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=version_callback,
        help="Show version and exit.",
    ),
):
    """Main CLI callback."""
    pass


# Import subcommands to register them
from llmwiki.cli import init, doctor, stats, profile, category, model, ingest, query, page, maintain, daemon  # noqa: F401
