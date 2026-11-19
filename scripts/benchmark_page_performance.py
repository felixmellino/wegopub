"""Compare page work without writing data. Use --database for live read timings."""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.models import DrinkEntry
from core.scoring_v1 import replay_season
from core.territories import territory_owner, territory_standings
from core.leaderboard import season_leaderboard


def elapsed(operation):
    start = perf_counter()
    result = operation()
    return result, (perf_counter() - start) * 1000


def benchmark_replay():
    start = datetime(2026, 11, 19, 18, tzinfo=timezone.utc)
    entries = [DrinkEntry(str(i), f'member-{i % 17}', 'benchmark', 'beer', 330,
        'synthetic-photo', None, None, f'area-{i % 24}', 'matched', 2,
        start + timedelta(minutes=i), size='medium', rule_version='v1', event_order=i)
        for i in range(1000)]

    def before():
        return season_leaderboard(entries), [
            (territory_owner(entries, f'area-{i}'), territory_standings(entries, f'area-{i}'))
            for i in range(24)]

    def after():
        snapshot = replay_season(entries)
        return snapshot.season_rows(), [
            (snapshot.owners.get(f'area-{i}'), snapshot.territory_rows(f'area-{i}'))
            for i in range(24)]

    old, old_ms = elapsed(before)
    new, new_ms = elapsed(after)
    assert old == new
    print(f'Leaderboard: 1000 synthetic entries / 24 areas; identical results; {old_ms:.1f} ms -> {new_ms:.1f} ms')


def benchmark_database():
    import data.db as db
    candidates = (db.get_client().table('lobby_memberships')
        .select('id,player_id,lobby_id,lobbies!inner(seasons!inner(id))').limit(1).execute().data)
    if not candidates:
        print('Database comparison skipped: no existing membership with a season.')
        return
    row = candidates[0]
    season_id = row['lobbies']['seasons'][0]['id']

    def before():
        player = db.get_player(row['player_id'])
        members = db.list_memberships_for_player(row['player_id'])
        seasons = db.list_seasons_for_lobby(row['lobby_id'])
        return player, next(m for m in members if m.id == row['id']), next(s for s in seasons if s.id == season_id)

    def after():
        player = db.get_player(row['player_id'])
        member, season = db.membership_context(row['player_id'], row['id'], row['lobby_id'], season_id)
        return player, member, season

    old_times, new_times = [], []
    for _ in range(3):
        old, timing = elapsed(before)
        old_times.append(timing)
        new, timing = elapsed(after)
        new_times.append(timing)
        assert old == new
    print(f'Database bootstrap: 3 warm samples, identical objects; 3 requests -> 2; '
          f'median {median(old_times):.0f} ms -> {median(new_times):.0f} ms')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', action='store_true', help='Make read-only requests using configured Supabase credentials')
    options = parser.parse_args()
    benchmark_replay()
    if options.database:
        benchmark_database()
