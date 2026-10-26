import logging
import os
from functools import partial

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QWidget

from core.validation.widgets.yasb.control_center import FoldersSectionConfig
from core.widgets.services.control_center.sections.quick_actions import ActionButton


class FoldersSectionWidget(QFrame):
    """Grid of folder rows; a click opens the folder and closes the popup."""

    def __init__(self, parent: QWidget, config: FoldersSectionConfig):
        super().__init__(parent)
        self.config = config
        self.setProperty("class", "section folders")

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        columns = max(1, config.columns)
        for column in range(columns):
            grid.setColumnStretch(column, 1)

        for index, item in enumerate(config.items):
            row = ActionButton(self)
            row.setProperty("class", "folder")
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            for text, part_class in ((item.icon, "icon"), (item.title, "label")):
                part = QLabel(text, row)
                part.setProperty("class", part_class)
                row_layout.addWidget(part)
            row_layout.addStretch(1)
            row.clicked.connect(partial(self._open, item.path))
            grid.addWidget(row, index // columns, index % columns)

    def _open(self, path: str) -> None:
        self.window().close()
        target = os.path.expanduser(path)
        if os.path.exists(target):
            os.startfile(target)
        else:
            logging.error("The system cannot find the folder specified: '%s'", target)
