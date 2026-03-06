# pegboard/commands/game.py
import random
import typer
from pegboard.pegboard import Pegboard
from pegboard.exceptions import PegboardError
from pegboard.utils.tables import render_games_table, render_proposal_table

app = typer.Typer()
pegboard = Pegboard()

def confirm_callback(msg: str) -> bool:
        typer.secho(f"⚠️  {msg}", fg="yellow")
        return typer.confirm("Do you want to proceed?")

def assign_players(
    game: int = typer.Argument(..., help="Game number"), 
    court: int = typer.Argument(..., help="Court number"), 
    p1: str = typer.Argument(..., help="Player 1 Side A"),
    p2: str = typer.Argument(..., help="Player 2 Side A"),
    p3: str = typer.Argument(..., help="Player 1 Side B"),
    p4: str = typer.Argument(..., help="Player 2 Side B"),
    duration: int = typer.Option(15, "--duration", help="Game duration in minutes",
    ),
):
    """
    Assigns 4 players to a specific game and court.
    """
    # If user didn't explicitly pass --duration, confirm default
    duration = typer.prompt(
        "Game duration (minutes)",
        default=duration,
        type=int
    )
        
    try:
        # Convert player names to IDs (could raise PlayerNotActiveError)
        ids = [
            pegboard.get_active_player_id(p1, confirm_callback),
            pegboard.get_active_player_id(p2, confirm_callback),
            pegboard.get_active_player_id(p3, confirm_callback),
            pegboard.get_active_player_id(p4, confirm_callback)
        ]

        if len(set(ids)) < 4:
            typer.secho("❌ Error: You have assigned the same player to multiple spots!", fg="red")
            raise typer.Exit()

        pegboard.assign_game(game, court, duration, (ids[0], ids[1]), (ids[2], ids[3]), confirm_callback)
        typer.secho(f"✅ Game {game} on Court {court} successfully assigned!", fg="green")

    except PegboardError as e:
        typer.secho(f"❌ {e}", fg="red")

def report():
    """
    Prints a report of all games grouped by Game Number.
    """
    games = pegboard.get_game_report()
    render_games_table(games)

def propose(names: list[str]):
    """
    Propose court assignments for 4, 8, or 12 players.
    Validates against historical pairs and opponent frequency.
    """
    if len(names) not in [4, 8, 12]:
        typer.secho(
            "❌ Error: You must provide exactly 4, 8, or 12 player names.",
            fg="red"
        )
        raise typer.Exit()

    # ✅ Resolve IDs safely
    player_ids = []
    for name in names:
        try:
            player_id = pegboard.get_active_player_id(name, confirm_callback)
            player_ids.append(player_id)
        except PegboardError as e:
            typer.secho(f"❌ {e}", fg="red")
            raise typer.Exit()
        
    # Ensure all IDs are unique
    if len(set(player_ids)) != len(player_ids):
        typer.secho(
            "❌ Error: You assigned the same player to multiple spots!",
            fg="red"
        )
        raise typer.Exit()

    assignments = None

    while True:
        # Shuffle + generate proposal
        if assignments is None:
            random.shuffle(player_ids)
            result = pegboard.generate_valid_assignments(player_ids)

            if result is None:
                continue

            assignments, warnings = result
            for w in warnings:
                typer.secho(f"⚠️  {w}", fg="yellow")

        named_assignments = []
        for side_a, side_b in assignments:
            named_assignments.append((
                (
                    pegboard.get_player_name_by_id(side_a[0]),
                    pegboard.get_player_name_by_id(side_a[1])
                ),
                (
                    pegboard.get_player_name_by_id(side_b[0]),
                    pegboard.get_player_name_by_id(side_b[1])
                )
            ))
        # Render proposal
        render_proposal_table(assignments=named_assignments)

        # User interaction
        action = typer.prompt(
            "Choices:\n" \
            "  -> [y]es (save)\n" \
            "  -> [n]o (reshuffle)\n" \
            "  -> [q]uit",
            default="y"
        ).lower()

        if action == "y":
            next_gn = pegboard.get_next_game_number()
            game_nr = typer.prompt("Game Number", default=next_gn, type=int)
            duration = typer.prompt("Duration (mins)", default=15, type=int)

            for court_nr, (side_a, side_b) in enumerate(assignments, 1):
                
                try:
                    pegboard.assign_game(game_nr, court_nr, duration, side_a, side_b, confirm_callback)
                    typer.secho(f"✅ Game {game_nr} on Court {court_nr} successfully assigned!", fg="green")

                except PegboardError as e:
                    typer.secho(f"❌ {e}", fg="red")

            report()
            break

        elif action == "n":
            assignments = None
            typer.echo("🎲 Re-shuffling...")

        elif action == "q":
            raise typer.Exit()
        
def swap_player(
    game_nr: int = typer.Argument(..., help="Game number"),
    player_out: str = typer.Argument(..., help="Player to remove"),
    player_in: str = typer.Argument(..., help="Player to insert"),
):
    """
    Swap one player with another.
    Handles:
    - Court ↔ Court swap
    - Court ↔ Sitting swap
    """

    try:
        message = pegboard.swap_player(game_nr, player_out, player_in, confirm_callback)
        typer.secho(f"✅ {message}", fg="green")

    except PegboardError as e:
        typer.secho(f"❌ {e}", fg="red")
        raise typer.Exit()