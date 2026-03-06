# pegboard/utils/tables.py
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import typer
from pegboard.pegboard import Gender

console = Console()

def render_players_table(players: list[dict], title: str, game_nrs: list[int] = None) -> None:
    """
    Render a full players table with sequence, name, gender, type, timestamp, status, and game columns.
    - Empty timestamp is displayed as orange '-'
    - Game participation shows 'P' in green or '-' if absent
    - Dim row style for players who left early (status == 'E')
    """
    total = len(players)
    
    if total == 0:
        clean_title = title.lower().replace("all ", "")
        typer.secho(f"No {clean_title} found.", fg="yellow", italic=True)
        raise typer.Exit()

    active_count = len([p for p in players if p.get("status") == "P"])
    stats_info = f"Total: {total} | Active: [bold green]{active_count}[/bold green]"

    table = Table(
        title=f"\n[bold]{title}[/bold] ({stats_info})",
        title_justify="left"
    )

    # Always use sequence number as first column
    table.add_column("#", justify="right")
    table.add_column("Name", justify="left")
    table.add_column("Gender", justify="left")
    table.add_column("Type", justify="left")
    table.add_column("Check-in", justify="center", style="dim")
    
    if game_nrs:
        for gn in game_nrs:
            table.add_column(f"G{gn}", justify="center", style="red")
    else:
        # Placeholder column if no games yet
        table.add_column("Games", justify="center", style="dim")

    for index, p in enumerate(players, start=1):
        row_data = [
            str(index),
            p.get("name", "-"),
            p.get("gender", "-"),
            p.get("type", "-"),
        ]

        timestamp = p.get("timestamp")
        if not timestamp:
            timestamp_display = "[orange1]-[/orange1]"
        else:
            timestamp_display = timestamp
        row_data.append(timestamp_display)

        # Game columns
        if game_nrs:
            for gn in game_nrs:
                val = p.get("game_history", {}).get(gn, "-")
                row_data.append("[green]P[/green]" if val == "P" else "-")
        else:
            row_data.append("-")

        # Row style: dim if left early
        row_style = "dim" if p.get("status") == "E" else "none"

        table.add_row(*row_data, style=row_style)

    console.print(table)

def render_games_table(games: list[dict]) -> None:
    if not games:
        console.print("[yellow italic]No games scheduled.[/yellow italic]")
        return

    report_dict = {}
    durations = {}

    for row in games:
        gn, cn, dur = row["game_nr"], row["court_nr"], row["duration"]
        side, p1, p2 = row["court_side"], row["p1_name"], row["p2_name"]

        report_dict.setdefault(gn, {}).setdefault(cn, {})[side] = f"{p1}\n{p2}"

        if gn not in durations:
            durations[gn] = dur

    max_court = max(row["court_nr"] for row in games)

    table = Table()
    table.add_column("Game (Time)", justify="center")

    for c in range(1, max_court + 1):
        table.add_column(f"Court {c}", justify="center", width=20)

    sorted_game_nrs = sorted(report_dict.keys())

    for i, g_nr in enumerate(sorted_game_nrs):
        courts = report_dict[g_nr]
        dur_label = f"[bold]{g_nr}[/bold]\n[dim]({durations[g_nr]}m)[/dim]"

        side_a_row = [
            f'[cyan]{courts.get(c, {}).get("Side A", "---")}[/cyan]'
            for c in range(1, max_court + 1)
        ]

        side_b_row = [
            courts.get(c, {}).get("Side B", "---")
            for c in range(1, max_court + 1)
        ]

        table.add_row(dur_label, *side_a_row)

        table.add_row(
            "",
            *["[dim]-vs-[/dim]" for _ in range(max_court)]
        )

        table.add_row("", *side_b_row)

        if i < len(sorted_game_nrs) - 1:
            table.add_section()

    console.print(table)

def render_proposal_table(assignments: list[tuple[tuple[int, int], tuple[int, int]]]):
    table = Table(title="\nProposed Court Assignments")

    # Dynamic column creation
    for i in range(1, len(assignments) + 1):
        table.add_column(f"Court {i}", justify="center", width=25)

    side_a_names = []
    side_b_names = []

    for (side_a, side_b) in assignments:
        p1, p2 = side_a
        p3, p4 = side_b

        side_a_names.append(
            f"[cyan]{p1}[/cyan]\n[cyan]{p2}[/cyan]"
        )

        side_b_names.append(
            f"{p3}\n{p4}"
        )

    table.add_row(*side_a_names)
    table.add_row(*["[dim]-vs-[/dim]" for _ in assignments])
    table.add_row(*side_b_names)

    console.print(table)
    typer.echo("\n")

def render_next_players_table(
    players: list[dict],
    must_play: list[dict],
    double_sitters: list[str],
):
    table = Table(
        title=f"\n[bold green]Next Up[/bold green] (Top {len(must_play)} of {len(players)} active)"
    )
    
    table.add_column("Rank", justify="right")
    table.add_column("Name", style="bold")
    table.add_column("Gender")
    table.add_column("Arrived At", style="dim")
    table.add_column("Streak", justify="center")

    for i, p in enumerate(must_play, start=1):
        gender = Gender.from_db(p["gender"]).value if p["gender"] else "---"
        priority = p['priority']

        label = f"{priority:+d}"

        color_map = {
            -2: "red",
            -1: "yellow",
            1: "white",
            2: "dim",
        }
        color = color_map[priority]
            
        table.add_row(
            str(i),
            p["name"],
            gender,
            p["timestamp"],
            # f"{label}",
            f"[{color}]{label}[/{color}]",
        )

    console.print(table)

    # Show Warning for Double-Sitters
    if double_sitters:
        msg = f"⚠️  [yellow]Double-Sit Warning:[/yellow] These people will sit for a 2nd game in a row because the courts are full: "
        names = ", ".join([f"[red]{name}[/red]" for name in double_sitters])
        console.print(Panel(msg + names, border_style="yellow"))
    else:
        console.print("\n[green]✅ Everyone who sat last game is included in this round.[/green]")