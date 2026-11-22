from __future__ import annotations

from typing import Any

import pandas as pd
from bs4 import Tag

from pokedex import get_html


LEARNED_MOVE_COLUMNS = [
    "pokemon_id", "level", "move", "type", "category", "power", "accuracy"
]
TM_MOVE_COLUMNS = [
    "pokemon_id", "tm", "move", "type", "category", "power", "accuracy"
]


# =============================================================================
# PRIMARY FUNCTION: Extract one Pokemon detail page for one independent queue job.
# =============================================================================
def get_pokemon_data(url: str, pokemon_id: int) -> dict[str, Any]:
    """Extract one Pokemon detail page for one independent queue job."""
    soup = get_html(url)
    main = soup.find("main")

    if main is None:
        raise ValueError(f"Could not find the main content for {url}")

    pokemon_name = _get_pokemon_name(main)
    pokemon_bio = _get_pokemon_bio(main)
    pokedex_data = _get_vitals_data(main, "Pokédex data")
    training = _get_vitals_data(main, "Training")
    breeding = _get_vitals_data(main, "Breeding")
    pokedex_entry = _get_pokedex_entry(main)
    moves_learned, moves_tm = _get_pokemon_moves(main, pokemon_id)

    return {
        "pokemon_id": pokemon_id,
        "pokemon_name": pokemon_name,
        "pokemon_bio": pokemon_bio,
        "pokedex_entry": pokedex_entry,
        "pokedex_data": pokedex_data,
        "training": training,
        "breeding": breeding,
        "moves_learned": moves_learned,
        "moves_tm": moves_tm,
    }


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Return the page's H1 text, or None when the heading is missing.
# -----------------------------------------------------------------------------
def _get_pokemon_name(main: Tag) -> str | None:
    """Return the page's H1 text, or None when the heading is missing."""
    h1 = main.find("h1")
    return h1.get_text(strip=True) if h1 is not None else None


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Join the introductory biography paragraphs into one text value.
# -----------------------------------------------------------------------------
def _get_pokemon_bio(main: Tag) -> str:
    """Join the introductory biography paragraphs into one text value."""
    h1 = main.find("h1")
    basics = main.find("div", id="dex-basics")

    if h1 is None or basics is None:
        return ""

    paragraphs = []
    for element in h1.next_elements:
        if element is basics:
            break

        if isinstance(element, Tag) and element.name == "p":
            text = " ".join(element.get_text("", strip=False).split())
            if text:
                paragraphs.append(text)

    return " ".join(paragraphs)


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Return the key-value rows from one named Pokemon detail section.
# -----------------------------------------------------------------------------
def _get_vitals_data(main: Tag, section_name: str) -> dict[str, str]:
    """Return the key-value rows from one named Pokemon detail section."""
    panel = main.find("div", class_="sv-tabs-panel-list")
    if panel is None:
        return {}

    for heading in panel.find_all("h2"):
        if heading.get_text(strip=True) != section_name:
            continue

        table = heading.find_next("table", class_="vitals-table")
        if table is None:
            return {}

        data: dict[str, str] = {}
        for row in table.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if th is None or td is None:
                continue

            key = th.get_text(" ", strip=True)
            value = td.get_text(" ", strip=True).replace("\xa0", " ")

            if key == "Local №":
                continue
            if key == "National №":
                key = "Pokedex Number"

            data[key] = value

        return data

    return {}


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Return the combined text from the available Pokedex entries.
# -----------------------------------------------------------------------------
def _get_pokedex_entry(main: Tag) -> str:
    """Return the combined text from the available Pokedex entries."""
    heading = None

    for h2 in main.find_all("h2"):
        if h2.get_text(strip=True) == "Pokédex entries":
            heading = h2
            break

    if heading is None:
        return ""

    entries = []
    seen = set()

    for element in heading.next_elements:
        if isinstance(element, Tag) and element.name == "h2":
            break

        if (
            isinstance(element, Tag)
            and element.name == "div"
            and "resp-scroll" in element.get("class", [])
        ):
            table = element.find("table", class_="vitals-table")
            if table is None:
                continue

            for td in table.find_all("td"):
                text = td.get_text(" ", strip=True)
                if text and text not in seen:
                    entries.append(text)
                    seen.add(text)

    return " ".join(entries)


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Return an empty moves DataFrame with nullable integer and text fields.
# -----------------------------------------------------------------------------
def _empty_moves_dataframe(columns: list[str]) -> pd.DataFrame:
    """Return an empty moves DataFrame with nullable integer and text fields."""
    data: dict[str, pd.Series] = {}
    for column in columns:
        if column in ("pokemon_id", "power", "accuracy"):
            data[column] = pd.Series(dtype="Int64")
        else:
            data[column] = pd.Series(dtype="string")
            
    return pd.DataFrame(data)


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Parse one move table and normalize its columns and values.
# -----------------------------------------------------------------------------
def _get_moves_dataframe(
    table: Tag,
    pokemon_id: int,
    move_kind: str,
) -> pd.DataFrame:
    """Parse one move table and normalize its columns and values."""
    raw_headers = [
        th.get_text(" ", strip=True)
        for th in table.select("thead th")
    ]

    header_map = {
        "Cat.": "category",
        "Acc.": "accuracy",
        "Lv.": "level",
        "Move": "move",
        "Type": "type",
        "Power": "power",
        "TM": "tm",
    }
    headers = [
        header_map.get(header, header.strip().lower().replace(" ", "_"))
        for header in raw_headers
    ]

    if not headers:
        expected = (
            LEARNED_MOVE_COLUMNS if move_kind == "learned" else TM_MOVE_COLUMNS
        )
        return _empty_moves_dataframe(expected)

    rows_data = []
    for row in table.select("tbody tr"):
        cells = row.find_all("td", recursive=False)
        values = []

        for cell in cells:
            value = cell.get_text(" ", strip=True)

            if not value:
                image = cell.find("img")
                if image:
                    value = image.get("alt", "")

            if value in ("—", ""):
                value = None
            elif value == "∞":
                value = "100"

            values.append(value)

        if values and len(values) == len(headers):
            rows_data.append(values)

    moves_df = pd.DataFrame(rows_data, columns=headers)
    moves_df["pokemon_id"] = pokemon_id

    expected = (
        LEARNED_MOVE_COLUMNS if move_kind == "learned" else TM_MOVE_COLUMNS
    )

    # Add missing source columns as null to keep the Parquet schema stable.
    for column in expected:
        if column not in moves_df.columns:
            moves_df[column] = None

    moves_df = moves_df[expected].copy()

    # Keep special level markers, such as "Evo.", as text.
    for column in ("level", "tm", "move", "type", "category"):
        if column in moves_df.columns:
            moves_df[column] = moves_df[column].astype("string")

    # Remove a trailing percent sign before converting numeric fields.
    for column in ("power", "accuracy"):
        if column in moves_df.columns:
            numeric_values = (
                moves_df[column]
                .astype("string")
                .str.replace("%", "", regex=False)
            )
            moves_df[column] = pd.to_numeric(
                numeric_values, errors="coerce"
            ).astype("Int64")

    return moves_df


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Return the level-up and TM move DataFrames for one Pokemon.
# -----------------------------------------------------------------------------
def _get_pokemon_moves(
    main: Tag,
    pokemon_id: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the level-up and TM move DataFrames for one Pokemon."""
    wrapper_heading = None

    for h2 in main.find_all("h2"):
        if h2.get_text(strip=True).startswith("Moves learned by"):
            wrapper_heading = h2
            break

    if wrapper_heading is None:
        return (
            _empty_moves_dataframe(LEARNED_MOVE_COLUMNS),
            _empty_moves_dataframe(TM_MOVE_COLUMNS),
        )

    wrapper = wrapper_heading.find_next("div", class_="tabset-moves-game")
    if wrapper is None:
        return (
            _empty_moves_dataframe(LEARNED_MOVE_COLUMNS),
            _empty_moves_dataframe(TM_MOVE_COLUMNS),
        )

    moves_learned = _empty_moves_dataframe(LEARNED_MOVE_COLUMNS)
    moves_tm = _empty_moves_dataframe(TM_MOVE_COLUMNS)

    for heading in wrapper.find_all("h3"):
        heading_text = heading.get_text(strip=True).lower()
        table = heading.find_next("table", class_="data-table")

        if table is None:
            continue

        if "moves learnt by level up" in heading_text:
            moves_learned = _get_moves_dataframe(
                table, pokemon_id, "learned"
            )
        elif "moves learnt by tm" in heading_text:
            moves_tm = _get_moves_dataframe(table, pokemon_id, "tm")

    return moves_learned, moves_tm
