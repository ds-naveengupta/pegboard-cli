"""This module provides the Pegboard CLI."""
# pegboard/cli.py
from rich.console import Console
from rich.panel import Panel
import typer
from pegboard import __app_name__, __version__, database
from pegboard.commands import game, player
from pegboard.pegboard import Pegboard

app = typer.Typer(
    no_args_is_help=True,
    help="Pegboard Management CLI",
)

console = Console()
pegboard = Pegboard()

# Register commands
app.command(name="add", help="Add a player with name and gender.")(
    player.add_player
)

app.command(name="load", help="Load players from CSV file.")(
    player.load_csv
)

app.command(name="players", help="List players.")(
    player.list_players
)

app.command(name="find", help="List players by name (partial match).")(
    player.find
)

app.command(name="checkin", help="Checkin players using partial or full name search.")(
    player.checkin
)

app.command(name="checkout", help="Checkout players using partial or full name search.")(
    player.checkout
)

app.command(name="next", help="Identify the next players due for a game.")(
    player.next
)

app.command(name="assign", help="Assigns 4 players to a specific game and court.")(
    game.assign_players
)

app.command(name="report", help="Prints a report of all games grouped by Game Number.")(
    game.report
)

app.command(name="propose", help="Propose court assignments for 4, 8, or 12 players.")(
    game.propose
)

app.command(name="swap", help="Swap one player with another.")(
    game.swap_player
)

@app.command()
def reset():
    """
    Clears all games and resets all player check-ins.
    """
    typer.secho("🧨 TOTAL RESET INITIATED", fg="red", bold=True)
    
    confirm = typer.confirm("This will clear ALL games and reset ALL player check-ins. Proceed?")
    
    if confirm:
        with console.status("[bold red]Scrubbing database..."):
            pegboard.reset_games_and_players()
        
        typer.secho("✅ Database is fresh. All players are now signed out.", fg="green", bold=True)
    else:
        typer.echo("Reset aborted.")

@app.command()
def path():
    """
    Displays the absolute path to the SQLite database file.
    """
    db_file = database.get_db_path()
    
    console.print(Panel(
        f"[bold cyan]Database Path:[/bold cyan]\n{db_file}",
        title="📂 File Information",
        expand=False
    ))

# ----------------------------
# Global version option
# ----------------------------
def version_callback(value: bool):
    if value:
        typer.echo(f"{__app_name__} v{__version__}")
        raise typer.Exit()

@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", callback=version_callback, is_eager=True,
        help="Show the application version"
    ),
):
    """Pegboard CLI main callback"""
    # Ensure database + tables exist
    database.create_schema()