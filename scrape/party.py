"""How a party is split across one or two rooms.

The booking engine does not accept a single party size for two rooms. The
search URL carries one occupancy per room:

    rooms=2&ad1=1&ch1=2&inf1=0&ad2=1&ch2=1&inf2=0

Hotel terms require a parent in the room with any child, and the booking
widget itself will not offer 0 adults on the second room. Every generated
split therefore puts at least one adult in each room. Mirror splits
(the same two occupancies swapped) are searched once; a live check showed
they return the same prices with the rooms exchanged.

Ages are not sent. The engine only receives the adult, child, and infant
counts produced by ``classify_party``.

Configured parties:

* ``2a3c`` — 2 adults and children aged 4, 8 and 12. Two rooms try
  (1 adult + 2 children) + (1 adult + 1 child), then
  (1 adult + 3 children) + (1 adult).
* ``4a1c`` — 4 adults and one child aged 8. One room is
  ``ad1=4&ch1=1&inf1=0``. Two rooms use the even split
  ``ad1=2&ch1=1&inf1=0&ad2=2&ch2=0&inf2=0`` (room 1 is 2 adults + the
  child, room 2 is the other 2 adults) and also the uneven splits
  (3 adults + 1 child) + (1 adult) and (1 adult + 1 child) + (3 adults).
  The cheaper split the engine actually returns is the one stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scrape.dates import Occupancy, classify_party

# Default composition. History files written before the party column, and
# rows that omit it, are this party.
DEFAULT_PARTY = "2a3c"
# Public rate, no promocode query parameter. A missing promo column means this.
DEFAULT_PROMO = "none"

# adults, child ages. Classification (infant / adult brackets) is applied later.
PARTY_PRESETS: dict[str, tuple[int, tuple[int, ...]]] = {
    "2a3c": (2, (4, 8, 12)),
    "4a1c": (4, (8,)),
}
PROMOS: tuple[str, ...] = (DEFAULT_PROMO, "mhot")


@dataclass(frozen=True)
class RoomAsk:
    adults: int
    children: int
    infants: int

    def to_dict(self, number: int) -> dict:
        return {
            "room": number,
            "adults": self.adults,
            "children": self.children,
            "infants": self.infants,
        }


@dataclass(frozen=True)
class Split:
    rooms: tuple[RoomAsk, ...]

    @property
    def room_count(self) -> int:
        return len(self.rooms)

    def label(self) -> str:
        return "; ".join(
            f"room {index}: {_bits(room)}"
            for index, room in enumerate(self.rooms, start=1)
        )

    def to_dict(self) -> dict:
        return {
            "label": self.label(),
            "rooms": [room.to_dict(index) for index, room in enumerate(self.rooms, start=1)],
        }

    def query_pairs(self) -> list[tuple[str, str]]:
        pairs = [("rooms", str(self.room_count))]
        for index, room in enumerate(self.rooms, start=1):
            pairs.append((f"ad{index}", str(room.adults)))
            pairs.append((f"ch{index}", str(room.children)))
            pairs.append((f"inf{index}", str(room.infants)))
        return pairs


def candidate_splits(occupancy: Occupancy, room_count: int) -> list[Split]:
    """Unique adult-in-each-room splits, most even child distribution first."""
    if room_count not in (1, 2):
        raise ValueError("rooms must be 1 or 2")
    if room_count == 1:
        return [Split((RoomAsk(occupancy.adults, occupancy.children, occupancy.infants),))]
    if occupancy.adults < 2:
        return []

    seen: set[tuple[tuple[int, int, int], ...]] = set()
    splits: list[Split] = []
    for adults_1 in range(1, occupancy.adults):
        adults_2 = occupancy.adults - adults_1
        for children_1 in range(occupancy.children + 1):
            children_2 = occupancy.children - children_1
            for infants_1 in range(occupancy.infants + 1):
                infants_2 = occupancy.infants - infants_1
                key = tuple(sorted((
                    (adults_1, children_1, infants_1),
                    (adults_2, children_2, infants_2),
                )))
                if key in seen:
                    continue
                seen.add(key)
                rooms = [
                    RoomAsk(adults_1, children_1, infants_1),
                    RoomAsk(adults_2, children_2, infants_2),
                ]
                rooms.sort(key=lambda room: (room.children, room.infants, room.adults), reverse=True)
                splits.append(Split(tuple(rooms)))
    splits.sort(key=lambda split: _imbalance(split))
    return splits


def _imbalance(split: Split) -> tuple[int, int]:
    loads = [room.children + room.infants for room in split.rooms]
    return (max(loads) - min(loads), max(loads))


def _bits(room: RoomAsk) -> str:
    parts: list[str] = []
    if room.adults:
        parts.append(f"{room.adults} adult" + ("s" if room.adults != 1 else ""))
    if room.children:
        parts.append(f"{room.children} child" + ("ren" if room.children != 1 else ""))
    if room.infants:
        parts.append(f"{room.infants} infant" + ("s" if room.infants != 1 else ""))
    return " + ".join(parts) if parts else "empty"


def parse_party_list(value: str) -> list[str]:
    """Comma-separated party ids, first-seen order, no duplicates."""
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise ValueError("provide at least one party")
    unknown = [part for part in parts if part not in PARTY_PRESETS]
    if unknown:
        known = ", ".join(PARTY_PRESETS)
        raise ValueError(f"unknown party {unknown[0]!r}; choose from {known}")
    ordered: list[str] = []
    for part in parts:
        if part not in ordered:
            ordered.append(part)
    return ordered


def parse_promo_list(value: str) -> list[str]:
    """Comma-separated promo ids. ``none`` omits the code; ``mhot`` sends it."""
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise ValueError("provide at least one promo")
    unknown = [part for part in parts if part not in PROMOS]
    if unknown:
        known = ", ".join(PROMOS)
        raise ValueError(f"unknown promo {unknown[0]!r}; choose from {known}")
    ordered: list[str] = []
    for part in parts:
        if part not in ordered:
            ordered.append(part)
    return ordered


def selected_parties(values: list[str] | None) -> list[str]:
    """Omitting ``--party``, or naming every preset, runs each configured party."""
    if not values:
        return list(PARTY_PRESETS)
    return parse_party_list(",".join(values))


def selected_promos(values: list[str] | None) -> list[str]:
    """Omitting ``--promo`` runs ``none`` and ``mhot``."""
    if not values:
        return list(PROMOS)
    return parse_promo_list(",".join(values))


def occupancy_for(
    party_id: str,
    *,
    adult_from_age: int = 13,
    infant_under_age: int = 2,
    adults: int | None = None,
    child_ages: list[int] | None = None,
) -> Occupancy:
    """Occupancy for a configured party, with the usual age brackets."""
    if party_id not in PARTY_PRESETS:
        known = ", ".join(PARTY_PRESETS)
        raise ValueError(f"unknown party {party_id!r}; choose from {known}")
    preset_adults, preset_ages = PARTY_PRESETS[party_id]
    return classify_party(
        preset_adults if adults is None else adults,
        list(preset_ages if child_ages is None else child_ages),
        adult_from_age=adult_from_age,
        infant_under_age=infant_under_age,
    )


def combo_output_dir(base: Path, party: str, promo: str) -> Path:
    """Where one party × promo grid is written.

    ``output/eilat/`` is 2a3c with promo ``none`` (the original layout).
    Other combos are sibling directories, not extra rows in that file:

    * 2a3c / none → ``<base>/``
    * 2a3c / mhot → ``<base>/promo-mhot/``
    * 4a1c / none → ``<base>/party-4a1c/``
    * 4a1c / mhot → ``<base>/party-4a1c/promo-mhot/``
    """
    path = base
    if party != DEFAULT_PARTY:
        path = path / f"party-{party}"
    if promo != DEFAULT_PROMO:
        path = path / f"promo-{promo}"
    return path


def two_room_note(party: str) -> str:
    """Explain which two-room splits are requested for this party."""
    shared = (
        " The cheaper valid split is stored on the row. "
        "The same room code is used twice only when AvailableRooms says at least two remain."
    )
    if party == "4a1c":
        return (
            "rooms=2 is priced by summing one rate per room. The split keeps at least one adult "
            "in each room. For 4 adults and 1 child the documented even split is "
            "room 1 = 2 adults + 1 child (ad1=2&ch1=1&inf1=0) and room 2 = 2 adults "
            "(ad2=2&ch2=0&inf2=0). The other legal splits, (3 adults + 1 child) + (1 adult) and "
            "(1 adult + 1 child) + (3 adults), are requested too."
            + shared
        )
    return (
        "rooms=2 is priced by summing one rate per room. The split keeps at least one adult "
        "in each room. For 2 adults and 3 children the candidates are "
        "(1 adult + 2 children) + (1 adult + 1 child) and "
        "(1 adult + 3 children) + (1 adult)."
        + shared
    )
