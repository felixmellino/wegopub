"""Circular pictures from authorized bytes, with initials as the fallback."""
import base64
from html import escape
import streamlit as st
from httpx import RequestError
from postgrest.exceptions import APIError
from storage3.utils import StorageException
import data.db as db
from core.profile_photo import initials, prepare_profile_photo

PICTURE_ERRORS = (APIError, StorageException, RequestError, RuntimeError, OSError)


def picture_identity(username: str, photo: bytes | None = None, *, size=64):
    if photo:
        source = base64.b64encode(photo).decode('ascii')
        picture = f'<img src="data:image/jpeg;base64,{source}" alt="Profile picture" style="width:100%;height:100%;object-fit:cover;">'
    else:
        picture = escape(initials(username))
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:14px;margin:8px 0 20px">'
        f'<span style="display:flex;align-items:center;justify-content:center;flex-shrink:0;'
        f'width:{size}px;height:{size}px;border-radius:50%;overflow:hidden;background:var(--surface-raised);'
        f'color:var(--text);font-weight:700;font-size:{size // 3}px">{picture}</span>'
        f'<span style="font-weight:600;overflow-wrap:anywhere">{escape(username)}</span></div>',
        unsafe_allow_html=True,
    )


def load_picture(viewer_id, owner_id):
    # Never cache across requests: removing a friend/request must end access.
    return db.download_profile_picture(viewer_id, st.session_state['credential_version'], owner_id)


def show_picture_identity(viewer_id, owner_id, username, *, size=64):
    try:
        photo = load_picture(viewer_id, owner_id)
    except PICTURE_ERRORS:
        photo = None
    picture_identity(username, photo, size=size)


def show_picture_editor(player):
    st.subheader('Profile picture')
    st.caption('Visible to you, your friends and players with a pending friend request. JPEG, PNG or WebP; up to 10 MB and 20 megapixels. Pictures are centre-cropped automatically.')
    if st.session_state.pop('_picture_saved', False):
        st.success('Profile picture saved.')
    if st.session_state.pop('_picture_removed', False):
        st.success('Profile picture removed.')
    version = st.session_state.get('_picture_input_version', 0)
    source = st.radio('Picture source', ['Upload photo', 'Take photo'], horizontal=True, key='pill_radio_picture_source')
    if source == 'Take photo':
        selected = st.camera_input('Take a profile picture', key=f'profile_camera_{version}')
    else:
        selected = st.file_uploader('Choose a picture from your library', type=['jpg', 'jpeg', 'png', 'webp'],
                                    key=f'profile_upload_{version}', max_upload_size=10)
    if selected is not None:
        try:
            prepared = prepare_profile_photo(selected.getvalue())
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.caption('Preview — press Save picture to use this photo.')
            picture_identity(player.display_name, prepared, size=96)
            if st.button('Save picture', type='primary'):
                try:
                    db.save_profile_picture(player.id, st.session_state['credential_version'], selected.getvalue())
                except ValueError as exc:
                    st.error(str(exc))
                except PICTURE_ERRORS:
                    st.error("Your picture couldn't be saved. Please try again later.")
                else:
                    st.session_state['_picture_input_version'] = version + 1
                    st.session_state['_picture_saved'] = True
                    st.rerun()
    try:
        saved = load_picture(player.id, player.id)
    except PICTURE_ERRORS:
        st.info('Saved pictures are unavailable. Please try again later.')
        return
    if saved and st.button('Remove picture'):
        try:
            db.remove_profile_picture(player.id, st.session_state['credential_version'])
        except PICTURE_ERRORS:
            st.error("Your picture couldn't be removed. Please try again.")
        else:
            st.session_state['_picture_input_version'] = version + 1
            st.session_state['_picture_removed'] = True
            st.rerun()
