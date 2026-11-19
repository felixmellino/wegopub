"""Quiz content and generators. No Streamlit, database, timing or scoring rules."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from random import SystemRandom


QUESTION_VERSION = 1
LOGIC_TEMPLATES = ('alternating', 'ordering', 'deduction', 'exclusion', 'conditional', 'boxes')
DEFAULT_LOGIC_TEMPLATES = LOGIC_TEMPLATES[:-1]  # long box puzzles stay an explicit advanced preview
CATEGORIES = ('general', 'math', 'logic')


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    question: str
    options: tuple[str, ...]
    correct_index: int
    explanation: str
    topic: str = ''
    difficulty: str = 'medium'
    reference_period: str = 'Stable fact'
    source_url: str = ''
    checked_on: str = ''

    def __post_init__(self):
        if self.category not in CATEGORIES:
            raise ValueError('Unsupported question category.')
        for name, limit in (('id', 120), ('question', 650), ('explanation', 650)):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError(f'Invalid question {name}.')
        if (not isinstance(self.options, tuple) or len(self.options) != 4
                or any(not isinstance(o, str) or not o.strip() or len(o) > 160 for o in self.options)
                or len({o.strip().casefold() for o in self.options}) != 4):
            raise ValueError('Each question needs four distinct, non-empty options.')
        if type(self.correct_index) is not int or self.correct_index not in range(4):
            raise ValueError('The correct option must be an index from zero to three.')
        for name in ('topic', 'difficulty', 'reference_period', 'source_url', 'checked_on'):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f'Invalid question {name}.')
        if self.source_url and not self.source_url.startswith('https://'):
            raise ValueError('Question references must use HTTPS.')

    @property
    def answer(self) -> str:
        return self.options[self.correct_index]

    def public_payload(self) -> dict:
        """Only the active question goes to a future player view; no answer key."""
        return dict(id=self.id, category=self.category, question=self.question, options=list(self.options))

    def snapshot(self) -> dict:
        """Private server/JSONB representation; never send this to the browser."""
        result = asdict(self)
        result['options'] = list(self.options)
        return dict(schema_version=QUESTION_VERSION, **result)

    @classmethod
    def from_snapshot(cls, value: dict) -> Question:
        if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != QUESTION_VERSION:
            raise ValueError('Unsupported question snapshot.')
        data = {key: item for key, item in value.items() if key != 'schema_version'}
        if not isinstance(data.get('options'), list):
            raise ValueError('Snapshot options must be a list.')
        data['options'] = tuple(data['options'])
        try:
            return cls(**data)
        except TypeError:
            raise ValueError('Invalid question snapshot fields.') from None


def shuffled(question: Question, rng=None) -> Question:
    """Shuffle once for both players, preserving the correct answer's mapping."""
    rng = rng or SystemRandom()
    indexes = list(range(4))
    rng.shuffle(indexes)
    return replace(question, options=tuple(question.options[i] for i in indexes),
                   correct_index=indexes.index(question.correct_index))


def _generated(id_, category, prompt, answer, wrong, explanation, *, rng, topic):
    # Distinct answers can coincide (e.g. 2x2 and 2+2). Remove those collisions.
    options = [str(answer)]
    for option in wrong:
        if str(option) not in options:
            options.append(str(option))
    if len(options) < 4:
        raise ValueError('Not enough distinct distractors.')
    question = Question(id_, category, prompt, tuple([options[0], *rng.sample(options[1:], 3)]),
                        0, explanation, topic=topic, difficulty='easy-medium')
    return shuffled(question, rng)


def math_question(rng=None, *, left=None, right=None) -> Question:
    """The entire 1x1 to 10x10 table is generated, with plausible wrong answers."""
    rng = rng or SystemRandom()
    if left is None and right is None:
        left, right = rng.randint(1, 10), rng.randint(1, 10)
    if any(type(n) is not int or not 1 <= n <= 10 for n in (left, right)):
        raise ValueError('Both factors must be integers from one to ten.')
    answer = left * right
    candidates = {left * (right + delta) for delta in (-1, 1)}
    candidates |= {(left + delta) * right for delta in (-1, 1)}
    candidates |= {answer + delta for delta in (-5, -3, -2, -1, 1, 2, 3, 5)}
    candidates |= {left + right}
    candidates = sorted(n for n in candidates if 1 <= n <= 100 and n != answer)
    return _generated(f'math-v1-{left}x{right}', 'math', f'What is {left} × {right}?',
        answer, candidates, f'{left} multiplied by {right} is {answer}.', rng=rng, topic='Multiplication 1–10')


