# pegboard/pegboard.py

import csv
from enum import Enum
from itertools import permutations
from pathlib import Path
import sqlite3
from typing import Callable, Dict, List, Optional, Tuple

from pegboard.database import get_connection
from pegboard.exceptions import (
    AmbiguousPlayerError, 
    CourtAlreadyAssignedError, 
    DuplicateAssignmentError, 
    InvalidCSVFormatError, 
    PairingConflictError, 
    PegboardError, 
    PlayerNotActiveError, 
    PlayerNotFoundError,
    GameNotFoundError
)


class Gender(str, Enum):
    MALE = "Male"
    FEMALE = "Female"

    @property
    def db_value(self) -> str:
       return self.value[0].upper()
    
    @classmethod
    def from_db(cls, char: str):
        # Maps "M" -> MALE, "F" -> FEMALE
        mapping = {"M": cls.MALE, "F": cls.FEMALE}
        return mapping.get(char.upper())
    
class PersonType(str, Enum):
    GUEST = "Guest"
    MEMBER = "Member"

    @property
    def db_value(self) -> str:
        return self.value[0].upper()
    
    @classmethod
    def from_db(cls, char: str):
        # Maps "M" -> MEMBER, "G" -> GUEST
        mapping = {"M": cls.MEMBER, "G": cls.GUEST}
        return mapping.get(char.upper())

class PlayerStatus(str, Enum):
    ABSENT = "A"
    PRESENT = "P"
    EARLY_LEAVE = "E"

    @property
    def display(self) -> str:
        # Mapping database values to CLI emojis
        mapping = {
            PlayerStatus.ABSENT: "",
            PlayerStatus.PRESENT: "✅",
            PlayerStatus.EARLY_LEAVE: "--"
        }
        return mapping.get(self, "-")

