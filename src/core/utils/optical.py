from typing import override

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QFont, QFontInfo, QFontMetricsF
from PyQt6.QtWidgets import QLabel

from core.utils.qobject import is_valid_qobject

_REAPPLY_EVENTS = frozenset(
    {
        QEvent.Type.Polish,
        QEvent.Type.FontChange,
        QEvent.Type.StyleChange,
        QEvent.Type.Resize,
        QEvent.Type.Show,
    }
)


CSS_PIXELS_PER_POINT = 96 / 72
_SPACING_EVENTS = frozenset({QEvent.Type.Polish, QEvent.Type.FontChange, QEvent.Type.StyleChange})


def icon_shift(
    *,
    icon_ascent: float,
    icon_descent: float,
    icon_height: float,
    ink_top: float,
    ink_bottom: float,
    text_ascent: float,
    text_descent: float,
    text_height: float,
    cap_height: float,
) -> float:
    """Pixels to move the icon down (positive) or up (negative) so its ink centre sits on the text's cap midline.

    Both labels are centred on one shared row and draw their line box centred inside their own height.
    ink_top and ink_bottom are the glyph's tight bounds relative to its baseline, y growing downward.
    """
    row_height = max(icon_height, text_height)
    text_top = (row_height - text_height) / 2
    text_baseline = text_top + (text_height - (text_ascent + text_descent)) / 2 + text_ascent
    cap_midline = text_baseline - cap_height / 2

    icon_top = (row_height - icon_height) / 2
    icon_baseline = icon_top + (icon_height - (icon_ascent + icon_descent)) / 2 + icon_ascent
    ink_centre = icon_baseline + (ink_top + ink_bottom) / 2
    return cap_midline - ink_centre


def measure_shift(icon: QLabel, text: QLabel) -> float:
    """The icon_shift of two labels, read from their current fonts. Zero when the icon is not a glyph."""
    glyph = icon.text()
    if not glyph.strip():
        return 0.0
    icon_metrics = QFontMetricsF(icon.font())
    text_metrics = QFontMetricsF(text.font())
    ink = icon_metrics.tightBoundingRect(glyph)
    if ink.isEmpty():
        return 0.0
    cap_height = text_metrics.capHeight() or text_metrics.tightBoundingRect("H").height()
    return icon_shift(
        icon_ascent=icon_metrics.ascent(),
        icon_descent=icon_metrics.descent(),
        icon_height=_content_height(icon),
        ink_top=ink.top(),
        ink_bottom=ink.bottom(),
        text_ascent=text_metrics.ascent(),
        text_descent=text_metrics.descent(),
        text_height=_content_height(text),
        cap_height=cap_height,
    )


def _content_height(label: QLabel) -> float:
    """The label's height without the vertical margins this module adds, or its font height before layout."""
    margins = label.contentsMargins()
    height = label.height() - margins.top() - margins.bottom()
    return float(height) if label.height() > 1 and height > 0 else QFontMetricsF(label.font()).height()


class _OpticalCentering(QObject):
    def __init__(self, icon: QLabel, text: QLabel) -> None:
        super().__init__(icon)
        self._icon = icon
        self._text = text
        self._applying = False
        icon.installEventFilter(self)
        text.installEventFilter(self)

    @override
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        if a1 is not None and a1.type() in _REAPPLY_EVENTS:
            self.apply()
        return False

    def apply(self) -> None:
        if self._applying or not is_valid_qobject(self._text):
            return
        self._applying = True
        try:
            # A margin of 2n pixels on one side moves the centred line by n
            offset = round(measure_shift(self._icon, self._text) * 2)
            margins = self._icon.contentsMargins()
            top, bottom = (offset, 0) if offset > 0 else (0, -offset)
            if margins.top() != top or margins.bottom() != bottom:
                self._icon.setContentsMargins(margins.left(), top, margins.right(), bottom)
        finally:
            self._applying = False

    def detach(self) -> None:
        self._icon.removeEventFilter(self)
        self._text.removeEventFilter(self)
        self.setParent(None)
        self.deleteLater()


def _pixel_size(font: QFont) -> float:
    """The font's size in pixels, from its point size when no platform font has resolved it."""
    for size in (font.pixelSize(), QFontInfo(font).pixelSize()):
        if size > 0:
            return float(size)
    return max(font.pointSizeF(), 0.0) * CSS_PIXELS_PER_POINT


class _CapsSpacing(QObject):
    def __init__(self, label: QLabel, em: float) -> None:
        super().__init__(label)
        self._label = label
        self._em = em
        self._applying = False
        label.installEventFilter(self)

    @override
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        if a1 is not None and a1.type() in _SPACING_EVENTS:
            self.apply()
        return False

    def apply(self) -> None:
        if self._applying:
            return
        self._applying = True
        try:
            font = self._label.font()
            spacing = _pixel_size(font) * self._em
            if font.letterSpacingType() != QFont.SpacingType.AbsoluteSpacing or font.letterSpacing() != spacing:
                font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
                self._label.setFont(font)
        finally:
            self._applying = False


def track_letter_spacing(label: QLabel, em: float = 0.08) -> None:
    """Space the label's letters by a fraction of its current font size, again whenever the font changes."""
    _CapsSpacing(label, em).apply()


def center_icon_on_text(icon: QLabel, text: QLabel) -> None:
    """Keep the icon's ink centred on the text's cap-height midline, measured from both fonts on every change."""
    previous = icon.findChild(_OpticalCentering)
    if previous is not None:
        previous.detach()
    _OpticalCentering(icon, text).apply()
