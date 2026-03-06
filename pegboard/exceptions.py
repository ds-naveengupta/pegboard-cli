# pegboard/exceptions.py

class PegboardError(Exception):
    """Base class for all Pegboard domain errors."""
    pass

class PlayerNotFoundError(PegboardError):
    pass

class AmbiguousPlayerError(PegboardError):
    def __init__(self, name: str, matches: list[str]):
        self.name = name
        self.matches = matches
        super().__init__(f"Multiple matches for '{name}': {', '.join(matches)}")

class PlayerNotActiveError(PegboardError):
    pass

class DuplicateAssignmentError(PegboardError):
    pass

class CourtAlreadyAssignedError(PegboardError):
    pass

class PairingConflictError(PegboardError):
    pass

class InvalidCSVFormatError(PegboardError):
    pass

class GameNotFoundError(PegboardError):
    pass