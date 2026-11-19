"""Camera/library previews stay unsaved until Save picture is pressed."""
from io import BytesIO
from unittest.mock import MagicMock
import pytest
from streamlit.testing.v1 import AppTest
from tests.test_profile_ui import repo, page, click
from tests.test_profile_photo import picture


@pytest.mark.parametrize('source', ['Upload photo', 'Take photo'])
def test_picture_preview_save_new_session_and_remove(repo, monkeypatch, source):
    state = {'photo': None}
    raw = picture()
    def selected(*args, **kwargs):
        return BytesIO(raw) if kwargs['key'].endswith('_0') else None
    monkeypatch.setattr('profile_picture_ui.st.file_uploader', selected)
    monkeypatch.setattr('profile_picture_ui.st.camera_input', selected)
    monkeypatch.setattr('data.db.download_profile_picture', lambda *args: state['photo'])
    def persist(*args):
        from core.profile_photo import prepare_profile_photo
        state['photo'] = prepare_profile_photo(args[-1])
    save = MagicMock(side_effect=persist)
    remove = MagicMock(side_effect=lambda *args: state.update(photo=None))
    monkeypatch.setattr('data.db.save_profile_picture', save)
    monkeypatch.setattr('data.db.remove_profile_picture', remove)
    at = page(repo)
    click(at, 'Edit profile')
    next(r for r in at.radio if r.label == 'Picture source').set_value(source).run()
    assert not at.exception
    assert any('Preview' in c.value for c in at.caption)
    assert any('data:image/jpeg;base64,' in m.value for m in at.markdown)
    save.assert_not_called()
    click(at, 'Save picture')
    save.assert_called_once_with('self', repo['player'].pin_hash, raw)
    assert at.success
    fresh = page(repo)
    assert any('data:image/jpeg;base64,' in m.value for m in fresh.markdown)
    click(fresh, 'Edit profile')
    click(fresh, 'Remove picture')
    remove.assert_called_once()
    assert state['photo'] is None
    assert any('>MI</span>' in m.value for m in fresh.markdown)


def test_invalid_image_cannot_be_saved(repo, monkeypatch):
    monkeypatch.setattr('profile_picture_ui.st.file_uploader', lambda *a, **k: BytesIO(b'invalid'))
    save = MagicMock()
    monkeypatch.setattr('data.db.save_profile_picture', save)
    at = page(repo)
    click(at, 'Edit profile')
    assert at.error
    assert not any(b.label == 'Save picture' for b in at.button)
    save.assert_not_called()


def test_storage_failure_preserves_name_editor_and_initials(repo, monkeypatch):
    def offline(*args):
        raise RuntimeError('offline')
    monkeypatch.setattr('data.db.download_profile_picture', offline)
    at = page(repo)
    click(at, 'Edit profile')
    assert not at.exception
    assert any('Saved pictures are unavailable' in i.value for i in at.info)
    assert any(b.label == 'Save changes' for b in at.button)
    assert any('>MI</span>' in m.value for m in at.markdown)


def test_friends_show_pictures_for_requests_but_not_stranger_search(monkeypatch):
    users = [{'id': 'friend', 'display_name': 'Friend'}, {'id': 'pending', 'display_name': 'Pending'},
             {'id': 'stranger', 'display_name': 'Stranger'}]
    relationships = [{'sender_id': 'self', 'recipient_id': 'friend', 'status': 'accepted'},
                     {'sender_id': 'pending', 'recipient_id': 'self', 'status': 'pending'}]
    monkeypatch.setattr('data.db.list_public_usernames', lambda: users)
    monkeypatch.setattr('data.db.list_friendships', lambda _: relationships)
    download = MagicMock(return_value=picture())
    monkeypatch.setattr('data.db.download_profile_picture', download)
    at = AppTest.from_string("from friends_ui import show_friends\nshow_friends('self')")
    at.session_state['credential_version'] = 'hash'
    at.run()
    assert not at.exception
    download.assert_not_called()  # Overview cards do not load private pictures.
    click(at, 'Current Friends · 1')
    assert {call.args[2] for call in download.call_args_list} == {'friend'}
    click(at, 'Close')
    click(at, 'Incoming requests · 1')
    assert {call.args[2] for call in download.call_args_list} == {'friend', 'pending'}
    click(at, 'Close')
    click(at, 'Find players')
    at.text_input[0].input('stranger').run()
    assert not at.exception
    assert all(call.args[2] != 'stranger' for call in download.call_args_list)
    assert any('>ST</span>' in m.value for m in at.markdown)
