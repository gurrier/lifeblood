"""Tests for parsing Lifeblood's supply levels page."""

from __future__ import annotations

import datetime

import pytest

from custom_components.lifeblood.api import (
    LIFEBLOOD_TZ,
    LifebloodClient,
    LifebloodConnectionError,
    LifebloodParseError,
    parse_ajax_response,
    parse_levels,
)
from custom_components.lifeblood.const import SOURCE_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import load_fixture, load_json_fixture


def _levels(data):
    return {k: v.level for k, v in data.levels.items()}


def test_parse_national_page() -> None:
    data, form_build_id = parse_levels(load_fixture("page_national.html"), "national")

    assert form_build_id == "form-r8xf5UHwJZn4lmzrbgp21h5MAQpd9PKHHWbd8tUAmKo"
    assert data.region_code == "National"
    assert data.updated == datetime.datetime(2026, 10, 14, 6, 0, tzinfo=LIFEBLOOD_TZ)
    assert _levels(data) == {
        "o_positive": "critical",
        "o_negative": "critical",
        "a_positive": "critical",
        "a_negative": "critical",
        "b_positive": "critical",
        "b_negative": "critical",
        "ab_positive": "need_more",
        "ab_negative": "good",
        "plasma": "ok",
    }
    assert data.levels["o_positive"].label == "Critical"
    assert data.updated_text is not None and "14 October 2026" in data.updated_text
    assert data.levels["plasma"].percent == 98.32
    assert data.levels["o_positive"].percent is None


def test_parse_ajax_nt_not_collected() -> None:
    data = parse_ajax_response(load_json_fixture("ajax_nt.json"), "nt")

    assert data.region_code == "NT"
    assert data.levels["b_negative"].level == "not_collected"
    assert data.levels["ab_positive"].level == "not_collected"
    assert data.levels["ab_negative"].level == "not_collected"
    assert data.levels["plasma"].level == "need_more"
    assert data.levels["plasma"].percent == 94.77
    # The "Updated" line isn't part of the AJAX fragment.
    assert data.updated is None


def test_parse_ajax_act_ok_vs_good() -> None:
    """ACT has a red cell "good" class (Ok) beside a plasma "good" class (Good)."""
    data = parse_ajax_response(load_json_fixture("ajax_act.json"), "act")

    assert data.levels["ab_positive"].level == "ok"
    assert data.levels["ab_negative"].level == "good"
    assert data.levels["plasma"].level == "good"


@pytest.mark.parametrize(
    ("label", "drop_class", "plasma", "expected"),
    [
        ("Urgent", "appeal-mode", False, "critical"),
        ("Urgent", "critical", False, "very_low"),
        ("Fine", "good", False, "ok"),
        ("Fine", "great", False, "good"),
        ("Fine", "good", True, "good"),
        ("Fine", "need-more", True, "need_more"),
        ("Who knows", "unheard-of", False, None),
    ],
)
def test_unknown_label_falls_back_to_class(label, drop_class, plasma, expected) -> None:
    if plasma:
        html = (
            f'<div class="drop-div plasma-block VIC 99%"><div class="drop-plasma {drop_class}"></div>'
            f'<strong>Plasma</strong><div class="day-coverage">{label}</div></div>'
        )
        key = "plasma"
    else:
        html = (
            f'<div class="drop-div Opos"><div class="drop O+ {drop_class}"></div>'
            f'<strong>O+</strong><div class="day-coverage">{label}</div></div>'
        )
        key = "o_positive"
    data, _ = parse_levels(html, "vic")
    assert data.levels[key].level == expected
    assert data.levels[key].label == label


def test_updated_pm_and_aest() -> None:
    html = (
        '<div class="last-updated">Updated 1:30pm <span>(AEST), </span>'
        "<em> 3 July 2026</em></div>"
    )
    data, _ = parse_levels(html, "national")
    assert data.updated == datetime.datetime(2026, 7, 3, 13, 30, tzinfo=LIFEBLOOD_TZ)
    assert data.updated.utcoffset() == datetime.timedelta(hours=10)


def test_parse_ajax_without_levels() -> None:
    with pytest.raises(LifebloodParseError):
        parse_ajax_response([{"command": "settings"}], "vic")
    with pytest.raises(LifebloodParseError):
        parse_ajax_response({"not": "a list"}, "vic")


async def test_client_national_uses_page_only(hass, mock_lifeblood) -> None:
    client = LifebloodClient(async_get_clientsession(hass), "test")
    data = await client.async_get_levels("national")

    assert data.region_code == "National"
    assert mock_lifeblood.call_count == 1


