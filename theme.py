"""Loads the WeGoPub design system (direction "Tennis") on every page.

assets/theme.css holds the colour, type and shape tokens plus the base
styling of Streamlit's own widgets. Page styles in assets/*.css only use
those tokens, so changing the look of the whole app means editing one file.
"""

from base64 import b64encode
from functools import cache
from html import escape
from pathlib import Path

import streamlit as st

_ASSETS = Path(__file__).parent / "assets"
_CSS = _ASSETS / "theme.css"


@cache
def icon_url(name: str) -> str:
    """A Phosphor icon from assets/icons (MIT licence) as a data URL for CSS."""
    svg = (_ASSETS / "icons" / f"{name}.svg").read_bytes()
    return "data:image/svg+xml;base64," + b64encode(svg).decode()


def icon_css(selector: str, name: str) -> str:
    """CSS that draws the icon as a mask, so it takes the element's colour."""
    url = icon_url(name)
    return f'{selector}{{-webkit-mask-image:url("{url}");mask-image:url("{url}");}}'


def menu_icons(icons: dict[str, str]) -> None:
    """Icons for rows of a menu list: {button key: icon name}. See .st-key-menu_list_* in theme.css."""
    css = "".join(icon_css(f".stApp .st-key-{key} button::before", icon) for key, icon in icons.items())
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def page_subtitle(*parts: str) -> None:
    """One quiet line under a page title, e.g. lobby · status."""
    st.markdown(f'<p class="page-subtitle">{escape(" · ".join(p for p in parts if p))}</p>', unsafe_allow_html=True)


def button_icons(icons: dict[str, str]) -> None:
    """A Phosphor icon in front of a normal button's label: {button key: icon name}."""
    base = ('content:"";display:inline-block;flex:0 0 20px;width:20px;height:20px;margin-right:6px;background-color:currentColor;'
            '-webkit-mask:none center/contain no-repeat;mask:none center/contain no-repeat;')
    css = "".join(f".stApp .st-key-{key} button::before{{{base}}}" + icon_css(f".stApp .st-key-{key} button::before", icon)
                  for key, icon in icons.items())
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def apply_theme() -> None:
    css = _CSS.read_text(encoding="utf-8")
    css += f':root{{--icon-caret-right:url("{icon_url("caret-right")}");}}'
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def wordmark(name: str = "WeGoPub") -> None:
    """The app name in the display face, in the brand red."""
    st.markdown(f'<p class="wego-wordmark">{escape(name)}</p>', unsafe_allow_html=True)
