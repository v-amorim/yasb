"""The calendar's date column is as wide as its widest child, so no empty band sits beside the date."""

from PyQt6.QtWidgets import QLabel

from tests.widgets.test_card_inset import Card

COLUMN_CLASSES = ("day-label", "month-label", "date-label")


def _column(card: Card) -> list[QLabel]:
    labels = [
        label
        for label in card[0].findChildren(QLabel)
        if label.isVisible() and str(label.property("class")) in COLUMN_CLASSES
    ]
    assert {str(label.property("class")) for label in labels} == set(COLUMN_CLASSES)
    return labels


def test_calendar_fit_column_is_its_widest_child(calendar: Card):
    labels = _column(calendar)
    widest = max(label.sizeHint().width() for label in labels)
    assert all(abs(label.width() - widest) <= 1 for label in labels), [(label.width(), widest) for label in labels]


def test_calendar_fit_column_is_one_gap_from_the_grid(calendar: Card):
    card = calendar[0]
    label = _column(calendar)[0]
    grid = card.layout().itemAt(1).widget()
    column_right = label.mapTo(card, label.rect().topLeft()).x() + label.width()
    assert grid.mapTo(card, grid.rect().topLeft()).x() - column_right == 8
