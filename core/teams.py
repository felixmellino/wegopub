"""Team settings and display identities. Persistence enforces joins atomically."""


def validate_config(mode, count, capacity, assignment):
    if mode == "individual":
        if any(value is not None for value in (count, capacity, assignment)):
            raise ValueError("Individual lobbies cannot have team settings.")
    elif mode == "team":
        if type(count) is not int or not 2 <= count <= 16:
            raise ValueError("Choose between 2 and 16 teams.")
        if type(capacity) is not int or not 1 <= capacity <= 20:
            raise ValueError("Choose between 1 and 20 players per team.")
        if assignment not in ("random", "manual"):
            raise ValueError("Choose random assignment or player choice.")
    else:
        raise ValueError("Choose individual or team mode.")


def team_name(value):
    value = value.strip()
    if not 1 <= len(value) <= 40 or any(ord(char) < 32 for char in value):
        raise ValueError("Use a team name of 1–40 characters without control characters.")
    return value


def competitor(entry):
    """An accepted entry keeps its team identity even if membership changes later."""
    return entry.team_id or entry.membership_id