class Pegboard:

    def add_player(self, name: str, gender: Gender, type: PersonType) -> int:
        """ Add new player."""
        insert_sql = """
        INSERT OR IGNORE INTO players (name, gender, type) VALUES(?, ?, ?)
        """

        with get_connection() as conn:
            cursor = conn.execute(
                insert_sql, (name, gender.db_value, type.db_value),
            )

            if cursor.rowcount == 0:
                raise PegboardError(f"{type.value} already exists.")

        return cursor.lastrowid
    
    def add_players_from_csv(self, file_path: Path) -> tuple[int, int]:
        """
        Loads players from CSV file.
        Returns (inserted_count, skipped_count).
        Raises InvalidCSVFormatError if structure is wrong.
        """

        inserted = 0
        skipped = 0

        with file_path.open(newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)

            required_columns = {"name", "gender", "type"}
            if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
                raise InvalidCSVFormatError(
                    "CSV must contain columns: name, gender, type"
                )
        
            with get_connection() as conn:
                for row in reader:
                    try:
                        name = row["name"].strip()
                        gender_raw = row["gender"].strip()
                        type_raw = row["type"].strip()

                        # Convert to enums (safe & consistent)
                        gender = Gender(gender_raw)
                        person_type = PersonType(type_raw)

                    except (ValueError, KeyError):
                        skipped += 1
                        continue

                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO players (name, gender, type)
                        VALUES (?, ?, ?)
                        """,
                        (name, gender.db_value, person_type.db_value),
                    )

                    if cursor.rowcount == 0:
                        skipped += 1
                    else:
                        inserted += 1

                conn.commit()

        return inserted, skipped
    
    def format_players(self, rows) -> List[dict]:
        """Helper to convert DB rows into the UI-ready dictionary format."""
        players = []
        for row in rows:
            gender_enum = Gender.from_db(row["gender"])
            type_enum = PersonType.from_db(row["type"])
            status_enum = PlayerStatus(row["status"])
            
            players.append({
                "id": row["id"],
                "name": row["name"],
                "gender": gender_enum.value,
                "type": type_enum.value,
                "timestamp": row["timestamp"],
                "status": status_enum
            })
        return players
    
    def list_players(self, show_all: bool = False):
        """
        Return players and game info in a unified format.

        Args:
            show_all (bool): 
                - True: return all players with game participation if any.
                - False: return only attended players (status 'P' or 'E').

        Returns:
            tuple: (game_nrs: list[int], players: list[dict])
        """
        with get_connection() as conn:
            # 1️⃣ Get all game numbers
            game_nrs = [r["game_nr"] for r in conn.execute("SELECT DISTINCT game_nr FROM games ORDER BY game_nr").fetchall()]

            if show_all:
                # 2️⃣ Get all players
                rows = conn.execute("""
                    SELECT id, name, gender, type, timestamp, status
                    FROM players
                    ORDER BY name
                """).fetchall()
                players = self.format_players(rows)
            else:
                # 2️⃣ Get only attended players
                rows = conn.execute("""
                    SELECT id, name, gender, type, timestamp, status
                    FROM players
                    WHERE status IN ('P', 'E')
                    ORDER BY timestamp ASC
                """).fetchall()
                players = self.format_players(rows)

            results = []
            for p in players:
                # 3️⃣ Build actual game history per player
                played = conn.execute("""
                    SELECT g.game_nr 
                    FROM games g
                    JOIN participations pt ON g.id = pt.game_id
                    WHERE pt.player_1 = ? OR pt.player_2 = ?
                """, (p["id"], p["id"])).fetchall()

                played_set = {r["game_nr"] for r in played}
                game_history = {gn: ("P" if gn in played_set else "-") for gn in game_nrs}

                results.append({**dict(p), "game_history": game_history})

            # 4️⃣ Sort for CLI display
            if show_all:
                results.sort(key=lambda p: p["name"].lower())
            else:
                results.sort(key=lambda p: p.get("timestamp") or "")

            return game_nrs, results

    def checkin_players(self, names: List[str]) -> List[Dict]:
        """
        Check in players matching the given partial names.
        
        Returns a list of dicts with:
        {
            "id": int,
            "name": str,
            "status_before": str,
            "status_after": str,
            "message": str
        }
        """
        results = []

        with get_connection() as conn:
            for name_query in names:
                search_pattern = f"%{name_query}%"

                matches = conn.execute(
                    "SELECT id, name, status FROM players WHERE name LIKE ?",
                    (search_pattern,)
                ).fetchall()

                if not matches:
                    results.append({
                        "id": None,
                        "name": name_query,
                        "status_before": None,
                        "status_after": None,
                        "message": f"No player found matching '{name_query}'"
                    })
                    continue

                for row in matches:
                    player_id = row["id"]
                    player_name = row["name"]
                    status_before = row["status"]

                    if status_before == "P":
                        results.append({
                            "id": player_id,
                            "name": player_name,
                            "status_before": status_before,
                            "status_after": status_before,
                            "message": "Already checked in"
                        })
                        continue

                    results.append({
                        "id": player_id,
                        "name": player_name,
                        "status_before": status_before,
                        "status_after": None,  # will be updated after confirmation
                        "message": "Pending check-in"
                    })

        return results

    def perform_checkin(self, player_ids: List[int]) -> List[int]:
        """
        Actually update the database to check in players.

        Args:
            player_ids: list of DB IDs to check in

        Returns:
            List of successfully checked-in player IDs
        """
        updated_ids = []

        if not player_ids:
            return updated_ids

        with get_connection() as conn:
            for pid in player_ids:
                cursor = conn.execute(
                    """
                    UPDATE players
                    SET status = 'P',
                        timestamp = time('now', 'localtime')
                    WHERE id = ? AND status != 'P'
                    """,
                    (pid,)
                )
                if cursor.rowcount > 0:
                    updated_ids.append(pid)
            conn.commit()

        return updated_ids

    def checkout_players(self, names: List[str]) -> List[Dict]:
        """
        Check out players matching the given partial names.
        
        Returns a list of dicts with:
        {
            "id": int,
            "name": str,
            "status_before": str,
            "status_after": str,
            "message": str
        }
        """
        results = []

        with get_connection() as conn:
            for name_query in names:
                search_pattern = f"%{name_query}%"

                matches = conn.execute(
                    "SELECT id, name, status FROM players WHERE name LIKE ?",
                    (search_pattern,)
                ).fetchall()

                if not matches:
                    results.append({
                        "id": None,
                        "name": name_query,
                        "status_before": None,
                        "status_after": None,
                        "message": f"No player found matching '{name_query}'"
                    })
                    continue

                for row in matches:
                    player_id = row["id"]
                    player_name = row["name"]
                    status_before = row["status"]

                    if status_before in ("A", "E"):
                        msg = "Not checked in" if status_before == "A" else \
                              "Already checked out" if status_before == "E" else \
                              "Unknown status"
                        results.append({
                            "id": player_id,
                            "name": player_name,
                            "status_before": status_before,
                            "status_after": status_before,
                            "message": msg
                        })
                        continue

                    results.append({
                        "id": player_id,
                        "name": player_name,
                        "status_before": status_before,
                        "status_after": None,  # will be updated after confirmation
                        "message": "Pending check-out"
                    })

        return results

    def perform_checkout(self, player_ids: List[int]) -> List[int]:
        """
        Perform checkout (set status = 'E') for given player IDs.

        Returns list of successfully checked-out player IDs.
        """
        updated_ids = []

        if not player_ids:
            return updated_ids

        with get_connection() as conn:
            for pid in player_ids:
                cursor = conn.execute(
                    """
                    UPDATE players
                    SET status = 'E'
                    WHERE id = ? AND status = 'P'
                    """,
                    (pid,)
                )
                if cursor.rowcount > 0:
                    updated_ids.append(pid)
            conn.commit()

        return updated_ids

    def get_active_player_id(
        self, 
        name: str, 
        confirm_callback: Callable[[str], bool] = None
    ) -> int:
        """
        Returns the player ID for a given name (partial match allowed).
        Raises exceptions if player not found, ambiguous, or inactive.
        Optional `confirm_callback` is called when a player is inactive
        and allows re-check-in.
        """
        search_term = f"%{name}%"

        with get_connection() as conn:
            matches = conn.execute(
                "SELECT id, name, status FROM players WHERE name LIKE ?",
                (search_term,)
            ).fetchall()

        # CASE 1: No match
        if not matches:
            raise PlayerNotFoundError(f"No player found matching '{name}'")

        # CASE 2: Multiple matches
        if len(matches) > 1:
            active_matches = [m for m in matches if m["status"] == "P"]
            if len(active_matches) == 1:
                player = active_matches[0]
            else:
                # Ambiguous (all inactive or multiple active)
                raise AmbiguousPlayerError(name, [m["name"] for m in matches])
        else:
            player = matches[0]

        # CASE 3: Inactive players ('E' or 'A')
        if player["status"] in ["E", "A"]:
            status_msg = "already checked out (Early)" if player["status"] == "E" else "NOT checked in yet"
            prompt_msg = f"re-check them in" if player["status"] == "E" else "check them in"

            if confirm_callback:
                proceed = confirm_callback(f"{player['name']} has {status_msg}. Would you like to {prompt_msg}?")
                if proceed:
                    with get_connection() as conn:
                        conn.execute(
                            """
                            UPDATE players 
                            SET status = 'P',
                                timestamp = time('now', 'localtime') 
                            WHERE id = ?
                            """,
                            (player["id"],)
                        )
                        conn.commit()
                else:
                    raise PlayerNotActiveError(f"Operation cancelled for '{player['name']}'")
            else:
                raise PlayerNotActiveError(f"{player['name']} has {status_msg}")

        return player["id"]
    
    def get_opponent_count(self, p1: int, p2: int) -> int:
        """Checks how many times p1 and p2 were on opposite sides."""
        with get_connection() as conn:
            query = """
                SELECT COUNT(*) FROM participations p1
                JOIN participations p2 ON p1.game_id = p2.game_id
                WHERE p1.court_side != p2.court_side
                  AND (
                    (p1.player_1 = ? OR p1.player_2 = ?) AND 
                    (p2.player_1 = ? OR p2.player_2 = ?)
                  )
            """
            return conn.execute(query, (p1, p1, p2, p2)).fetchone()[0]

    def assign_game(
            self,
            game_nr: int,
            court_nr: int,
            duration: int,
            side_a: Tuple[int, int],
            side_b: Tuple[int, int],
            confirm_callback: Callable[[str], bool] = None
        ) -> None:
            """
            Assigns 4 players to a specific game and court.

            Returns:
                pair_history: Dict of side name -> previous pairing count
            
            Raises:
                DuplicateAssignmentError: if a player is already assigned in this game
                CourtAlreadyAssignedError: if the court is already assigned
                PairingConflictError: if a pair has played together before (warning-level)
            """
            all_players = list(side_a) + list(side_b)

            with get_connection() as conn:
                try:
                    # 1️⃣ Check if any players already assigned to this game
                    placeholders = ', '.join(['?'] * len(all_players))
                    query = f"""
                        SELECT p.name 
                        FROM participations pt
                        JOIN games g ON pt.game_id = g.id
                        JOIN players p ON (p.id = pt.player_1 OR p.id = pt.player_2)
                        WHERE g.game_nr = ? 
                        AND p.id IN ({placeholders})
                    """
                    existing = conn.execute(query, [game_nr] + all_players).fetchall()
                    if existing:
                        raise DuplicateAssignmentError(
                            f"Player(s) {', '.join(r['name'] for r in existing)} already assigned to another court"
                        )

                    # 2️⃣ Check previous pairings
                    for side_name, p1, p2 in [("Side A", side_a[0], side_a[1]), ("Side B", side_b[0], side_b[1])]:
                        history = conn.execute("""
                            SELECT COUNT(*) FROM participations 
                            WHERE (player_1 = ? AND player_2 = ?) 
                            OR (player_1 = ? AND player_2 = ?)
                        """, (p1, p2, p2, p1)).fetchone()[0]

                        if history > 0 and confirm_callback:
                            msg = f"The pair on {side_name} has played together {history} time(s) before."
                            if not confirm_callback(msg):
                                raise PairingConflictError(f"Assignment cancelled by user for {side_name}")

                    opponent_pairs = [
                        (side_a[0], side_b[0]),
                        (side_a[0], side_b[1]),
                        (side_a[1], side_b[0]),
                        (side_a[1], side_b[1]),
                    ]
                    for p1, p2 in opponent_pairs:
                        opponent_count = self.get_opponent_count(p1, p2)

                        if opponent_count > 2:
                            msg = (
                                f"Players {p1} and {p2} have already played "
                                f"against each other {opponent_count} time(s)."
                            )

                            if confirm_callback:
                                if not confirm_callback(msg):
                                    raise PairingConflictError(
                                        f"Opponent limit exceeded for players {p1} vs {p2}"
                                    )
                            else:
                                raise PairingConflictError(msg)
                    
                    # 3️⃣ Insert the game
                    cursor = conn.execute(
                        "INSERT INTO games (game_nr, court_nr, duration) VALUES (?, ?, ?)",
                        (game_nr, court_nr, duration)
                    )
                    game_id = cursor.lastrowid

                    # 4️⃣ Insert participations
                    participation_data = [
                        (game_id, 'Side A', side_a[0], side_a[1]),
                        (game_id, 'Side B', side_b[0], side_b[1])
                    ]
                    conn.executemany(
                        "INSERT INTO participations (game_id, court_side, player_1, player_2) VALUES (?, ?, ?, ?)",
                        participation_data
                    )
                    conn.commit()

                except sqlite3.IntegrityError:
                    conn.rollback()
                    raise CourtAlreadyAssignedError(f"Court {court_nr} is already assigned for Game {game_nr}")

    def get_game_report(self):
        with get_connection() as conn:
            return conn.execute("""
                SELECT g.game_nr, g.court_nr, g.duration, pt.court_side, 
                       p1.name as p1_name, p2.name as p2_name
                FROM games g
                JOIN participations pt ON g.id = pt.game_id
                JOIN players p1 ON pt.player_1 = p1.id
                JOIN players p2 ON pt.player_2 = p2.id
                ORDER BY g.game_nr, g.court_nr
            """).fetchall()

    def get_partnership_count(self, p1_id: int, p2_id: int) -> int:
        """Checks if these two have ever been on the same side."""
        with get_connection() as conn:
            query = """
                SELECT COUNT(*) 
                FROM participations 
                WHERE (player_1 = ? AND player_2 = ?) 
                   OR (player_1 = ? AND player_2 = ?)
            """
            return conn.execute(query, (p1_id, p2_id, p2_id, p1_id)).fetchone()[0]

    def get_player_gender(self, player_id: int) -> str:
        """Returns the gender character ('M' or 'F') from the database."""
        with get_connection() as conn:
            result = conn.execute("SELECT gender FROM players WHERE id = ?", (player_id,)).fetchone()
            return result["gender"] if result else "M"
            
    def is_gender_balanced(self, p1_id, p2_id, p3_id, p4_id) -> bool:
        """
        Returns False if it is 2 Females vs 2 Males.
        Otherwise returns True.
        """
        g1, g2 = self.get_player_gender(p1_id), self.get_player_gender(p2_id)
        g3, g4 = self.get_player_gender(p3_id), self.get_player_gender(p4_id)
        
        side_a = {g1, g2}
        side_b = {g3, g4}

        # Check if Side A is all Female ('F') and Side B is all Male ('M')
        if side_a == {'F'} and side_b == {'M'}:
            return False
        # Check if Side A is all Male ('M') and Side B is all Female ('F')
        if side_a == {'M'} and side_b == {'F'}:
            return False
            
        return True
    
    def generate_valid_assignments(self, player_ids: List[int]) -> Optional[Tuple[List[Tuple], List[str]]]:
        """
        Finds valid groupings for courts of 4 players.
        Returns:
            (assignments, warnings)
            OR None if impossible
        """
        available = list(player_ids)
        assignments = []
        warnings = []

        while len(available) >= 4:
            found_court = False
            current_pool = available[:4]

            for p in permutations(current_pool):
                p1, p2, p3, p4 = p

                # RULE 1: No previous partnership
                if self.get_partnership_count(p1, p2) == 0 and \
                    self.get_partnership_count(p3, p4) == 0:

                    # RULE 2: Gender balance
                    if self.is_gender_balanced(p1, p2, p3, p4):

                        # RULE 3: Opponent frequency warning
                        opp_counts = [
                            self.get_opponent_count(p1, p3),
                            self.get_opponent_count(p1, p4),
                            self.get_opponent_count(p2, p3),
                            self.get_opponent_count(p2, p4),
                        ]

                        if any(c > 2 for c in opp_counts):
                            warnings.append(
                                f"High opponent frequency (>2) detected on court "
                                f"with players {self.get_player_name_by_id(p1)},{self.get_player_name_by_id(p2)} " 
                                f"vs {self.get_player_name_by_id(p3)},{self.get_player_name_by_id(p4)}"
                            )

                        assignments.append(((p1, p2), (p3, p4)))
                        available = available[4:]
                        found_court = True
                        break

            if not found_court:
                return None

        return assignments, warnings

    def get_player_name_by_id(self, player_id: int) -> str:
        with get_connection() as conn:
            result = conn.execute(
                "SELECT name FROM players WHERE id = ?", (player_id,)
            ).fetchone()
            return result["name"] if result else "Unknown"

    def get_next_game_number(self) -> int:
        """Returns the highest game_nr + 1, or 1 if no games exist."""
        with get_connection() as conn:
            result = conn.execute("SELECT MAX(game_nr) as max_nr FROM games").fetchone()
            current_max = result["max_nr"] if result["max_nr"] is not None else 0
            return current_max + 1

    def get_rotation_prioritised(self):
        with get_connection() as conn:
            query = f"""
                WITH ranked_rounds AS (
                    SELECT DISTINCT game_nr
                    FROM games
                    ORDER BY game_nr DESC
                ),
                last_two AS (
                    SELECT 
                        game_nr,
                        ROW_NUMBER() OVER (ORDER BY game_nr DESC) AS rn
                    FROM ranked_rounds
                ),
                round_numbers AS (
                    SELECT
                        MAX(CASE WHEN rn = 1 THEN game_nr END) AS last_game,
                        MAX(CASE WHEN rn = 2 THEN game_nr END) AS prev_game
                    FROM last_two
                ),
                player_rounds AS (
                    SELECT 
                        p.id,
                        p.name,
                        p.gender,
                        p.timestamp,
                        MAX(CASE WHEN g.game_nr = r.last_game THEN 1 ELSE 0 END) AS played_last_game,
                        CASE 
                            WHEN r.prev_game IS NULL THEN NULL
                            ELSE MAX(CASE WHEN g.game_nr = r.prev_game THEN 1 ELSE 0 END)
                        END AS played_prev_game
                    FROM players p
                    CROSS JOIN round_numbers r
                    LEFT JOIN participations pa
                        ON p.id IN (pa.player_1, pa.player_2)
                    LEFT JOIN games g
                        ON g.id = pa.game_id
                    AND g.game_nr IN (r.prev_game, r.last_game)
                    WHERE p.status = 'P'
                    GROUP BY p.id
                )
                SELECT
                    id,
                    name,
                    gender,
                    timestamp,
                    played_prev_game,
                    played_last_game,
                    CASE
					WHEN played_prev_game IS NULL 
						THEN CASE 
								WHEN played_last_game = 1 THEN 1
								ELSE -1
							 END
					WHEN played_prev_game = 0 AND played_last_game = 0 THEN -2
					WHEN played_prev_game = 1 AND played_last_game = 0 THEN -1
					WHEN played_prev_game = 0 AND played_last_game = 1 THEN 1
					WHEN played_prev_game = 1 AND played_last_game = 1 THEN 2
				END AS priority
                FROM player_rounds
                ORDER BY priority NULLS FIRST, timestamp;
            """
            return conn.execute(query).fetchall()
 
    def reset_games_and_players(self):
        """Clears all games and resets player statuses/timestamps."""
        with get_connection() as conn:
            # 1. Clear game history (Order: Child table first)
            conn.execute("DELETE FROM participations")
            conn.execute("DELETE FROM games")
            
            # 2. Reset Player States
            # Assuming your columns are 'status', 'timestamp'
            conn.execute("""
                UPDATE players 
                SET status = 'A', 
                    timestamp = NULL
            """)
            
            # 3. Reset Auto-increment IDs for Games
            conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('games', 'participations')")
            
            conn.commit()

    def get_game_ids(self, game_nr: int):
        with get_connection() as conn:
            cur = conn.execute(
                "SELECT id FROM games WHERE game_nr = ?",
                (game_nr,),
            )
            rows = cur.fetchall()

            if not rows:
                raise GameNotFoundError(f"Game {game_nr} not found.")

            return [row["id"] for row in rows]
    
    def find_participation(self, game_ids: list[int], player_id: int):
        placeholders = ",".join("?" * len(game_ids))

        with get_connection() as conn:
            cur = conn.execute(
                f"""
                SELECT *
                FROM participations
                WHERE game_id IN ({placeholders})
                AND (player_1 = ? OR player_2 = ?)
                """,
                (*game_ids, player_id, player_id),
            )
            return cur.fetchone()
    
    def player_already_in_game(self, game_ids: list[int], player_id: int):
        return self.find_participation(game_ids, player_id) is not None
    
    def replace_player(self, participation_row, old_player, new_player):
        with get_connection() as conn:
            if participation_row["player_1"] == old_player:
                conn.execute(
                    "UPDATE participations SET player_1 = ? WHERE id = ?",
                    (new_player, participation_row["id"]),
                )
            else:
                conn.execute(
                    "UPDATE participations SET player_2 = ? WHERE id = ?",
                    (new_player, participation_row["id"]),
                )
    
    def swap_player(
            self, 
            game_nr: int, 
            player_out: str, 
            player_in: str,
            confirm_callback: Callable[[str], bool] = None
        ):
        game_ids = self.get_game_ids(game_nr)
        p_out = self.get_active_player_id(player_out)
        p_in = self.get_active_player_id(player_in, confirm_callback)

        if p_out == p_in:
            raise PegboardError(
                f"Cannot swap a player with themselves."
            )
        
        part_out = self.find_participation(game_ids, p_out)
        if not part_out:
            raise PegboardError(
                f"Player {player_out} is not playing in game {game_nr}."
            )

        part_in = self.find_participation(game_ids, p_in)
        
        # -----------------------------------------
        # CASE 1: Court ↔ Court
        # -----------------------------------------
        if part_in:

            if part_out["id"] == part_in["id"]:
                raise PairingConflictError(
                    "Both players are already on the same side."
                )

            self.replace_player(part_out, p_out, p_in)
            self.replace_player(part_in, p_in, p_out)

            return (
                f"Swapped Player {player_out} "
                f"with Player {player_in} (court-to-court)."
            )

        # -----------------------------------------
        # CASE 2: Court ↔ Sitting
        # -----------------------------------------
        else:

            self.replace_player(part_out, p_out, p_in)
            return (
                f"Swapped Player {player_out} "
                f"with sitting Player {player_in}."
            )