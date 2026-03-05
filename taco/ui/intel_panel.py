"""Tabbed panel for displaying intel channel output.

Each channel gets its own :class:`IntelTextBrowser` tab.  A permanent
"System" tab is always present for internal application messages.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QTabWidget

from taco.ui.intel_text_browser import IntelTextBrowser


class IntelPanel(QTabWidget):
    """QTabWidget that manages one :class:`IntelTextBrowser` per intel channel.

    Signals
    -------
    system_clicked(str)
        Re-emitted from any child :class:`IntelTextBrowser` when the
        user clicks a system-name link.
    """

    system_clicked = pyqtSignal(str)

    _SYSTEM_TAB_NAME = "System"
    _ALL_TAB_NAME = "All"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(False)
        self.setMovable(True)

        # Map channel name -> (tab index tracking key, browser widget)
        self._channels: dict[str, IntelTextBrowser] = {}
        self._pinned_last: QWidget | None = None  # widget pinned as last tab

        # Create the "All" tab; System is deferred so it appears after channels
        self._add_tab(self._ALL_TAB_NAME, self._ALL_TAB_NAME)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def init_system_tab(self) -> None:
        """Create the System tab and pin it so new channels insert before it.

        Call this after adding the initial user channel tabs so that the
        System tab appears after channels but before any widget appended
        after it (e.g. the Settings tab).
        """
        if self._SYSTEM_TAB_NAME not in self._channels:
            browser = self._add_tab(self._SYSTEM_TAB_NAME, self._SYSTEM_TAB_NAME)
            self._pinned_last = browser

    def pin_last_tab(self, widget: QWidget) -> None:
        """Mark *widget* as the tab that should always stay rightmost.

        New channel tabs will be inserted before this tab.
        """
        self._pinned_last = widget

    def add_channel_tab(self, name: str, short_name: str = "") -> IntelTextBrowser:
        """Add a new channel tab and return its :class:`IntelTextBrowser`.

        If a tab with *name* already exists the existing browser is
        returned without creating a duplicate.

        Parameters
        ----------
        name:
            The full channel name (used as the internal key).
        short_name:
            An optional abbreviated label shown on the tab.  Falls back
            to *name* when empty.

        Returns
        -------
        IntelTextBrowser
            The text browser widget for this channel.
        """
        if name in self._channels:
            return self._channels[name]
        label = short_name if short_name else name
        return self._add_tab(name, label)

    def remove_channel_tab(self, name: str) -> None:
        """Remove the tab identified by *name*.

        The built-in "System" and "All" tabs cannot be removed.
        """
        if name in (self._SYSTEM_TAB_NAME, self._ALL_TAB_NAME):
            return

        browser = self._channels.pop(name, None)
        if browser is not None:
            idx = self.indexOf(browser)
            if idx != -1:
                self.removeTab(idx)
            browser.deleteLater()

    def write_intel(
        self,
        channel: str,
        text: str,
        parse_links: bool = False,
        system_names: Optional[list[str]] = None,
    ) -> None:
        """Append *text* to the browser for *channel*.

        Parameters
        ----------
        channel:
            The channel name.  If no matching tab exists the message
            is silently dropped.
        text:
            The intel line to display.
        parse_links:
            When ``True`` and *system_names* is provided, system names
            in the text are turned into clickable links.
        system_names:
            List of system names to linkify when *parse_links* is
            ``True``.
        """
        browser = self._channels.get(channel)
        if browser is None:
            return
        if parse_links and system_names:
            browser.append_intel(text, system_names=system_names)
        else:
            browser.append_intel(text)

        # Mirror to the "All" tab with a channel prefix
        if channel not in (self._SYSTEM_TAB_NAME, self._ALL_TAB_NAME):
            all_browser = self._channels.get(self._ALL_TAB_NAME)
            if all_browser is not None:
                prefixed = f"[{channel}] {text}"
                if parse_links and system_names:
                    all_browser.append_intel(prefixed, system_names=system_names)
                else:
                    all_browser.append_intel(prefixed)

    def write_system(self, text: str) -> None:
        """Convenience method to write to the built-in System tab."""
        self.write_intel(self._SYSTEM_TAB_NAME, text)

    def get_browser(self, channel: str) -> Optional[IntelTextBrowser]:
        """Return the :class:`IntelTextBrowser` for *channel*, or ``None``."""
        return self._channels.get(channel)

    @property
    def channel_names(self) -> list[str]:
        """Return a list of all channel names (including 'System')."""
        return list(self._channels.keys())

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _add_tab(self, name: str, label: str) -> IntelTextBrowser:
        """Create a new tab with the given internal *name* and visible *label*."""
        browser = IntelTextBrowser(self)
        browser.system_clicked.connect(self.system_clicked.emit)
        self._channels[name] = browser
        # Insert before the pinned-last tab if one exists
        if self._pinned_last is not None:
            pin_idx = self.indexOf(self._pinned_last)
            if pin_idx >= 0:
                self.insertTab(pin_idx, browser, label)
                return browser
        self.addTab(browser, label)
        return browser
