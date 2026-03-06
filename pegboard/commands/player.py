# pegboard/commands/player.py
from typing import List

from rich.console import Console
import typer
from pegboard.exceptions import PegboardError
from pegboard.commands.game import propose
from pegboard.pegboard import Gender, Pegboard, PersonType
from pegboard.utils.tables import render_next_players_table, render_players_table
from pathlib import Path

pegboard = Pegboard()
console = Console()

def add_player(
    name: str = typer.Argument(..., help="Full name"),
    gender: Gender = typer.Argument(..., case_sensitive=False, help="Male or Female"),
    type: PersonType = typer.Option(
        PersonType.MEMBER,
        "--type",
        help="Member or Guest",
    ),
):
    """
    Add a player with name and gender.
    """
    try:
        player_id = pegboard.add_player(name, gender, type)
        typer.secho(
            f"✅ Added [{type.value}] {name} ({gender.value}) with ID {player_id}",
            fg="green",
        )

    except PegboardError as e:
        typer.secho(f"❌ {e}", fg="red")
        raise typer.Exit()
    
def load_csv(
    file: Path = typer.Argument(
        ...,
        exists=False,  # we'll handle existence manually
        help="Path to CSV file containing players",
    )
):
    """
    Load players from CSV file.
    """
    if not file.exists():
        typer.echo("❌ File not found.")
        raise typer.Exit(code=1)
    
    try:
        inserted, skipped = pegboard.add_players_from_csv(file)

        typer.secho(f"✅ Inserted: {inserted}", fg="green")
        typer.secho(f"⚠️  Skipped (duplicates/invalid): {skipped}", fg="yellow")

    except PegboardError as e:
        typer.secho(f"❌ {e}", fg="red")
        raise typer.Exit(code=1)
    
def list_players(
    show_all: bool = typer.Option(
        False, "--show-all", 
        help="Show all registered players"
    )
):
    """
    List players with full detail:
    - Name, Gender, Type, Check-in, Status, and Game columns
    - Default shows only attended players
    - --show-all shows all registered players
    """
    # Call the unified list_players method
    game_nrs, players = pegboard.list_players(show_all)

    # Render the table
    title = "All Players" if show_all else "Attended Players"
    render_players_table(players, title=title, game_nrs=game_nrs)

def find(
    search: str = typer.Argument(
        ..., 
        help="Filter players by partial name match"
    )
):
    """
    List players by name (partial match):
    - Name, Gender, Type, Check-in, Status, and Game columns
    """
    # 1️⃣ Get all relevant players
    game_nrs, players = pegboard.list_players(show_all=True)

    # 2️⃣ Apply partial name filter if provided
    if search:
        search_lower = search.lower()
        players = [p for p in players if search_lower in p["name"].lower()]

    # 3️⃣ Determine table title
    title = "All Players"
    if search:
        title += f" (filtered by '{search}')"

    # 4️⃣ Render the table
    render_players_table(players, title=title, game_nrs=game_nrs)

def checkin(
    names: List[str],
    confirm: bool = typer.Option(
        True,
        help="Ask before checking in each player"
    )
):
    """
    Check in players by name (partial match supported).
    """
    # 1️⃣ Get players to check in
    results = pegboard.checkin_players(names)
    player_ids_to_checkin = []

    for r in results:
        if r["id"] is None:
            typer.secho(f"❓ {r['message']}", fg="yellow")
            continue

        if r["status_after"] == "P":
            typer.secho(f"ℹ️  {r['name']} is already checked in.", fg="cyan")
            continue

        # Ask confirmation if requested
        if confirm:
            ok = typer.confirm(f"Check in {r['name']}?")
            if not ok:
                typer.secho(f"⏭️  Skipped {r['name']}", fg="yellow")
                continue

        player_ids_to_checkin.append(r["id"])

    # 2️⃣ Perform actual DB update
    updated_ids = pegboard.perform_checkin(player_ids_to_checkin)

    # 3️⃣ Display results
    for r in results:
        if r["id"] in updated_ids:
            typer.secho(f"✅ Checked in: {r['name']}", fg="green")
    if updated_ids:
        typer.secho(f"\nTotal players checked in: {len(updated_ids)}\n", bold=True)

def checkout(
    names: List[str], 
    confirm: bool = typer.Option(
        True, 
        help="Ask before checking out each player"
    )
):
    """
    Checkout players by partial name match.
    """
    results = pegboard.checkout_players(names)
    player_ids_to_checkout = []

    for r in results:
        if r["id"] is None:
            typer.secho(f"❓ {r['message']}", fg="yellow")
            continue

        if r["status_after"] == "E" or r["status_before"] == "E":
            typer.secho(f"ℹ️  {r['name']} has already checked out.", fg="blue")
            continue

        if r["status_before"] != "P":
            typer.secho(f"🚫 Cannot checkout {r['name']}: {r['message']}", fg="red")
            continue

        if confirm:
            ok = typer.confirm(f"Check out {r['name']}?")
            if not ok:
                typer.secho(f"⏭️  Skipped {r['name']}", fg="yellow")
                continue

        player_ids_to_checkout.append(r["id"])

    updated_ids = pegboard.perform_checkout(player_ids_to_checkout)

    for r in results:
        if r["id"] in updated_ids:
            typer.secho(f"✅ Checked out: {r['name']}", fg="green")

    if updated_ids:
        typer.secho(f"\nTotal players checked out: {len(updated_ids)}\n", bold=True)

def next(
    count: int = typer.Argument(
        12,
        help="Number of players needed (4, 8, or 12)"
    )
):
    """
    Identify the next players due for a game.
    """
    if count not in [4, 8, 12]:
        typer.secho("❌ Please request exactly 4, 8, or 12 players.", fg="red")
        raise typer.Exit()

    # Fetch players using the new 'Priority Rotaion' SQL
    players = pegboard.get_rotation_prioritised()

    if not players:
        typer.secho(
            "No active players found. Run 'players' to check status.",
            fg="yellow"
        )
        return

    # Identify "Must-Play" (Select first count from the players list)
    must_play = players[:count]
    overflow = players[count:]

    if len(must_play) < count:
        typer.secho(
            f"⚠️  Only {len(must_play)} active players available.",
            fg="yellow"
        )
    
    # Double sitters = Sat last game AND sitting again now
    double_sitters = [
        p['name']
        for p in overflow
        if p['played_last_game'] == 0
    ]

    # Render Table
    render_next_players_table(players, must_play, double_sitters)

    # Propose Action
    if len(must_play) == count:

        if typer.confirm("\nProceed to generate court proposal for these players?", default=True):
            propose([p["name"] for p in must_play])
            raise typer.Exit()
        else:
            typer.echo("ℹ️  Operation cancelled by the User.")
            raise typer.Exit()