def logic_question(rng=None, *, template=None) -> Question:
    """Use explicit rules and finite deductions, avoiding ambiguous odd-one-out puzzles."""
    rng = rng or SystemRandom()
    template = template or rng.choice(DEFAULT_LOGIC_TEMPLATES)
    if template not in LOGIC_TEMPLATES:
        raise ValueError('Unsupported logic template.')
    names = ['Amelia', 'Ben', 'Clara', 'Daniel']
    colours = ['red', 'blue', 'green', 'yellow']
    rng.shuffle(names)
    rng.shuffle(colours)
    if template == 'alternating':
        start, step = rng.randint(2, 9), rng.randint(2, 6)
        # Explicit rule ensures that only one of the four answers is possible.
        after_add = start + step
        after_double = after_add * 2
        answer = after_double + step
        return _generated(f'logic-v1-alternating-{start}-{step}', 'logic',
            f'A pattern alternates between adding {step} and doubling. It starts {start}, '
            f'{after_add}, {after_double}. What comes next?', answer,
            [after_double * 2, after_double + 1, answer - 1, answer + 1, after_double - step],
            f'The next operation is adding {step}: {after_double} + {step} = {answer}.',
            rng=rng, topic=template)
    if template == 'ordering':
        position = rng.choice((1, 2))
        prompt = (f'{names[0]} finished before {names[1]}. {names[1]} finished before {names[2]}. '
                  f'{names[2]} finished before {names[3]}. Who finished {"second" if position == 1 else "third"}?')
        return _generated('logic-v1-order-' + '-'.join(names) + f'-{position}', 'logic', prompt,
            names[position], [n for n in names if n != names[position]],
            f'The order is {", ".join(names)}. {names[position]} is {"second" if position == 1 else "third"}.',
            rng=rng, topic=template)
    colour = colours[0]
    if template == 'deduction':
        shape = rng.choice(('round', 'square', 'triangular'))
        return _generated(f'logic-v1-deduction-{colour}-{shape}', 'logic',
            f'All {colour} tokens are {shape}. This token is {colour}. What must be true?',
            f'It is {shape}.', [f'It is {colours[1]}.', 'It is made of metal.', 'It has a number on it.'],
            f'Every {colour} token is {shape}, so this token must be {shape}.', rng=rng, topic=template)
    if template == 'exclusion':
        return _generated(f'logic-v1-exclusion-{colour}', 'logic',
            f'No {colour} cards have a number on them. This card has a number on it. What must be true?',
            f'It is not {colour}.', [f'It is {colour}.', 'It is square.', f'It is {colours[1]}.'],
            f'A numbered card cannot be {colour}; nothing identifies its exact colour or shape.',
            rng=rng, topic=template)
    if template == 'conditional':
        return _generated(f'logic-v1-conditional-{colour}', 'logic',
            f'If a box is sealed, its indicator is {colour}. The indicator is not {colour}. What must be true?',
            'The box is not sealed.', ['The box is sealed.', 'The box is empty.', 'The box is heavy.'],
            f'A sealed box must show {colour}. Without that colour, it cannot be sealed.', rng=rng, topic=template)
    # Exactly one statement is true. A fixed four-statement construction has
    # exactly one solution; permuting colours changes the concrete question.
    a, b, c, d = colours
    prompt = (f'Exactly one of four boxes contains gold, and exactly one statement below is true. '
              f'Red box: "The gold is in the {a} box." '
              f'Blue box: "The gold is not in the {b} box." '
              f'Green box: "The gold is in the {d} box." '
              f'Yellow box: "The gold is not in the {a} box." Which box contains the gold?')
    result = _generated('logic-v1-boxes-' + '-'.join(colours), 'logic', prompt,
        b.capitalize(), [n.capitalize() for n in colours if n != b],
        f'Only gold in the {b} box makes exactly one statement true. '
        'The other locations make two or three statements true.', rng=rng, topic=template)
    return replace(result, difficulty='medium-hard')
