"""Versioned question bank and private JSONB-ready packs for future Quiz Duel."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from random import SystemRandom

from core.quiz_questions import Question, math_question, logic_question, shuffled

BANK_PATH = Path(__file__).parent / 'quiz' / 'general_en_v1.json'
PACK_VERSION = 1


@lru_cache(maxsize=1)
def load_general_bank() -> tuple[Question, ...]:
    """Server-local content; cache immutable records, never a player's game state."""
    return read_general_bank(BANK_PATH)


def read_general_bank(path: Path) -> tuple[Question, ...]:
    bank = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(bank, dict) or type(bank.get('schema_version')) is not int
            or bank['schema_version'] != 1 or bank.get('language') != 'en'
            or bank.get('bank_version') != 'general-en-v1' or not isinstance(bank.get('questions'), list)):
        raise ValueError('Unsupported general-knowledge bank.')
    questions = tuple(Question.from_snapshot(dict(schema_version=1, **row)) for row in bank['questions'])
    if len(questions) != 100 or len({q.id for q in questions}) != len(questions):
        raise ValueError('The v1 general bank must contain 100 unique question IDs.')
    if len({q.question.casefold() for q in questions}) != len(questions):
        raise ValueError('The general bank contains repeated questions.')
    if any(q.category != 'general' or not q.source_url or not q.checked_on for q in questions):
        raise ValueError('General questions need their category, source and review date.')
    return questions


@dataclass(frozen=True)
class QuestionPack:
    """A shared private snapshot: persist once; never generate per participant."""
    pack_id: str
    rounds: tuple[Question, ...]

    def __post_init__(self):
        if not isinstance(self.pack_id, str) or not self.pack_id.strip() or len(self.pack_id) > 120:
            raise ValueError('A stable pack ID is required.')
        if (not isinstance(self.rounds, tuple) or len(self.rounds) != 3
                or any(not isinstance(q, Question) for q in self.rounds)
                or tuple(q.category for q in self.rounds) != ('general', 'math', 'logic')):
            raise ValueError('A pack must contain general, math and logic in that order.')

    def snapshot(self) -> dict:
        return dict(schema_version=PACK_VERSION, pack_id=self.pack_id,
                    rounds=[q.snapshot() for q in self.rounds])

    @classmethod
    def from_snapshot(cls, value: dict) -> QuestionPack:
        if (not isinstance(value, dict) or type(value.get('schema_version')) is not int
                or value['schema_version'] != PACK_VERSION or set(value) != {'schema_version', 'pack_id', 'rounds'}
                or not isinstance(value['rounds'], list)):
            raise ValueError('Unsupported question pack.')
        return cls(value['pack_id'], tuple(Question.from_snapshot(q) for q in value['rounds']))

    @property
    def fingerprint(self) -> str:
        """Detect a changed pack/order when validating persisted snapshots."""
        encoded = json.dumps(self.snapshot(), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        return sha256(encoded.encode('utf-8')).hexdigest()

    def public_round(self, index: int) -> dict:
        if type(index) is not int or index not in range(3):
            raise ValueError('Choose a round from zero to two.')
        return dict(pack_id=self.pack_id, round=index, **self.rounds[index].public_payload())


def prepare_pack(pack_id: str, rng=None) -> QuestionPack:
    """Future server creation path: save snapshot to Supabase before revealing it."""
    rng = rng or SystemRandom()
    general = shuffled(rng.choice(load_general_bank()), rng)
    return QuestionPack(pack_id, (general, math_question(rng), logic_question(rng)))


def prepare_decider(rng=None, *, used_ids=()) -> Question:
    """Extra general-knowledge question on a tie; do not repeat used questions."""
    rng = rng or SystemRandom()
    available = [q for q in load_general_bank() if q.id not in used_ids]
    if not available:
        raise ValueError('No unused general-knowledge questions remain.')
    return shuffled(rng.choice(available), rng)


def prepare_duel_deck(duel_id: str, rng=None) -> list[dict]:
    """Private three-round pack plus three distinct general-knowledge deciders."""
    from core.quiz_duel import CONFIG
    rng = rng or SystemRandom()
    pack = prepare_pack(duel_id, rng)
    questions = list(pack.rounds)
    used = {questions[0].id}
    for _ in range(CONFIG['max_deciders']):
        question = prepare_decider(rng, used_ids=used)
        questions.append(question)
        used.add(question.id)
    return [q.snapshot() for q in questions]
