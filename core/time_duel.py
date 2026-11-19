"""Time Duel boundary validation; PostgreSQL owns state and rewards."""
from core.chug_duel import validate_pair  # shared opponent eligibility, used by the UI

CONFIG = dict(version=1, rounds=3, min_seconds=5, max_seconds=12,
              ready_seconds=60, timer_seconds=30, invitation_seconds=600,
              boost_seconds=3600, multiplier=1.25)
ACTIVE = {'accepted', 'playing'}
FINAL = {'completed', 'draw', 'cancelled', 'declined', 'expired'}
ERRORS = {
    'permission_denied': 'This Time Duel is not available to your account.',
    'time_busy': 'Finish the accepted or running minigame first.',
    'time_limit': 'This Time Duel challenge or acceptance is already used or reserved tonight.',
    'time_pending': 'Cancel your existing Time Duel invitation first.',
    'time_action': 'This action is unavailable. Reopen the saved duel.',
    'time_evidence': 'The timing result could not be accepted.',
    'scoring_closed': 'Time Duel opens during the scoring window; test seasons can play while active.',
    'duel_team': 'Choose a member of an opposing team. Both players must join a team first.',
}


def outcome(targets_ms, challenger, opponent):
    """None is an abandoned round. An incomplete tie never grants a reward."""
    if len(targets_ms) != 3 or len(challenger) != 3 or len(opponent) != 3:
        raise ValueError('Three resolved rounds are required.')
    def score(values):
        return (sum(v is None for v in values),
                sum(abs(v-t) for v, t in zip(values, targets_ms) if v is not None))
    a, b = score(challenger), score(opponent)
    return 'challenger' if a < b else 'opponent' if b < a else 'both' if a[0] == 0 else 'none'


def component_action(value, duel):
    if not isinstance(value, dict) or value.get('duel_id') != duel['id']:
        return None
    if not isinstance(value.get('event_id'), str) or not 1 <= len(value['event_id']) <= 100:
        return None
    action = value.get('action')
    if action in {'accept', 'decline', 'cancel', 'back'}:
        return action, None, None
    if type(value.get('round_no')) is not int or value['round_no'] != duel['round_no']:
        return None
    if action in {'ready', 'start', 'abandon'}:
        return action, value['round_no'], None
    ms = value.get('elapsed_ms')
    if action == 'stop' and type(ms) is int and 0 <= ms <= CONFIG['timer_seconds'] * 1000:
        return action, value['round_no'], ms
    return None
