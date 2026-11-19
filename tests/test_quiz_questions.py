"""Allowed selections, all multiplication boundaries, and reusable private packs."""
from dataclasses import FrozenInstanceError, replace
import json
from random import Random
import re

import pytest

from core.quiz_questions import LOGIC_TEMPLATES, Question, logic_question, math_question, shuffled
from data.quiz_questions import QuestionPack, load_general_bank, prepare_decider, prepare_pack, read_general_bank


def test_general_bank_has_100_unique_reviewed_english_questions_and_correct_mappings():
    bank = load_general_bank()
    assert len(bank) == len({q.id for q in bank}) == len({q.question for q in bank}) == 100
    assert all(q.category == 'general' and q.source_url.startswith('https://') and q.checked_on for q in bank)
    football = [q for q in bank if q.topic in ('Premier League', 'Bundesliga', 'European & international football')]
    assert len(football) == 20
    assert all(q.difficulty in ('easy', 'easy-medium') for q in bank)
    for question in football:
        years = re.findall(r'\b(?:19|20)\d{2}\b', question.reference_period)
        assert all(int(year) >= 2022 for year in years)
    assert all(len(set(q.options)) == 4 and q.answer == q.options[q.correct_index] for q in bank)
    assert bank[0].answer == 'Portugal'
    assert not any('census' in q.question.casefold() for q in bank)


@pytest.mark.parametrize('left', range(1, 11))
@pytest.mark.parametrize('right', range(1, 11))
def test_every_one_to_ten_multiplication_has_one_correct_and_three_distinct_plausible_answers(left, right):
    question = math_question(Random(left * 100 + right), left=left, right=right)
    assert question.category == 'math' and question.answer == str(left * right)
    assert f'{left} × {right}' in question.question
    assert len(set(question.options)) == 4
    assert all(1 <= int(option) <= 100 for option in question.options)
    for seed in range(3):
        assert math_question(Random(seed), left=left, right=right).answer == question.answer


@pytest.mark.parametrize('left,right', [(0, 5), (11, 5), (5, -1), (5, 11), (True, 2), ('4', 2), (2, 2.0), (2, None)])
def test_invalid_multiplication_factors_are_rejected(left, right):
    with pytest.raises(ValueError):
        math_question(left=left, right=right)


@pytest.mark.parametrize('template', LOGIC_TEMPLATES)
def test_all_logic_templates_produce_valid_different_variants(template):
    generated = [logic_question(Random(seed), template=template) for seed in range(100)]
    assert len({q.question for q in generated}) > 1
    assert all(q.category == 'logic' and len(set(q.options)) == 4 for q in generated)
    assert all(q.answer in q.options and q.explanation for q in generated)


def test_box_puzzles_have_exactly_one_solution_by_exhaustive_truth_check():
    for seed in range(100):
        question = logic_question(Random(seed), template='boxes')
        claims = re.findall(r'The gold is (not )?in the (red|blue|green|yellow) box', question.question)
        assert len(claims) == 4
        solutions = []
        for colour in ('red', 'blue', 'green', 'yellow'):
            truths = [colour != target if negate else colour == target for negate, target in claims]
            if sum(truths) == 1:
                solutions.append(colour.capitalize())
        assert solutions == [question.answer]


def test_logic_ordering_matches_the_chain_of_constraints():
    for seed in range(40):
        question = logic_question(Random(seed), template='ordering')
        constraints = re.findall(r'(Amelia|Ben|Clara|Daniel) finished before (Amelia|Ben|Clara|Daniel)', question.question)
        assert len(constraints) == 3
        ordered = [constraints[0][0], *(pair[1] for pair in constraints)]
        assert question.answer == ordered[1 if 'second?' in question.question else 2]


def test_shuffle_preserves_correctness_without_mutating_cached_questions():
    original = load_general_bank()[0]
    snapshot = original.snapshot()
    positions = set()
    for seed in range(40):
        variant = shuffled(original, Random(seed))
        assert variant.answer == original.answer
        assert set(variant.options) == set(original.options)
        positions.add(variant.correct_index)
    assert positions == {0, 1, 2, 3} and original.snapshot() == snapshot
    with pytest.raises(FrozenInstanceError):
        original.correct_index = 0


