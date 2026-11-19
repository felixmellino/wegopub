"""Server wrapper contracts; the SQL integration suite tests actual rules."""
from unittest.mock import Mock
import pytest
from postgrest.exceptions import APIError
import data.db as db


@pytest.fixture
def client(monkeypatch):
    value=Mock()
    value.rpc.return_value.execute.return_value.data={'id':'saved'}
    monkeypatch.setattr(db,'get_client',lambda:value)
    return value


def test_invite_generates_private_deck_on_server(client):
    assert db.invite_quiz_duel('p','s','d','o',3) == {'id':'saved'}
    name,params=client.rpc.call_args.args
    assert name=='invite_quiz_duel'
    assert params['selected_stake']==3 and len(params['private_questions'])==6
    assert all('correct_index' in q for q in params['private_questions'])


def test_bad_stake_never_calls_database(client):
    with pytest.raises(ValueError):db.invite_quiz_duel('p','s','d','o',True)
    client.rpc.assert_not_called()


def test_answer_sends_choice_not_client_correctness_or_winner(client):
    db.quiz_action('p','d','answer',1,2)
    assert client.rpc.call_args.args == ('quiz_action',dict(actor_player='p',target_duel='d',
        selected_action='answer',expected_round=1,selected_choice=2))


@pytest.mark.parametrize('reason',['quiz_funds','quiz_busy','quiz_reserved_points','quiz_answer_locked'])
def test_friendly_server_rejection(client,reason):
    client.rpc.return_value.execute.side_effect=APIError(dict(code='P0001',message=reason,details='',hint=''))
    with pytest.raises(ValueError):db.quiz_status('p','s')


def test_missing_migration_has_clear_setup_message(client):
    client.rpc.return_value.execute.side_effect=APIError(dict(code='PGRST202',message='missing',details='',hint=''))
    with pytest.raises(RuntimeError,match='016'):db.quiz_status('p','s')


def test_transfers_do_not_hide_unexpected_database_failures(client):
    client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.side_effect=APIError(
        dict(code='XX000',message='failure',details='',hint=''))
    with pytest.raises(APIError):db.list_season_transfers('s')
