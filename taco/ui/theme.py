"""T.A.C.O. dark / light theme stylesheets for PyQt6.

Provides QSS strings and a convenience function to apply the active
theme to the entire application.
"""
from PyQt6.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# Dark theme
# ---------------------------------------------------------------------------

DARK_THEME: str = """
/* ---- Global ---- */
QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-family: "Segoe UI", "Cantarell", sans-serif;
    font-size: 10pt;
}

/* ---- Main window / frames ---- */
QMainWindow {
    background-color: #1e1e1e;
}

QFrame {
    background-color: #1e1e1e;
    border: none;
}

/* ---- Menu bar ---- */
QMenuBar {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border-bottom: 1px solid #3c3c3c;
}

QMenuBar::item:selected {
    background-color: #3e3e3e;
}

QMenu {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
}

QMenu::item:selected {
    background-color: #094771;
}

QMenu::separator {
    height: 1px;
    background-color: #3c3c3c;
    margin: 4px 8px;
}

/* ---- Tool bar ---- */
QToolBar {
    background-color: #2d2d2d;
    border: none;
    spacing: 4px;
    padding: 2px;
}

QToolButton {
    background-color: transparent;
    color: #e0e0e0;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 4px;
}

QToolButton:hover {
    background-color: #3e3e3e;
    border: 1px solid #555555;
}

QToolButton:pressed {
    background-color: #094771;
}

/* ---- Status bar ---- */
QStatusBar {
    background-color: #007acc;
    color: #ffffff;
}

/* ---- Tab widget ---- */
QTabWidget::pane {
    border: 1px solid #3c3c3c;
    background-color: #1e1e1e;
}

QTabBar::tab {
    background-color: #2d2d2d;
    color: #969696;
    padding: 6px 14px;
    border: 1px solid #3c3c3c;
    border-bottom: none;
    margin-right: 1px;
}

QTabBar::tab:selected {
    background-color: #1e1e1e;
    color: #e0e0e0;
    border-bottom: 2px solid #007acc;
}

QTabBar::tab:hover:!selected {
    background-color: #353535;
    color: #e0e0e0;
}

/* ---- Text browser / text edit ---- */
QTextBrowser, QTextEdit, QPlainTextEdit {
    background-color: #1e1e1e;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    selection-background-color: #094771;
    selection-color: #e0e0e0;
}

/* ---- Line edit ---- */
QLineEdit {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    border-radius: 2px;
    padding: 4px;
}

QLineEdit:focus {
    border: 1px solid #007acc;
}

/* ---- Combo box ---- */
QComboBox {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    border-radius: 2px;
    padding: 4px 8px;
}

QComboBox:hover {
    border: 1px solid #555555;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    selection-background-color: #094771;
}

/* ---- Spin box ---- */
QSpinBox, QDoubleSpinBox {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    border-radius: 2px;
    padding: 2px 4px;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #007acc;
}

/* ---- Push button ---- */
QPushButton {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    padding: 5px 16px;
    min-width: 60px;
}

QPushButton:hover {
    background-color: #3e3e3e;
    border: 1px solid #555555;
}

QPushButton:pressed {
    background-color: #094771;
}

QPushButton:disabled {
    background-color: #2d2d2d;
    color: #555555;
    border: 1px solid #333333;
}

/* ---- Check box / radio button ---- */
QCheckBox, QRadioButton {
    color: #e0e0e0;
    spacing: 6px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #555555;
    background-color: #2d2d2d;
}

QCheckBox::indicator:checked {
    background-color: #007acc;
    border: 1px solid #007acc;
}

QRadioButton::indicator:checked {
    background-color: #007acc;
    border: 1px solid #007acc;
    border-radius: 7px;
}

/* ---- Group box ---- */
QGroupBox {
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 12px;
    color: #e0e0e0;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #e0e0e0;
}

/* ---- Scroll bar ---- */
QScrollBar:vertical {
    background-color: #1e1e1e;
    width: 12px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #424242;
    min-height: 20px;
    border-radius: 3px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #555555;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: #1e1e1e;
    height: 12px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: #424242;
    min-width: 20px;
    border-radius: 3px;
    margin: 2px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #555555;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ---- Splitter ---- */
QSplitter::handle {
    background-color: #3c3c3c;
}

QSplitter::handle:horizontal {
    width: 2px;
}

QSplitter::handle:vertical {
    height: 2px;
}

/* ---- List / tree / table views ---- */
QListView, QTreeView, QTableView {
    background-color: #1e1e1e;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    alternate-background-color: #252526;
    selection-background-color: #094771;
    selection-color: #e0e0e0;
}

QHeaderView::section {
    background-color: #2d2d2d;
    color: #e0e0e0;
    padding: 4px 8px;
    border: 1px solid #3c3c3c;
}

/* ---- Tooltip ---- */
QToolTip {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    padding: 4px;
}

/* ---- Slider ---- */
QSlider::groove:horizontal {
    background-color: #3c3c3c;
    height: 4px;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background-color: #007acc;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background-color: #1a8ad4;
}

/* ---- Progress bar ---- */
QProgressBar {
    background-color: #2d2d2d;
    border: 1px solid #3c3c3c;
    border-radius: 2px;
    text-align: center;
    color: #e0e0e0;
}

QProgressBar::chunk {
    background-color: #007acc;
    border-radius: 2px;
}

/* ---- Dock widget ---- */
QDockWidget {
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
    color: #e0e0e0;
}

QDockWidget::title {
    background-color: #2d2d2d;
    padding: 4px;
    border: 1px solid #3c3c3c;
}
"""

# ---------------------------------------------------------------------------
# Light theme -- empty string lets Qt use native platform styling
# ---------------------------------------------------------------------------

LIGHT_THEME: str = ""


def apply_theme(app: QApplication, dark_mode: bool) -> None:
    """Apply the dark or light stylesheet to the given QApplication.

    Parameters
    ----------
    app:
        The running QApplication instance.
    dark_mode:
        When ``True`` the dark QSS is applied; otherwise the native
        platform appearance is restored.
    """
    app.setStyleSheet(DARK_THEME if dark_mode else LIGHT_THEME)
