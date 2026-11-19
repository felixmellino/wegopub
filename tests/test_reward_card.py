"""The check-in reward card: what each saved-result case shows."""
from drink_entry_ui import reward_card_html


def test_matched_capture_shows_points_territory_and_chip():
    card = reward_card_html("3", "matched", territory="Bairro Alto", captured=True)
    assert 'reward-points">+3<' in card
    assert "in Bairro Alto" in card
    assert "You captured Bairro Alto!" in card


def test_team_capture_names_the_team():
    assert "Your team captured Le Pub!" in reward_card_html("2", "matched", territory="Le Pub", captured=True,
                                                            team_mode=True)


def test_no_chip_without_capture():
    assert "reward-chip" not in reward_card_html("2", "matched", territory="Le Pub")


def test_outside_is_season_points_only():
    card = reward_card_html("1", "outside")
    assert "season points only" in card and "reward-chip" not in card


def test_zero_points_uses_muted_variant():
    card = reward_card_html("0", "matched", territory="Le Pub")
    assert "reward-zero" in card and "zero points" in card


def test_owner_income_and_unavailable_notes():
    card = reward_card_html("4", "matched", owner_income="1", ownership_unavailable=True)
    assert "previous owner also earned +1 season points" in card
    assert "ownership update is unavailable" in card


def test_territory_name_is_escaped():
    card = reward_card_html("1", "matched", territory="<b>Pub</b>", captured=True)
    assert "<b>" not in card and "&lt;b&gt;Pub&lt;/b&gt;" in card
