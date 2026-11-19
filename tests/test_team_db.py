import base64
from io import BytesIO
from unittest.mock import Mock

import pytest
from PIL import Image
from postgrest.exceptions import APIError

import data.db as db


def test_team_picture_is_sanitized_before_rpc(monkeypatch):
    source=BytesIO()
    image=Image.new('RGB',(700,300),'green')
    exif=Image.Exif()
    exif[270]='Private metadata'
    image.save(source,format='JPEG',exif=exif)
    rpc=Mock()
    monkeypatch.setattr(db,'_team_rpc',rpc)
    db.edit_lobby_team('actor','team','  Tigers  ',source.getvalue())
    method,args=rpc.call_args.args
    assert method=='edit_lobby_team' and args['actor_player']=='actor' and args['new_name']=='Tigers'
    assert args['change_photo'] is True
    with Image.open(BytesIO(base64.b64decode(args['new_photo']))) as cleaned:
        assert cleaned.size==(512,512) and not cleaned.getexif()


def test_invalid_team_picture_never_writes(monkeypatch):
    rpc=Mock()
    monkeypatch.setattr(db,'_team_rpc',rpc)
    with pytest.raises(ValueError):
        db.edit_lobby_team('actor','team','Tigers',b'not a photo')
    rpc.assert_not_called()


def test_nonmember_cannot_load_private_team_pictures(monkeypatch):
    monkeypatch.setattr(db,'list_memberships_for_player',lambda _:[])
    client=Mock()
    monkeypatch.setattr(db,'get_client',client)
    with pytest.raises(PermissionError):
        db.list_lobby_teams('outsider','private-lobby')
    client.assert_not_called()


@pytest.mark.parametrize('reason,code,message',[
    ('team_full','P0001','full'),('team_locked','P0001','locked'),
    ('permission_denied','P0001','Only members'),('duplicate key','23505','already uses')])
def test_team_errors_are_actionable(monkeypatch,reason,code,message):
    client=Mock()
    client.rpc.return_value.execute.side_effect=APIError({'message':reason,'code':code,'details':None,'hint':None})
    monkeypatch.setattr(db,'get_client',lambda:client)
    with pytest.raises(ValueError,match=message):
        db.choose_lobby_team('actor','lobby','team')
