from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from core.utils.floating_popup import PopupThread


def test_thread_colour_comes_from_the_stylesheet(qapp: QApplication) -> None:
    thread = PopupThread()
    thread.setStyleSheet(".popup-thread { qproperty-threadcolor: #ff0000; }")

    thread.ensurePolished()

    assert thread.get_color() == QColor("#ff0000")