@pytest.mark.parametrize('changes', [
    {'options': ('A', 'B', 'C')}, {'options': ('A', 'a ', 'B', 'C')}, {'options': ('A', '', 'B', 'C')},
    {'correct_index': True}, {'correct_index': -1}, {'correct_index': 4}, {'correct_index': '1'},
    {'category': 'other'}, {'question': ' '}, {'source_url': 'http://example.test'},
])
def test_invalid_question_content_is_rejected(changes):
    with pytest.raises(ValueError):
        replace(load_general_bank()[0], **changes)


def test_same_saved_pack_survives_restart_and_gives_both_players_identical_public_questions():
    pack = prepare_pack('duel-123', Random(193))
    saved = json.dumps(pack.snapshot())
    recovered = QuestionPack.from_snapshot(json.loads(saved))
    assert recovered == pack and recovered.fingerprint == pack.fingerprint
    assert tuple(q.category for q in recovered.rounds) == ('general', 'math', 'logic')
    for round_ in range(3):
        assert recovered.public_round(round_) == pack.public_round(round_)
        public = recovered.public_round(round_)
        assert set(public) == {'pack_id', 'round', 'id', 'category', 'question', 'options'}
        assert not {'correct_index', 'answer', 'explanation', 'source_url'} & set(public)
    assert QuestionPack.from_snapshot(json.loads(saved)).snapshot() == pack.snapshot()


def test_default_generator_needs_no_seed_and_different_private_orders_change_fingerprint():
    pack = prepare_pack('default-random')
    assert len(pack.rounds) == 3
    different = replace(pack, rounds=(replace(pack.rounds[0], options=tuple(reversed(pack.rounds[0].options)),
        correct_index=3 - pack.rounds[0].correct_index), *pack.rounds[1:]))
    assert different.fingerprint != pack.fingerprint
    assert different.rounds[0].answer == pack.rounds[0].answer


def test_default_packs_keep_advanced_box_puzzles_out_of_the_easy_game():
    for seed in range(100):
        pack = prepare_pack('easy-default', Random(seed))
        assert pack.rounds[2].topic != 'boxes'
        assert pack.rounds[2].difficulty == 'easy-medium'


@pytest.mark.parametrize('version', [None, True, 0, 2, '1'])
def test_unknown_pack_or_question_versions_are_rejected(version):
    pack = prepare_pack('version-check', Random(1)).snapshot()
    with pytest.raises(ValueError):
        QuestionPack.from_snapshot(dict(pack, schema_version=version))
    question = pack['rounds'][0]
    with pytest.raises(ValueError):
        Question.from_snapshot(dict(question, schema_version=version))


def test_corrupted_or_misordered_packs_and_round_indexes_are_rejected():
    pack = prepare_pack('invalid-check', Random(2))
    for rounds in (list(pack.rounds), tuple(reversed(pack.rounds)), pack.rounds[:2]):
        with pytest.raises(ValueError):
            replace(pack, rounds=rounds)
    for index in (-1, 3, True, '0'):
        with pytest.raises(ValueError):
            pack.public_round(index)
    value = pack.snapshot()
    value['rounds'][0]['extra'] = 'unexpected'
    with pytest.raises(ValueError):
        QuestionPack.from_snapshot(value)


def test_decider_does_not_repeat_questions_already_used():
    bank = load_general_bank()
    available = bank[-1]
    decider = prepare_decider(Random(0), used_ids=[q.id for q in bank[:-1]])
    assert decider.id == available.id and decider.answer == available.answer
    with pytest.raises(ValueError):
        prepare_decider(used_ids=[q.id for q in bank])


def test_corrupt_bank_is_rejected_instead_of_silently_loading_partial_content(tmp_path):
    from data.quiz_questions import BANK_PATH
    raw = json.loads(BANK_PATH.read_text(encoding='utf-8'))
    damaged = tmp_path / 'questions.json'
    for mutation in ('duplicate', 'missing', 'wrong_category', 'bad_version'):
        value = json.loads(json.dumps(raw))
        if mutation == 'duplicate':
            value['questions'][1] = value['questions'][0]
        elif mutation == 'missing':
            value['questions'].pop()
        elif mutation == 'wrong_category':
            value['questions'][0]['category'] = 'math'
        else:
            value['schema_version'] = True
        damaged.write_text(json.dumps(value), encoding='utf-8')
        with pytest.raises(ValueError):
            read_general_bank(damaged)
