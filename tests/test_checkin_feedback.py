from dataclasses import replace

import pytest

from core.checkin_feedback import captured_territory
from tests.test_scoring_v1 import entry


@pytest.mark.parametrize('previous_kind,previous_size,expected', [
    ('beer', 'medium', 'territory-a'),  # Strictly passes the previous owner.
    ('beer', 'large', None),           # Ties keep the previous owner.
    ('shot', None, None),              # Remains behind.
])
def test_capture_follows_existing_ownership_rules(previous_kind, previous_size, expected):
    previous = entry('prior', 'rival', previous_kind, previous_size, 0, order=1)
    saved = entry('saved', 'me', 'beer', 'large', 2, order=2)
    assert captured_territory(saved.id, [saved, previous]) == expected


def test_first_claim_counts_but_defending_your_territory_does_not():
    first = entry('first', 'me', 'beer', 'small', 0, order=1)
    defence = entry('defence', 'me', 'beer', 'medium', 2, order=2)
    assert captured_territory(first.id, [first, defence]) == 'territory-a'
    assert captured_territory(defence.id, [first, defence]) is None


def test_later_recapture_does_not_hide_original_capture_and_other_seasons_are_ignored():
    prior = entry('prior', 'rival', 'beer', 'medium', 0, order=1)
    saved = entry('saved', 'me', 'beer', 'large', 2, order=2)
    later = entry('later', 'rival', 'shot', None, 4, order=3)
    other_season = replace(prior, id='other-season-entry', season_id='other-season')
    assert captured_territory(saved.id, [later, saved, other_season, prior]) == 'territory-a'


@pytest.mark.parametrize('changes', [
    {'territory_id': None, 'location_check_result': 'outside'},
    {'points_awarded': 0}, {'location_check_result': 'uncertain'},
])
def test_outside_zero_and_unverified_entries_never_capture(changes):
    saved = replace(entry('saved', 'me', 'beer', 'large', 0), **changes)
    assert captured_territory(saved.id, [saved]) is None


def test_unsaved_entry_has_no_capture_feedback():
    assert captured_territory('unsaved', []) is None
