"""Exercise the content preview through real Streamlit widgets, without Supabase."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from data.quiz_questions import QuestionPack

ROOT = Path(__file__).resolve().parents[1]


def test_pack_preview_preserves_the_same_questions_when_rounds_change_and_refresh():
    page = AppTest.from_file(ROOT / 'scripts/preview_quiz_questions.py', default_timeout=10).run()
    assert not page.exception
    stored = page.session_state['preview_pack']
    pack = QuestionPack.from_snapshot(stored)
    assert any(text.value == pack.rounds[0].question for text in page.text)
    page.radio[1].set_value(1).run()
    assert not page.exception and page.session_state['preview_pack'] == stored
    assert any(text.value == pack.rounds[1].question for text in page.text)
    page.run()
    assert page.session_state['preview_pack'] == stored
    page.radio[1].set_value(2).run()
    assert any(text.value == pack.rounds[2].question for text in page.text)


def test_preview_selects_all_content_types_and_math_boundaries():
    page = AppTest.from_file(ROOT / 'scripts/preview_quiz_questions.py', default_timeout=10).run()
    page.radio[0].set_value('Multiplication').run()
    page.number_input[0].set_value(10)
    page.number_input[1].set_value(10).run()
    assert not page.exception and any(text.value == 'What is 10 × 10?' for text in page.text)
    assert any('100' in item.value for item in page.markdown)
    page.radio[0].set_value('Logic').run()
    page.selectbox[0].set_value('boxes').run()
    assert not page.exception and any('Exactly one of four boxes' in item.value for item in page.text)
    next(b for b in page.button if b.label == 'Generate another logic question').click().run()
    assert not page.exception
    page.radio[0].set_value('General knowledge').run()
    assert not page.exception and len(page.selectbox[0].options) == 100
    page.selectbox[0].set_value(99).run()
    assert not page.exception and any('2024/25 Champions League' in item.value for item in page.text)
