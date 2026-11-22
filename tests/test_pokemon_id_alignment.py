"""Check that pokemon_id agrees between the URL file and the stats file.

The URL file and the stats Parquet file are built in two different functions.
Downstream joins use pokemon_id as the key. If the two IDs differ, joins give
wrong results without any error. These tests run the real pipeline path:
filter rows -> serialize rows -> parse stored rows -> build stats.
"""

from bs4 import BeautifulSoup

from pokedex import (
    filter_pokedex_rows_urls,
    get_pokedex_rows,
    get_pokedex_stats,
    parse_pokedex_rows_html,
    serialize_pokedex_rows,
)


def _row(sort_value, name, href, stats=(318, 45, 49, 49, 65, 65, 45)):
    """Build one table row in the PokemonDB layout (10 cells)."""
    stat_cells = "".join(f"<td>{value}</td>" for value in stats)
    return (
        "<tr>"
        f'<td data-sort-value="{sort_value}">{sort_value}</td>'
        f'<td><a href="{href}">{name}</a></td>'
        "<td>Grass</td>"
        f"{stat_cells}"
        "</tr>"
    )


def _table(*rows):
    html = (
        '<table id="pokedex"><thead><tr><th>#</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )
    return BeautifulSoup(html, "html.parser")


def _run_pipeline(soup):
    """Return (url_records, stats_df) using the same steps as production."""
    source_rows = get_pokedex_rows(soup)
    selected_rows, url_records = filter_pokedex_rows_urls(source_rows)

    # Production stores the rows as HTML, then re-reads them in another function.
    stored_html = serialize_pokedex_rows(selected_rows)
    stats_df = get_pokedex_stats(parse_pokedex_rows_html(stored_html))
    return url_records, stats_df


def test_ids_and_names_match_for_clean_input():
    soup = _table(
        _row("0001", "Bulbasaur", "/pokedex/bulbasaur"),
        _row("0002", "Ivysaur", "/pokedex/ivysaur"),
        _row("0003", "Venusaur", "/pokedex/venusaur"),
    )

    url_records, stats_df = _run_pipeline(soup)

    assert [r["pokemon_id"] for r in url_records] == [1, 2, 3]
    assert list(stats_df["pokemon_id"]) == [r["pokemon_id"] for r in url_records]
    assert list(stats_df["pokemon"]) == [r["pokemon_name"] for r in url_records]


def test_ids_match_when_rows_are_dropped_by_the_filter():
    """Duplicate URLs, numbers above 493, and bad rows must not shift IDs."""
    soup = _table(
        _row("0001", "Bulbasaur", "/pokedex/bulbasaur"),
        # Alternate form: same URL as the row above, so the filter drops it.
        _row("0001", "Mega Bulbasaur", "/pokedex/bulbasaur"),
        # No numeric sort value: dropped.
        _row("n/a", "Broken", "/pokedex/broken"),
        _row("0002", "Ivysaur", "/pokedex/ivysaur"),
        # Above the National Dex cap of 493: dropped.
        _row("0494", "Victini", "/pokedex/victini"),
        _row("0003", "Venusaur", "/pokedex/venusaur"),
    )

    url_records, stats_df = _run_pipeline(soup)

    assert [r["pokemon_name"] for r in url_records] == [
        "Bulbasaur",
        "Ivysaur",
        "Venusaur",
    ]
    assert list(stats_df["pokemon_id"]) == [1, 2, 3]
    assert list(stats_df["pokemon"]) == [r["pokemon_name"] for r in url_records]


def test_stats_row_count_equals_url_record_count():
    soup = _table(
        *[
            _row(f"{n:04d}", f"Mon{n}", f"/pokedex/mon{n}")
            for n in range(1, 21)
        ]
    )

    url_records, stats_df = _run_pipeline(soup)

    assert len(stats_df) == len(url_records) == 20
    assert set(stats_df["pokemon_id"]) == {r["pokemon_id"] for r in url_records}


def test_stats_values_stay_with_the_right_pokemon():
    """The stats of a Pokemon must not move to another ID."""
    soup = _table(
        _row("0001", "Alpha", "/pokedex/alpha", stats=(100, 1, 2, 3, 4, 5, 6)),
        _row("0002", "Beta", "/pokedex/beta", stats=(200, 7, 8, 9, 10, 11, 12)),
    )

    _, stats_df = _run_pipeline(soup)

    beta = stats_df[stats_df["pokemon_id"] == 2].iloc[0]
    assert beta["pokemon"] == "Beta"
    assert (beta["total"], beta["hp"], beta["speed"]) == (200, 7, 12)
