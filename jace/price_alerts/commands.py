from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class CommandError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: tuple[str, ...]


def parse_command(text: str) -> ParsedCommand:
    cleaned = " ".join(text.strip().split())
    if not cleaned.startswith("/"):
        raise CommandError("Commands must start with /.")
    parts = cleaned.split()
    raw_name = parts[0][1:].lower()
    raw_name = raw_name.split("@", 1)[0]
    # Public command surface is fixed by the integration spec: only /alert,
    # /alerts, /deletealert, /clearalerts and /alerthistory are accepted.
    # /delete, /alertCAprice and /alertcaprice are deliberately NOT exposed.
    # The values below are internal handler names, not public commands.
    aliases = {
        "alert": "alert",
        "alerts": "alerts",
        "deletealert": "delete",
        "clearalerts": "clear",
        "alerthistory": "history",
    }
    name = aliases.get(raw_name)
    if not name:
        raise CommandError("Unknown alert command.")
    return ParsedCommand(name, tuple(parts[1:]))


def parse_target(value: str) -> Decimal:
    try:
        target = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise CommandError("Target price must be a positive number.") from exc
    if not target.is_finite() or target <= 0:
        raise CommandError("Target price must be a positive number.")
    return target


def validate_address(address: str) -> str:
    if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", address):
        raise CommandError("Invalid Solana contract address")
    return address

