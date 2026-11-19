"""Profile edits preserve identity and reuse existing credential rules."""
from dataclasses import replace
from core.auth import hash_password, validate_password, validate_profile_names, verify_password


def edit_profile(player, first_name, last_name, username, users):
    first_name, last_name, username = validate_profile_names(first_name, last_name, username)
    if any(u["id"] != player.id and u["display_name"].strip().lower() == username.lower() for u in users):
        raise ValueError("That username is already taken.")
    return replace(player, first_name=first_name, last_name=last_name, display_name=username)


def change_password(player, current, password, confirmation):
    if not verify_password(current, player.pin_hash):
        raise ValueError("Current password is incorrect.")
    validate_password(password, confirmation)
    if verify_password(password, player.pin_hash):
        raise ValueError("Choose a different password from your current password.")
    return replace(player, pin_hash=hash_password(password))
