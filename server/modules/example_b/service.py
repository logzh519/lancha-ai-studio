"""In-process event receipt for demonstrating the current event bus semantics."""

from modules.example_a.contract import ItemCreated

_received: list[ItemCreated] = []


def on_item_created(event: ItemCreated) -> None:
    _received.append(event)


def list_received() -> list[ItemCreated]:
    return list(reversed(_received))


def clear_received() -> None:
    _received.clear()