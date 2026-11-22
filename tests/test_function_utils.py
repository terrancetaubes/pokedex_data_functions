import pytest

from function_utils import (
    _parse_url_records,
    _run_id_from_path,
    _serialize_url_records,
    _slugify,
    _validate_run_id,
)


def test_slugify_makes_safe_folder_names():
    assert _slugify("Mr. Mime") == "mr-mime"
    assert _slugify("  Farfetch'd  ") == "farfetch-d"


def test_slugify_falls_back_for_empty_input():
    assert _slugify("") == "unknown-pokemon"
    assert _slugify("!!!") == "unknown-pokemon"


def test_validate_run_id_accepts_generated_style_ids():
    assert _validate_run_id("20261121T120000Z-ab12cd34") == "20261121T120000Z-ab12cd34"


@pytest.mark.parametrize("bad", ["", "../etc", "a/b", "x" * 81, "run id"])
def test_validate_run_id_rejects_unsafe_values(bad):
    with pytest.raises(ValueError):
        _validate_run_id(bad)


def test_url_records_round_trip():
    records = [
        {"pokemon_id": 1, "pokemon_name": "Bulbasaur", "url": "https://example/1"},
        {"pokemon_id": 2, "pokemon_name": "Ivysaur", "url": "https://example/2"},
    ]
    assert _parse_url_records(_serialize_url_records(records)) == records


def test_parse_url_records_skips_incomplete_rows():
    content = "pokemon_id\tpokemon_name\turl\n1\tBulbasaur\thttps://example/1\n\tNoId\thttps://example/x\n"
    parsed = _parse_url_records(content)
    assert [r["pokemon_id"] for r in parsed] == [1]


def test_parse_url_records_rejects_empty_file():
    with pytest.raises(ValueError):
        _parse_url_records("pokemon_id\tpokemon_name\turl\n")


def test_run_id_from_bronze_path():
    path = "bronze/source/20261121T120000Z-ab12cd34/pokedex_rows.html"
    assert _run_id_from_path(path) == "20261121T120000Z-ab12cd34"


def test_run_id_from_short_path_fails():
    with pytest.raises(ValueError):
        _run_id_from_path("bronze/source")
