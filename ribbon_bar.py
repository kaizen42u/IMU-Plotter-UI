"""Classic ribbon bar — tabbed strip of named control groups."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

_RIBBON_BG      = "#2D2D2D"
_GROUP_BG       = "#333333"
_GROUP_BORDER   = "#505050"
_TAB_ACTIVE_BG  = "#3C3C3C"
_TAB_HOVER_BG   = "#404040"
_TAB_TEXT       = "#CCCCCC"
_GROUP_TITLE    = "#888888"

_TAB_BAR_STYLE = f"""
QTabBar {{
    background: {_RIBBON_BG};
    border-bottom: 1px solid {_GROUP_BORDER};
}}
QTabBar::tab {{
    background: {_RIBBON_BG};
    color: {_TAB_TEXT};
    padding: 3px 14px;
    border: 1px solid transparent;
    border-bottom: none;
    font-size: 9pt;
    margin-right: 1px;
}}
QTabBar::tab:selected {{
    background: {_TAB_ACTIVE_BG};
    border-color: {_GROUP_BORDER};
    border-bottom-color: {_TAB_ACTIVE_BG};
}}
QTabBar::tab:hover:!selected {{
    background: {_TAB_HOVER_BG};
}}
"""

_RIBBON_PANEL_STYLE = f"""
QWidget#ribbon_panel {{
    background: {_RIBBON_BG};
    border-bottom: 1px solid {_GROUP_BORDER};
}}
"""


class RibbonGroup(QFrame):
    """A bordered, labelled group of controls inside a ribbon tab.

    Usage::

        group = tab.add_group("COM Port")
        row = group.add_row()
        row.addWidget(port_combo)
        row.addWidget(baud_combo)
        row = group.add_row()
        row.addWidget(connect_btn)
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            RibbonGroup {{
                background: {_GROUP_BG};
                border: 1px solid {_GROUP_BORDER};
                border-radius: 3px;
            }}
            QLabel#group_title {{
                color: {_GROUP_TITLE};
                font-size: 8pt;
                border: none;
                background: transparent;
                padding: 0;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 2)
        root.setSpacing(2)

        # Controls area
        self._body = QVBoxLayout()
        self._body.setSpacing(3)
        self._body.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._body)

        # Group title pinned to bottom
        lbl = QLabel(title)
        lbl.setObjectName("group_title")
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(lbl)

    def add_row(self) -> QHBoxLayout:
        """Append a horizontal row and return its layout for adding widgets."""
        row = QHBoxLayout()
        row.setSpacing(4)
        row.setContentsMargins(0, 0, 0, 0)
        self._body.addLayout(row)
        return row

    def add_widget(self, w: QWidget) -> None:
        """Add a single widget occupying a full row."""
        self._body.addWidget(w)


class RibbonTab(QWidget):
    """Horizontal strip of RibbonGroups, shown when the matching tab is active."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ribbon_panel")
        self.setStyleSheet(_RIBBON_PANEL_STYLE)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 4, 6, 4)
        self._layout.setSpacing(6)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def add_group(self, title: str) -> RibbonGroup:
        """Append a named group and return it."""
        group = RibbonGroup(title, self)
        self._layout.addWidget(group)
        return group

    def add_stretch(self) -> None:
        self._layout.addStretch()


class RibbonBar(QWidget):
    """Tabbed ribbon bar.

    Usage::

        ribbon = RibbonBar(parent=self)
        tab = ribbon.add_tab("Home")
        grp = tab.add_group("COM Port")
        ...
    """

    # Height budget: tab bar ≈ 22 px + content ≈ 60 px = 82 px
    TAB_CONTENT_HEIGHT = 60

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tab_bar = QTabBar()
        self._tab_bar.setStyleSheet(_TAB_BAR_STYLE)
        self._tab_bar.setExpanding(False)
        root.addWidget(self._tab_bar)

        self._stack = QStackedWidget()
        self._stack.setFixedHeight(self.TAB_CONTENT_HEIGHT)
        root.addWidget(self._stack)

        self._tab_bar.currentChanged.connect(self._stack.setCurrentIndex)

        # Separator line below the whole ribbon
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {_GROUP_BORDER};")
        root.addWidget(line)

    def add_tab(self, title: str) -> RibbonTab:
        """Append a new tab and return its :class:`RibbonTab` panel."""
        tab = RibbonTab(self)
        self._stack.addWidget(tab)
        self._tab_bar.addTab(title)
        return tab
