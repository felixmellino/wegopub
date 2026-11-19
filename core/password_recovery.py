"""Reset-code format shared by the account screen, storage and email."""
import re
import secrets

from core.auth import token_hash

RESET_MESSAGE = "If an account exists for that email, a reset code will be sent. Check your inbox and spam folder. Wait at least one minute before requesting another code."
RESET_ERROR = "The reset code is incorrect, expired or unavailable. Request a new code or try again in 15 minutes."


def new_reset_code():
    raw = secrets.token_hex(8).upper()
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def reset_code_hash(code, credential_version):
    normalized = code.strip().replace("-", "").replace(" ", "").upper()
    if not re.fullmatch(r"[0-9A-F]{16}", normalized):
        raise ValueError(RESET_ERROR)
    # A previously issued code stops matching after a password change.
    return token_hash(normalized + ":" + credential_version)
