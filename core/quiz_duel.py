"""Quiz Duel rules. Database transactions independently enforce these boundaries."""
from core.chug_duel import night_id, next_reset, validate_pair
from core.scoring_v1 import scoring_open, utc

CONFIG = dict(version=1, min_stake=3, max_stake=10, round_seconds=20,
              countdown_seconds=3, result_seconds=3, invitation_seconds=600,
              setup_seconds=600, game_seconds=600, max_deciders=3)
ACTIVE = {'accepted', 'playing', 'between'}
FINAL = {'completed', 'forfeited', 'draw', 'declined', 'cancelled', 'expired'}


def validate_stake(stake):
    if type(stake) is not int or not CONFIG['min_stake'] <= stake <= CONFIG['max_stake']:
        raise ValueError('Choose an integer stake from 3 to 10 points.')
    return stake


def available(season, now):
    active = utc(season.starts_at) <= utc(now) < utc(season.ends_at)
    return active and ((season.scoring_rules or {}).get('test_mode') is True or scoring_open(now, season))


def allowances(member, night, duels, *, test_mode=False):
    if test_mode:
        return True, True
    used = [d for d in duels if d['game_night'] == night
            and (d['status'] in ACTIVE or d.get('started_at'))]
    return (not any(d['challenger_id'] == member for d in used),
            not any(d['opponent_id'] == member for d in used))


def round_winner(challenger_answer, opponent_answer):
    """Answers are (correct, server receipt time), or None for no answer."""
    a = challenger_answer if challenger_answer and challenger_answer[0] else None
    b = opponent_answer if opponent_answer and opponent_answer[0] else None
    if a and b:
        return 'challenger' if a[1] < b[1] else 'opponent' if b[1] < a[1] else None
    return 'challenger' if a else 'opponent' if b else None


def outcome(round_no, challenger_score, opponent_score):
    """Called after a round is resolved: 0–2 normal, 3–5 deciding questions."""
    if round_no < 2 and max(challenger_score, opponent_score) < 2:
        return 'next'
    if challenger_score != opponent_score:
        return 'challenger' if challenger_score > opponent_score else 'opponent'
    return 'draw' if round_no == 2 + CONFIG['max_deciders'] else 'next'


def component_action(value, duel):
    if not isinstance(value, dict) or value.get('duel_id') != duel['id']:
        return None
    if not isinstance(value.get('event_id'), str) or not 1 <= len(value['event_id']) <= 100:
        return None
    action = value.get('action')
    if action in ('ready', 'forfeit', 'cancel', 'back'):
        return action, None, None
    if (action == 'answer' and type(value.get('round_no')) is int
            and value['round_no'] == duel.get('round_no')
            and type(value.get('choice')) is int and value['choice'] in range(4)):
        return action, value['round_no'], value['choice']
    return None


ERRORS = {
    'permission_denied': 'This quiz is not available to your account.',
    'quiz_stake': 'Choose an integer stake from 3 to 10 points.',
    'quiz_funds': 'Both accounts need the full available stake. Reserved points cannot be used twice.',
    'quiz_reserved_points': 'These points are committed to a quiz. Finish the quiz before reducing them.',
    'quiz_team': 'Choose a player from another team. Both players must join a team first.',
    'quiz_busy': 'A player already has an accepted or running minigame. Finish it first.',
    'quiz_pending': 'Cancel your open quiz invitation before sending another.',
    'quiz_limit': 'A quiz challenge or acceptance is already used or reserved for this evening.',
    'quiz_unavailable': 'The quiz has changed or expired. Refresh to recover its saved state.',
    'quiz_early': 'Wait for the countdown to finish.',
    'quiz_answer_locked': 'Your first answer is already locked for this round.',
    'quiz_invalid_answer': 'Choose one of the four answers for the current round.',
    'quiz_questions': 'The shared question pack could not be accepted. Refresh and try again.',
    'scoring_closed': 'Quizzes are available during the season scoring window; test seasons can play while active.',
}
