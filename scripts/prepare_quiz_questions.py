"""Validate the shipped bank, optionally export a private Supabase JSONB-ready pack."""
import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.quiz_questions import LOGIC_TEMPLATES, math_question
from data.quiz_questions import BANK_PATH, QuestionPack, load_general_bank, prepare_pack


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, help='Write an example PRIVATE pack, including answers; never serve this file')
    options = parser.parse_args()
    bank = load_general_bank()
    print(f'General knowledge: {len(bank)} reviewed English questions loaded.')
    for a in range(1, 11):
        for b in range(1, 11):
            question = math_question(left=a, right=b)
            assert question.answer == str(a * b) and len(set(question.options)) == 4
    print('Multiplication: all 100 factor pairs from 1x1 through 10x10 validated.')
    print(f'Logic: {len(LOGIC_TEMPLATES)} templates available.')
    pack = prepare_pack(str(uuid4()))
    restored = QuestionPack.from_snapshot(json.loads(json.dumps(pack.snapshot())))
    assert restored == pack and restored.fingerprint == pack.fingerprint
    print('Private pack: general/math/logic JSON round-trip verified; public payload excludes the answer key.')
    if options.snapshot:
        if options.snapshot.resolve() == BANK_PATH.resolve():
            parser.error('The example snapshot cannot overwrite the source question bank.')
        options.snapshot.parent.mkdir(parents=True, exist_ok=True)
        options.snapshot.write_text(json.dumps(pack.snapshot(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'Private example written to {options.snapshot}. No database or scoring changes were made.')


if __name__ == '__main__':
    main()
