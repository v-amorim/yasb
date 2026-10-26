from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QWidget


def set_tabular(*widgets: QWidget) -> None:
    """Give every digit the same width, so changing numbers never shift the text around them."""
    for widget in widgets:
        font = widget.font()
        font.setFeature(QFont.Tag("tnum"), 1)
        widget.setFont(font)
