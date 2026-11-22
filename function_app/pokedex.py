from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag


POKEDEX_URL = "https://pokemondb.net/pokedex/all"
POKEMONDB_BASE_URL = "https://pokemondb.net"



# =============================================================================
# PRIMARY FUNCTION: Return filtered source rows and their matching Pokemon URL records.
# =============================================================================
def create_pokedex_html_urls() -> tuple[str, list[dict[str, Any]]]:
    """Return filtered source rows and their matching Pokemon URL records."""
    soup = get_html(POKEDEX_URL)
    source_rows = get_pokedex_rows(soup)
    selected_rows, url_records = filter_pokedex_rows_urls(source_rows)
    rows_html = serialize_pokedex_rows(selected_rows)
    
    return rows_html, url_records


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Fetch HTML with a browser-style user agent and a request timeout.
# -----------------------------------------------------------------------------
def get_html(url: str, timeout: int = 30) -> BeautifulSoup:
    """Fetch HTML with a browser-style user agent and a request timeout."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    
    return BeautifulSoup(response.text, "html.parser")


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Return data rows from the Pokedex table, excluding its header row.
# -----------------------------------------------------------------------------
def get_pokedex_rows(soup: BeautifulSoup) -> list[Tag]:
    """Return data rows from the Pokedex table, excluding its header row."""
    table = soup.find("table", id="pokedex")
    if table is None:
        raise ValueError("Could not find the Pokedex table on PokemonDB.")
        
    return table.find_all("tr")[1:]


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Keep the requested National Dex range and create matching URL records.
# -----------------------------------------------------------------------------
def filter_pokedex_rows_urls(
    rows: list[Tag],
    max_national_dex_number: int = 493,
) -> tuple[list[Tag], list[dict[str, Any]]]:
    """Keep the requested National Dex range and create matching URL records."""
    selected_rows: list[Tag] = []
    url_records: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue

        sort_value = cells[0].get("data-sort-value")
        if sort_value is None:
            continue

        try:
            national_dex_number = int(sort_value)
        except (TypeError, ValueError):
            continue

        if national_dex_number > max_national_dex_number:
            continue

        row_details = _get_row_name_and_url(row)
        if row_details is None:
            continue

        pokemon_name, url = row_details
        if url in seen_urls:
            continue

        seen_urls.add(url)
        pokemon_id = len(url_records) + 1
        selected_rows.append(row)
        url_records.append(
            {
                "pokemon_id": pokemon_id,
                "pokemon_name": pokemon_name,
                "url": url,
            }
        )

    if not selected_rows:
        raise ValueError("No Pokemon rows passed the Pokedex filter.")

    return selected_rows, url_records


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Return a row's linked Pokemon name and URL, or None if incomplete.
# -----------------------------------------------------------------------------
def _get_row_name_and_url(row: Tag) -> tuple[str, str] | None:
    """Return a row's linked Pokemon name and URL, or None if incomplete."""
    cells = row.find_all("td")
    if len(cells) < 10:
        return None

    link = cells[1].find("a")
    if link is None or not link.get("href"):
        return None

    name = link.get_text(strip=True)
    url = urljoin(POKEMONDB_BASE_URL, link["href"])
    if not name:
        return None

    return name, url


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Serialize the selected table rows as an HTML text payload.
# -----------------------------------------------------------------------------
def serialize_pokedex_rows(rows: list[Tag]) -> str:
    """Serialize the selected table rows as an HTML text payload."""
    return "\n".join(str(row) for row in rows)


# -----------------------------------------------------------------------------
# UTILITY FUNCTION: Recreate row elements from the stored Pokedex HTML text.
# -----------------------------------------------------------------------------
def parse_pokedex_rows_html(rows_html: str) -> list[Tag]:
    """Recreate row elements from the stored Pokedex HTML text."""
    soup = BeautifulSoup(rows_html, "html.parser")
    rows = soup.find_all("tr")
    if not rows:
        raise ValueError("The stored Pokedex rows file contains no table rows.")
        
    return rows


# =============================================================================
# PRIMARY FUNCTION: Extract base stats while preserving the URL file's sequential IDs.
# =============================================================================
def get_pokedex_stats(rows: list[Tag]) -> pd.DataFrame:
    """Extract base stats while preserving the URL file's sequential IDs."""
    columns = [
        "pokemon_id",
        "pokemon",
        "total",
        "hp",
        "attack",
        "defense",
        "special_attack",
        "special_defense",
        "speed",
    ]

    data: list[list[Any]] = []

    for pokemon_id, row in enumerate(rows, start=1):
        cells = row.find_all("td")
        if len(cells) < 10:
            continue

        pokemon_link = cells[1].find("a")
        if pokemon_link is None:
            continue

        pokemon = pokemon_link.get_text(strip=True)
        stats = [int(cell.get_text(strip=True)) for cell in cells[3:10]]
        data.append([pokemon_id, pokemon] + stats)

    if not data:
        raise ValueError("No Pokemon stats could be extracted.")

    return pd.DataFrame(data, columns=columns)