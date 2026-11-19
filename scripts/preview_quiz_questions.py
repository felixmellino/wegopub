"""Content-only Streamlit preview. Synthetic packs; no login or database writes."""
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st

from core.quiz_questions import LOGIC_TEMPLATES, logic_question, math_question
from data.quiz_questions import QuestionPack, load_general_bank, prepare_pack
from theme import apply_theme

st.set_page_config(page_title='Quiz questions — preview', layout='centered')
apply_theme()
st.title('Quiz Duel · Content preview')
st.caption('Developer preview · No stakes, points or database changes')

mode = st.radio('Question type', ('Three-round pack', 'General knowledge', 'Multiplication', 'Logic'), horizontal=True)
bank = load_general_bank()
if mode == 'General knowledge':
    selected = st.selectbox('Question', range(len(bank)), format_func=lambda i: f'{i + 1:03d} · {bank[i].topic}')
    question = bank[selected]
elif mode == 'Multiplication':
    left, right = st.columns(2)
    a = left.number_input('First factor', min_value=1, max_value=10, value=7, step=1)
    b = right.number_input('Second factor', min_value=1, max_value=10, value=8, step=1)
    key = ('math', a, b)
    if st.session_state.get('preview_key') != key:
        st.session_state['preview_key'] = key
        st.session_state['preview_question'] = math_question(left=a, right=b).snapshot()
    from core.quiz_questions import Question
    question = Question.from_snapshot(st.session_state['preview_question'])
elif mode == 'Logic':
    template = st.selectbox('Logic template', LOGIC_TEMPLATES)
    key = ('logic', template)
    generate = st.button('Generate another logic question')
    if st.session_state.get('preview_key') != key or generate:
        st.session_state['preview_key'] = key
        st.session_state['preview_question'] = logic_question(template=template).snapshot()
    from core.quiz_questions import Question
    question = Question.from_snapshot(st.session_state['preview_question'])
else:
    generate = st.button('Generate another pack')
    if 'preview_pack' not in st.session_state or generate:
        st.session_state['preview_pack'] = prepare_pack(str(uuid4())).snapshot()
    pack = QuestionPack.from_snapshot(st.session_state['preview_pack'])
    round_ = st.radio('Round', (0, 1, 2), format_func=lambda n: ('1 · General knowledge', '2 · Multiplication', '3 · Logic')[n])
    question = pack.rounds[round_]
    st.caption(f'Shared saved pack · {pack.pack_id}')

st.subheader(question.category.capitalize())
st.text(question.question)
for index, option in enumerate(question.options):
    st.button(f'{"ABCD"[index]}. {option}', key=f'preview_answer_{index}', width='stretch')
with st.expander('Review answer and explanation'):
    st.write(f'Correct: {"ABCD"[question.correct_index]} · {question.answer}')
    st.write(question.explanation)
    if question.source_url:
        st.link_button('Reference source', question.source_url)
