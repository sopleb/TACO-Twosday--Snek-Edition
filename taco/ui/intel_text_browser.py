"""Custom QTextBrowser that makes system names clickable.

System names are rendered as internal hyperlinks.  When clicked they
emit the :pyqt:`system_clicked` signal so that the map view can
centre on or highlight the named system.
"""
from __future__ import annotations

import html
import re
from typing import Optional

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QTextBrowser


# Internal URL scheme used to distinguish system-name links from real URLs.
_SYSTEM_SCHEME = "taco-system"


class IntelTextBrowser(QTextBrowser):
    """QTextBrowser subclass that turns known system names into clickable links.

    Signals
    -------
    system_clicked(str)
        Emitted when the user clicks a system-name hyperlink.  The
        payload is the system name exactly as stored in the universe
        data.
    """

    system_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._on_anchor_clicked)

        # Limit scroll-back so memory usage stays bounded
        self.document().setMaximumBlockCount(2000)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append_intel(self, text: str, system_names: Optional[list[str]] = None) -> None:
        """Append a line of intel text, optionally hyperlinking system names.

        Parameters
        ----------
        text:
            The raw intel text to display.
        system_names:
            An optional list of system names that appear in *text*.
            Each occurrence is wrapped in an ``<a>`` tag pointing to
            ``taco-system://<name>`` so that it becomes clickable.
            If *None* or empty, the text is appended as-is (HTML
            escaped).
        """
        if system_names:
            html_line = self._linkify(text, system_names)
        else:
            html_line = html.escape(text)

        # Highlight alert lines
        if "** ALERT:" in text and text.rstrip().endswith("**"):
            html_line = f'<span style="color:#ff6060; font-weight:bold;">{html_line}</span>'
        else:
            # Wrap in <span> so Qt always parses as HTML (plain text
            # would double-escape entities like &gt;)
            html_line = f"<span>{html_line}</span>"

        self.append(html_line)
        self._scroll_to_bottom()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _linkify(text: str, system_names: list[str]) -> str:
        """Return *text* as HTML with each system name wrapped in an <a> tag.

        The replacement is case-insensitive and respects word boundaries
        so that substrings of longer words are not accidentally linked.
        """
        escaped = html.escape(text)

        # Sort longest-first so that e.g. "N-RAEL" is matched before "N-R"
        sorted_names = sorted(system_names, key=len, reverse=True)

        for name in sorted_names:
            # Build a pattern that matches the (already HTML-escaped) name
            escaped_name = html.escape(name)
            pattern = re.compile(
                r"\b" + re.escape(escaped_name) + r"\b",
                re.IGNORECASE,
            )
            link = (
                f'<a href="{_SYSTEM_SCHEME}://{escaped_name}" '
                f'style="color:#4ec9b0; text-decoration:underline;">'
                f"{escaped_name}</a>"
            )
            escaped = pattern.sub(link, escaped)

        return escaped

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """Handle clicks on hyperlinks embedded in the text."""
        if url.scheme() == _SYSTEM_SCHEME:
            system_name = url.host()
            if system_name:
                self.system_clicked.emit(system_name)
        else:
            # External URL -- open in the default browser
            QDesktopServices.openUrl(url)

    def _scroll_to_bottom(self) -> None:
        """Ensure the view is scrolled to the most recent line."""
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