async def test_client_region_posts_form(hass, mock_lifeblood) -> None:
    client = LifebloodClient(async_get_clientsession(hass), "test")
    data = await client.async_get_levels("vic")

    assert data.region_code == "VIC"
    assert data.levels["ab_positive"].level == "low"
    # Carried over from the full page.
    assert data.updated == datetime.datetime(2026, 10, 14, 6, 0, tzinfo=LIFEBLOOD_TZ)
    assert mock_lifeblood.call_count == 2
    _, _, form, _ = mock_lifeblood.mock_calls[1]
    assert form["lb_region_select"] == "victoria"
    assert form["form_build_id"] == "form-r8xf5UHwJZn4lmzrbgp21h5MAQpd9PKHHWbd8tUAmKo"


def test_form_build_id_scoped_to_stock_form() -> None:
    """Another Drupal form on the page must not supply the token."""
    html = (
        '<form><input name="form_build_id" value="form-other"/>'
        '<input name="form_id" value="newsletter"/></form>'
        '<form><input name="form_build_id" value="form-stock"/>'
        '<input name="form_id" value="stock_level_form"/></form>'
        '<form><input name="form_build_id" value="form-later"/>'
        '<input name="form_id" value="contact"/></form>'
    )
    _, form_build_id = parse_levels(html, "vic")
    assert form_build_id == "form-stock"


def test_region_code_falls_back_to_id() -> None:
    """Without the class-list code, the drop's id still names the region."""
    html = (
        '<div id="drop plasma-type VIC" class="drop-div plasma-block">'
        '<div class="drop-plasma okay"></div><strong>Plasma</strong>'
        '<div class="day-coverage">Ok</div></div>'
    )
    data, _ = parse_levels(html, "vic")
    assert data.region_code == "VIC"
    assert data.levels["plasma"].percent is None


def test_plasma_level_outside_its_options_warns(caplog) -> None:
    html = (
        '<div class="drop-div plasma-block VIC 90%"><div class="drop-plasma low"></div>'
        '<strong>Plasma</strong><div class="day-coverage">Low</div></div>'
    )
    data, _ = parse_levels(html, "vic")
    assert data.levels["plasma"].level == "low"
    assert "isn't a level Plasma has had before" in caplog.text


def test_unparseable_updated_warns(caplog) -> None:
    html = '<div class="last-updated">Updated 6am, 14 Oct 2026</div>'
    data, _ = parse_levels(html, "national")
    assert data.updated is None
    assert data.updated_text == "Updated 6am, 14 Oct 2026"
    assert "Couldn't parse Lifeblood's updated time" in caplog.text


async def test_client_accepts_page_without_region_code(hass, aioclient_mock, caplog) -> None:
    """A national page whose plasma drop is gone still yields the red cells."""
    page = load_fixture("page_national.html")
    start = page.index('<div class="plasma-wrapper">')
    end = page.index("</div>", page.index('day-coverage">  Ok', start)) + len("</div>")
    aioclient_mock.get(SOURCE_URL, text=page[:start] + page[end:])

    client = LifebloodClient(async_get_clientsession(hass), "test")
    data = await client.async_get_levels("national")

    assert data.region_code is None
    assert "plasma" not in data.levels
    assert data.levels["o_positive"].level == "critical"
    assert "No region code" in caplog.text
    assert aioclient_mock.call_count == 1


async def test_client_wrong_region_returned(hass, mock_lifeblood) -> None:
    """VIC data in reply to a NSW request must not be reported as NSW."""
    client = LifebloodClient(async_get_clientsession(hass), "test")
    with pytest.raises(LifebloodParseError):
        await client.async_get_levels("nsw")


async def test_client_http_error(hass, aioclient_mock) -> None:
    aioclient_mock.get(SOURCE_URL, status=503)
    client = LifebloodClient(async_get_clientsession(hass), "test")
    with pytest.raises(LifebloodConnectionError):
        await client.async_get_levels("national")


async def test_client_timeout(hass, aioclient_mock) -> None:
    aioclient_mock.get(SOURCE_URL, exc=TimeoutError)
    client = LifebloodClient(async_get_clientsession(hass), "test")
    with pytest.raises(LifebloodConnectionError):
        await client.async_get_levels("national")


async def test_client_page_without_levels(hass, aioclient_mock) -> None:
    aioclient_mock.get(SOURCE_URL, text="<html><body>Maintenance</body></html>")
    client = LifebloodClient(async_get_clientsession(hass), "test")
    with pytest.raises(LifebloodParseError):
        await client.async_get_levels("national")
