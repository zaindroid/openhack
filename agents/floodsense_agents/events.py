"""The two reference events and their replay windows, keyed by Copernicus EMS activation id (the contract's event_id).
Owner of the facts: Saleeta / Urvashi; this file only fixes the window the Watchers query and the point ids involved."""
from __future__ import annotations
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EventSpec:
    event_id: str
    name: str
    window_from_utc: str
    window_to_utc: str
    region: str
    river: str
    catchment: str
    river_points: tuple[str, ...]      # point_ids in hazard_timeline / discharge_daily that carry discharge
    rain_points: tuple[str, ...]       # point_ids that carry rain

    def as_dict(self) -> dict:
        return asdict(self)


EVENTS: dict[str, EventSpec] = {
    "EMSR773": EventSpec("EMSR773", "Valencia DANA, 29 Oct 2024", "2024-10-28T00:00:00Z", "2024-10-30T23:59:59Z",
                         "Valencia province", "Barranco del Poyo", "Poyo ravine catchment", ("poyo-ribaroja",), ("chiva", "turis")),
    "EMSR517": EventSpec("EMSR517", "Ahr valley flood, 14-15 Jul 2021", "2021-07-12T00:00:00Z", "2021-07-16T23:59:59Z",
                         "Ahr valley, Rhineland-Palatinate", "Ahr", "Ahr catchment (Eifel)", ("altenahr",), ("ahrweiler",)),
}
ALIASES = {"valencia_2024": "EMSR773", "ahr_2021": "EMSR517"}


def spec(event_id: str) -> EventSpec:
    key = ALIASES.get(event_id, event_id)
    if key not in EVENTS:
        raise KeyError(f"unknown event_id {event_id!r}; known: {', '.join(EVENTS)} (aliases: {', '.join(ALIASES)})")
    return EVENTS[key]
