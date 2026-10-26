# pyright: reportPrivateUsage=false

from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest
from pydantic import ValidationError
from PyQt6.QtCore import QEvent, QEventLoop, QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QContextMenuEvent, QImage
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QWidget

from core import bar_helper, bar_motion
from core.bar import Bar
from core.bar_helper import AppBarManager
from core.utils.utilities import PopupWidget
from core.utils.win32 import app_bar
from core.validation.bar import BarConfig, BarWindowFlags
from core.widgets.base import BaseWidget

type MakeBar = Callable[..., Bar]


class _FakeAppBar:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.reserve_space: list[bool] = []

    def create_appbar(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append("create")
        self.reserve_space.append(args[6])

    def remove_appbar(self) -> None:
        self.calls.append("remove")


def _wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture
def registered_bars(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    registered: list[int] = []

    def register_bar(self: AppBarManager, hwnd: int, bar_widget: Bar) -> None:
        registered.append(hwnd)

    def unregister_bar(self: AppBarManager, hwnd: int) -> None:
        pass

    monkeypatch.setattr(AppBarManager, "register_bar", register_bar)
    monkeypatch.setattr(AppBarManager, "unregister_bar", unregister_bar)
    return registered


@pytest.fixture
def make_bar(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, registered_bars: list[int]) -> Iterator[MakeBar]:
    monkeypatch.setattr(app_bar, "Win32AppBar", _FakeAppBar)
    bars: list[Bar] = []

    def make(widgets: dict[str, list[QWidget]] | None = None, **config: Any) -> Bar:
        screen = QApplication.primaryScreen()
        assert screen is not None
        bar = Bar(
            bar_id="test-bar",
            bar_name="test-bar",
            bar_screen=screen,
            stylesheet="",
            widgets=cast(dict[str, list[BaseWidget]], {"left": [], "center": [], "right": [], **(widgets or {})}),
            config=BarConfig.model_validate(config),
            init=True,
        )
        bars.append(bar)
        return bar

    yield make
    for bar in bars:
        bar.skip_animation = True
        bar.close()


# One entry per option that switches on its own code path, plus a few realistic combinations.
BAR_CONFIGS: dict[str, dict[str, Any]] = {
    "defaults": {},
    "bottom": {"alignment": {"position": "bottom"}},
    "align-left": {"alignment": {"align": "left"}},
    "align-right": {"alignment": {"align": "right"}},
    "padding": {"padding": {"top": 4, "left": 8, "bottom": 4, "right": 8}},
    "adaptive": {"style": "adaptive"},
    "adaptive-bottom": {"style": "adaptive", "alignment": {"position": "bottom"}},
    "width-auto": {"dimensions": {"width": "auto"}},
    "width-pixels": {"dimensions": {"width": 600, "height": 40}},
    "width-percent": {"dimensions": {"width": "50%"}},
    "no-animation": {"animation": {"enabled": False}},
    "fade-animation": {"animation": {"type": "fade"}},
    "blur": {"blur_effect": {"enabled": True, "round_corners": True}},
    "always-on-top": {"window_flags": {"always_on_top": True}},
    "windows-app-bar": {"window_flags": {"windows_app_bar": True}},
    "hide-on-fullscreen": {"window_flags": {"always_on_top": True, "hide_on_fullscreen": True}},
    "hide-on-maximized": {"window_flags": {"hide_on_maximized": True}},
    "auto-hide": {"window_flags": {"auto_hide": True}},
    "auto-hide-zone": {"window_flags": {"auto_hide": True, "auto_hide_zone": "45%-55%", "auto_hide_show_delay": 100}},
    "auto-hide-peek": {
        "dimensions": {"width": "auto"},
        "window_flags": {"auto_hide": True, "auto_hide_peek": ["clock"], "auto_hide_peek_height": 24},
    },
    "no-context-menu": {"context_menu": False},
    "no-stretch": {"layouts": {"left": {"stretch": False}, "center": {"stretch": False}, "right": {"stretch": False}}},
    "auto-hide-bottom-slide": {
        "alignment": {"position": "bottom"},
        "animation": {"type": "slide"},
        "window_flags": {"auto_hide": True, "always_on_top": True},
    },
    "app-bar-auto-width-adaptive": {
        "style": "adaptive",
        "dimensions": {"width": "auto"},
        "window_flags": {"windows_app_bar": True, "always_on_top": True, "hide_on_fullscreen": True},
    },
}


@pytest.mark.parametrize("config", BAR_CONFIGS.values(), ids=BAR_CONFIGS.keys())
def test_bar_lifecycle(make_bar: MakeBar, config: dict[str, Any]):
    bar = make_bar(**config)
    assert bar.isVisible()
    assert cast(_FakeAppBar, bar.app_bar_manager).calls[0] == "create"

    bar.position_bar()
    bar.show()
    assert bar.isVisible()

    bar.skip_animation = True
    bar.hide()
    assert not bar.isVisible()


@pytest.mark.parametrize("position", ["top", "bottom"])
def test_bar_sits_at_its_screen_edge(make_bar: MakeBar, position: str):
    padding = {"top": 3, "left": 0, "bottom": 5, "right": 0}
    bar = make_bar(alignment={"position": position}, padding=padding, animation={"enabled": False})
    screen = bar.target_screen.geometry()

    if position == "top":
        assert bar.y() == screen.top() + padding["top"]
    else:
        assert bar.geometry().bottom() == screen.bottom() - padding["bottom"]


def test_auto_hide_sets_up_its_manager(make_bar: MakeBar):
    bar = make_bar(window_flags={"auto_hide": True})

    assert bar.autohide_manager is not None
    assert bar.autohide_manager.is_enabled()


def test_hide_on_maximized_starts_the_watcher(make_bar: MakeBar):
    bar = make_bar(window_flags={"hide_on_maximized": True})

    assert bar._maximized_watcher is not None


def test_auto_width_uses_its_manager(make_bar: MakeBar):
    bar = make_bar(dimensions={"width": "auto"})

    assert bar._auto_width_manager is not None
    bar._auto_width_manager.sync()


@pytest.mark.parametrize(
    "window_flags, registered",
    [
        ({}, False),
        ({"windows_app_bar": True}, True),
        ({"always_on_top": True, "hide_on_fullscreen": True}, True),
    ],
)
def test_app_bar_registration(
    make_bar: MakeBar, registered_bars: list[int], window_flags: dict[str, bool], registered: bool
):
    make_bar(window_flags=window_flags)

    assert bool(registered_bars) == registered


@pytest.mark.parametrize(
    ("window_flags", "calls"),
    [
        ({"auto_hide": True}, ["create", "remove"]),
        ({"auto_hide": True, "always_on_top": True, "hide_on_fullscreen": True}, ["create"]),
        ({"auto_hide": True, "always_on_top": True, "hide_on_fullscreen": True, "windows_app_bar": True}, ["create"]),
    ],
)
def test_auto_hide_keeps_the_app_bar_only_for_fullscreen_notices(
    make_bar: MakeBar, window_flags: dict[str, bool], calls: list[str]
):
    fake = cast(_FakeAppBar, make_bar(window_flags=window_flags).app_bar_manager)

    assert fake.calls == calls
    assert fake.reserve_space == [False]


@pytest.mark.parametrize("animation_type", ["slide", "fade"])
def test_animations_run_to_completion(make_bar: MakeBar, animation_type: str):
    bar = make_bar(animation={"enabled": True, "type": animation_type, "duration": 20})
    _wait(80)

    bar.hide()
    _wait(120)
    assert not bar.isVisible()

    bar.show_bar()
    _wait(120)
    assert bar.isVisible()


@pytest.mark.parametrize("enabled", [True, False])
def test_context_menu(make_bar: MakeBar, enabled: bool):
    bar = make_bar(context_menu=enabled, animation={"enabled": False})
    point = QPoint(5, 5)

    bar.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, bar.mapToGlobal(point)))
    menus = bar.findChildren(QMenu)

    if not enabled:
        assert menus == []
        return
    assert len(menus) >= 1
    texts = [action.text() for action in menus[0].actions() if action.text()]
    assert texts[0] == "Bar: test-bar"
    assert {"Task Manager", "Take Screenshot", "Enable Auto Hide", "Reload Bar", "Exit"} <= set(texts)
    menus[0].close()


@pytest.mark.parametrize(("on_right", "opens"), [("do_nothing", True), ("default", False), ("toggle_label", False)])
def test_context_menu_over_a_widget_opens_only_when_its_right_click_does_nothing(
    make_bar: MakeBar, on_right: str, opens: bool
):
    widget = BaseWidget()
    widget.setFixedSize(60, 20)
    widget.callback_right = on_right
    bar = make_bar(widgets={"left": [widget]}, context_menu=True, animation={"enabled": False})
    bar.show()
    QApplication.processEvents()
    point = widget.mapTo(bar, QPoint(10, 10))
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(10, 10), widget.mapToGlobal(QPoint(10, 10)))

    widget.contextMenuEvent(event)
    assert event.isAccepted() != opens
    bar.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, bar.mapToGlobal(point)))
    menus = bar.findChildren(QMenu)

    assert bool(menus) == opens
    for menu in menus:
        menu.close()


# Timing tests keep their bar in a corner, where a real cursor is unlikely to send Enter or Leave mid-test.
_OUT_OF_THE_WAY = {"position": "bottom", "align": "left"}


def _named_widget(name: str) -> QLabel:
    label = QLabel(name)
    setattr(label, "widget_name", name)
    return label


class _CursorAt:
    """Stands in for QCursor so a Leave event never lands in the auto-hide safe zone."""

    def __init__(self, point: QPoint) -> None:
        self.point = point

    def pos(self) -> QPoint:
        return self.point


@pytest.mark.parametrize("zone", ["45%-55%", "0%-100%", " 10% - 20% "])
def test_auto_hide_zone_accepts_a_range(zone: str):
    assert BarWindowFlags.model_validate({"auto_hide_zone": zone}).auto_hide_zone == zone


@pytest.mark.parametrize("zone", ["55%-45%", "50%", "0%-120%", "a-b", "40%-40%"])
def test_auto_hide_zone_rejects_a_bad_range(zone: str):
    with pytest.raises(ValidationError):
        BarWindowFlags.model_validate({"auto_hide_zone": zone})


def test_auto_hide_zone_covers_its_band(make_bar: MakeBar):
    bar = make_bar(window_flags={"auto_hide": True, "auto_hide_zone": "45%-55%"}, animation={"enabled": False})
    assert bar.autohide_manager is not None
    bar.autohide_manager.setup_detection_zone()
    screen = bar.target_screen.geometry()

    zone = bar.autohide_manager._detection_zone
    assert zone is not None
    assert zone.x() == screen.x() + round(screen.width() * 0.45)
    assert zone.width() == round(screen.width() * 0.10)


def test_auto_hide_show_delay_waits_on_the_zone(make_bar: MakeBar):
    bar = make_bar(
        alignment=_OUT_OF_THE_WAY,
        animation={"enabled": False},
        window_flags={"auto_hide": True, "auto_hide_show_delay": 60, "auto_hide_zone": "0%-1%"},
    )
    manager = bar.autohide_manager
    assert manager is not None
    manager.setup_detection_zone()
    manager.hide_bar()
    assert not bar.isVisible()

    manager.request_show()
    manager.cancel_show()
    _wait(100)
    assert not bar.isVisible()

    manager.request_show()
    _wait(100)
    assert bar.isVisible()


def test_auto_hide_stays_down_behind_a_fullscreen_app(make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch):
    bar = make_bar(
        alignment=_OUT_OF_THE_WAY,
        animation={"enabled": False},
        window_flags={"auto_hide": True, "always_on_top": True, "hide_on_fullscreen": True, "auto_hide_zone": "0%-1%"},
    )
    manager = bar.autohide_manager
    assert manager is not None
    manager.setup_detection_zone()
    manager.hide_bar()
    intended = AppBarManager()._bar_intended_state

    monkeypatch.setitem(intended, int(bar.winId()), False)
    manager.request_show()
    assert not bar.isVisible()

    monkeypatch.setitem(intended, int(bar.winId()), True)
    manager.request_show()
    assert bar.isVisible()


def test_auto_hide_peek_collapses_and_grows(make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch):
    clock, weather, muted = _named_widget("clock"), _named_widget("weather"), _named_widget("volume")
    bar = make_bar(
        widgets={"center": [clock, weather, muted]},
        alignment=_OUT_OF_THE_WAY,
        dimensions={"width": "auto", "height": 34},
        animation={"enabled": False},
        window_flags={
            "auto_hide": True,
            "auto_hide_peek": ["clock"],
            "auto_hide_peek_height": 24,
            "auto_hide_show_delay": 60,
            "auto_hide_hide_delay": 30,
        },
    )
    monkeypatch.setattr(bar_helper, "QCursor", _CursorAt(bar.geometry().center() + QPoint(0, 200)))
    manager = bar.autohide_manager
    assert manager is not None
    muted.hide()  # switched off from the context menu before the bar collapses
    _wait(20)  # auto width settles on the next event loop turn
    full_width = bar.width()

    manager.hide_bar()
    _wait(20)
    assert bar.isVisible()
    assert manager.is_peeking()
    assert not weather.isVisible() and clock.isVisible()
    assert bar.height() == 24 and bar.width() < full_width
    assert "peek" in str(bar.bar_frame.property("class")).split()

    QApplication.sendEvent(bar, QEvent(QEvent.Type.Enter))
    QApplication.sendEvent(bar, QEvent(QEvent.Type.Leave))
    _wait(100)
    assert manager.is_peeking(), "passing over the bar must not grow it"

    QApplication.sendEvent(bar, QEvent(QEvent.Type.Enter))
    _wait(100)
    assert not manager.is_peeking()
    assert weather.isVisible() and muted.isHidden()
    assert bar.height() == 34
    assert "peek" not in str(bar.bar_frame.property("class")).split()

    QApplication.sendEvent(bar, QEvent(QEvent.Type.Leave))
    _wait(100)
    assert manager.is_peeking()

    manager.cleanup()
    assert weather.isVisible() and bar.height() == 34


def test_widgets_shown_in_both_states_take_the_padding_of_the_state_the_bar_is_in(make_bar: MakeBar):
    clock = _named_widget("clock")
    clock.setProperty("class", "stays")
    bar = make_bar(
        widgets={"left": [_named_widget("a")], "center": [clock]},
        alignment=_OUT_OF_THE_WAY,
        dimensions={"width": "auto", "height": 34},
        animation={"enabled": False},
        window_flags={"auto_hide": True, "auto_hide_peek": ["clock"], "auto_hide_peek_height": 24},
    )
    bar.setStyleSheet(".stays { padding: 0 9px; } .peek .stays { padding: 0 3px; }")
    manager = bar.autohide_manager
    assert manager is not None
    _wait(20)
    full = clock.sizeHint().width()

    manager.collapse(animate=False)
    _wait(20)
    assert clock.sizeHint().width() < full

    manager.expand(animate=False)
    _wait(20)
    assert clock.sizeHint().width() == full


_CENTERED = {"position": "bottom", "align": "center"}


def _x_center(widget: QWidget) -> int:
    return widget.mapToGlobal(widget.rect().center()).x()


@pytest.mark.parametrize("balanced", [True, False])
def test_balanced_layouts_keep_the_center_mid_bar(make_bar: MakeBar, balanced: bool):
    bar = make_bar(
        widgets={
            "left": [_named_widget("a much wider left side")],
            "center": [_named_widget("clock")],
            "right": [_named_widget("r")],
        },
        alignment=_CENTERED,
        dimensions={"width": "auto"},
        animation={"enabled": False},
        layouts={"balanced": balanced},
    )
    _wait(20)

    assert (abs(_x_center(bar._section_frames["center"]) - _x_center(bar)) <= 1) == balanced


def test_balanced_peek_keeps_the_clock_where_it_was(make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch):
    clock, left, right = _named_widget("clock"), _named_widget("power and home menu"), _named_widget("tray")
    bar = make_bar(
        widgets={"left": [left], "center": [clock], "right": [right]},
        alignment=_CENTERED,
        dimensions={"width": "auto", "height": 34},
        animation={"enabled": False},
        layouts={"balanced": True},
        window_flags={"auto_hide": True, "auto_hide_peek": ["clock"], "auto_hide_hide_delay": 30},
    )
    monkeypatch.setattr(bar_helper, "QCursor", _CursorAt(bar.geometry().center() + QPoint(0, 200)))
    manager = bar.autohide_manager
    assert manager is not None
    _wait(20)
    expanded = _x_center(clock)

    manager.hide_bar()
    _wait(20)

    assert manager.is_peeking() and not left.isVisible()
    assert abs(_x_center(clock) - expanded) <= 1


def test_below_widgets_hang_by_the_center_only_while_the_bar_is_full(
    make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch
):
    clock, tray, dots = _named_widget("clock"), _named_widget("tray"), _named_widget("dots")
    bar = make_bar(
        widgets={"center": [clock], "right": [tray], "below": [dots]},
        alignment=_CENTERED,
        dimensions={"width": "auto", "height": 34},
        animation={"enabled": False},
        layouts={"balanced": True},
        window_flags={"auto_hide": True, "auto_hide_peek": ["clock"], "auto_hide_hide_delay": 30},
    )
    monkeypatch.setattr(bar_helper, "QCursor", _CursorAt(bar.geometry().center() + QPoint(0, 200)))
    manager, strip = bar.autohide_manager, bar._below_strip
    assert manager is not None and strip is not None
    _wait(20)

    assert strip.isVisible() and dots.isVisible()
    assert abs(_x_center(strip) - _x_center(clock)) <= 1
    assert strip.geometry().bottom() < bar.geometry().top(), "a bottom bar hangs the strip above itself"
    assert strip.windowFlags() & Qt.WindowType.WindowTransparentForInput

    manager.hide_bar()
    _wait(20)
    assert manager.is_peeking() and not strip.isVisible()

    QApplication.sendEvent(bar, QEvent(QEvent.Type.Enter))
    _wait(20)
    assert not manager.is_peeking() and strip.isVisible()

    bar.close()
    assert not strip.isVisible()


def test_bar_widens_to_an_open_popup_and_returns_on_close(make_bar: MakeBar):
    clock, tray = _named_widget("clock"), _named_widget("tray")
    bar = make_bar(
        widgets={"left": [_named_widget("levels")], "center": [clock], "right": [tray]},
        alignment=_CENTERED,
        dimensions={"width": "auto", "height": 34},
        animation={"enabled": False},
        layouts={"balanced": True},
    )
    _wait(20)
    resting_width, clock_x = bar.width(), _x_center(clock)
    popup = PopupWidget(tray, bar_anchored=True)
    popup.setFixedSize(resting_width + 120, 60)
    popup.setPosition(alignment="center")

    popup.show()
    _wait(20)

    assert bar.width() == popup.width() == bar.bar_frame.width()
    assert bar.x() == popup.x()
    assert abs(_x_center(clock) - clock_x) <= 1

    popup.hide()
    _wait(20)

    assert bar.width() == resting_width
    assert abs(_x_center(clock) - clock_x) <= 1


def test_bar_keeps_its_width_for_a_narrower_popup(make_bar: MakeBar):
    tray = _named_widget("tray")
    bar = make_bar(
        widgets={"center": [_named_widget("clock")], "right": [tray]},
        alignment=_CENTERED,
        dimensions={"width": "auto", "height": 34},
        animation={"enabled": False},
    )
    _wait(20)
    resting_width = bar.width()
    popup = PopupWidget(tray, bar_anchored=True)
    popup.resize(resting_width - 40, 60)
    popup.setPosition(alignment="center")

    popup.show()
    _wait(20)

    assert bar.width() == resting_width
    assert popup.width() == resting_width
    popup.hide()


def _reference_bezier(x1: float, y1: float, x2: float, y2: float, x: float) -> float:
    """CSS cubic-bezier(x1, y1, x2, y2) at progress x, by bisection on the curve parameter."""

    def point(s: float, a: float, b: float) -> float:
        return 3 * (1 - s) ** 2 * s * a + 3 * (1 - s) * s**2 * b + s**3

    low, high = 0.0, 1.0
    for _ in range(60):
        mid = (low + high) / 2
        low, high = (mid, high) if point(mid, x1, x2) < x else (low, mid)
    return point((low + high) / 2, y1, y2)


@pytest.mark.parametrize("curve", [bar_motion.EXPAND.width.curve, bar_motion.EXPAND.height.curve])
def test_motion_curves_match_css_cubic_bezier(curve: bar_motion.Bezier):
    easing = bar_motion.cubic_bezier(*curve)

    for step in range(1, 20):
        x = step / 20
        assert easing.valueForProgress(x) == pytest.approx(_reference_bezier(*curve, x), abs=2e-3)


def test_motion_timings_are_the_picked_ones():
    ease = (0.2, 0.0, 0.0, 1.0)
    even = (0.4, 0.0, 0.2, 1.0)

    assert bar_motion.EXPAND == bar_motion.Timing(
        width=bar_motion.Track(250, (0.34, 1.2, 0.64, 1.0)),
        height=bar_motion.Track(190, ease),
        text=bar_motion.Track(250, even),
        pills=bar_motion.Track(110, ease, delay=120),
    )
    assert bar_motion.COLLAPSE == bar_motion.Timing(
        width=bar_motion.Track(260, ease),
        height=bar_motion.Track(260, ease),
        text=bar_motion.Track(260, even),
        pills=bar_motion.Track(120, ease),
    )


_TOP_CENTER = {"position": "top", "align": "center"}


def _motion_bar(
    make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch, center: tuple[str, ...] = ("clock",), **config: Any
) -> Bar:
    monkeypatch.setattr(bar_motion, "animations_enabled", lambda: True)
    bar = make_bar(
        widgets={
            "left": [_named_widget("levels")],
            "center": [_named_widget(name) for name in center],
            "right": [_named_widget("tray")],
        },
        alignment=_TOP_CENTER,
        dimensions={"width": "auto", "height": 40},
        layouts={"balanced": True},
        **{
            "animation": {"enabled": True, "duration": 10},
            "window_flags": {
                "auto_hide": True,
                "auto_hide_peek": list(center),
                "auto_hide_peek_height": 22,
                "auto_hide_show_delay": 60,
                "auto_hide_hide_delay": 600_000,
            },
            **config,
        },
    )
    monkeypatch.setattr(bar_helper, "QCursor", _CursorAt(bar.geometry().center() + QPoint(0, 300)))
    _wait(100)
    return bar


def _play(motion: bar_motion.BarMotion, until: float | None = None) -> list[bar_motion.Look]:
    """Drive the running motion by hand at 60 fps, up to `until` ms or to its end."""
    motion._timer.stop()
    looks: list[bar_motion.Look] = []
    elapsed = 0.0
    while motion.active and not motion._landed and (until is None or elapsed <= until):
        motion.seek(min(elapsed, motion._total))
        looks.append(motion._look)
        elapsed += 1000 / 60
    if motion._landed:
        motion.finish()
    return looks


def _frame_rect(bar: Bar) -> QRect:
    return bar.bar_frame.geometry()


def test_motion_ends_on_the_geometry_of_the_instant_path(make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch):
    reference = _motion_bar(make_bar, monkeypatch)
    ref_manager = reference.autohide_manager
    assert ref_manager is not None
    initial = reference.geometry()
    ref_manager.collapse(animate=False)
    _wait(30)
    peek_window, peek_frame = reference.geometry(), _frame_rect(reference)
    ref_manager.expand(animate=False)
    _wait(30)
    full_window, full_frame = reference.geometry(), _frame_rect(reference)
    reference.skip_animation = True
    reference.hide()

    bar = _motion_bar(make_bar, monkeypatch)
    manager = bar.autohide_manager
    assert manager is not None
    motion = manager._motion
    assert bar.geometry() == initial
    assert peek_window.height() == 22 and peek_window.width() < full_window.width()

    manager.collapse()
    assert motion.active and manager.is_peeking()
    looks = _play(motion)

    assert not motion.active
    assert bar.geometry() == peek_window and _frame_rect(bar) == peek_frame
    _wait(30)
    assert bar.geometry() == peek_window, "nothing moves after the motion ends"
    assert "peek" in str(bar.bar_frame.property("class")).split()
    assert all(bar._section_frames[name].isVisible() for name in ("left", "center", "right"))
    assert bar.widgets["center"][0].isVisible() and not bar.widgets["left"][0].isVisible()
    assert looks[0].width == initial.width()
    assert looks[-1].width == pytest.approx(peek_window.width(), abs=0.01)

    manager.expand()
    assert motion.active and not manager.is_peeking()
    looks = _play(motion)

    assert not motion.active
    assert bar.geometry() == full_window and _frame_rect(bar) == full_frame
    _wait(30)
    assert bar.geometry() == full_window, "nothing moves after the motion ends"
    assert "peek" not in str(bar.bar_frame.property("class")).split()
    assert all(widget.isVisible() for widgets in bar.widgets.values() for widget in widgets)
    assert looks[0].width == peek_window.width()
    assert max(look.width for look in looks) > full_window.width(), "the width overshoots before it settles"
    assert [look.pills for look in looks][:3] == pytest.approx([0, 0, 0]), "the pills wait before they fade in"
    assert looks[-1].pills == pytest.approx(1) and looks[-1].text == pytest.approx(1)


def test_motion_holds_the_window_still_until_it_ends(make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch):
    bar = _motion_bar(make_bar, monkeypatch)
    manager = bar.autohide_manager
    assert manager is not None
    manager.collapse(animate=False)
    _wait(30)
    manager.expand()
    motion = manager._motion
    motion._timer.stop()
    motion.seek(0)
    window = bar.geometry()

    for elapsed in range(0, 240, 16):
        motion.seek(elapsed)
        assert bar.geometry() == window, "a layered window must not be resized per frame"
        assert bar.bar_frame.width() == round(motion._look.width)
    bar.position_bar()

    assert bar.geometry() == window, "position_bar leaves a running motion alone"
    motion.finish()
    assert bar.geometry() != window and not motion.active


def test_pointer_back_mid_collapse_reverses_from_the_current_state(make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch):
    bar = _motion_bar(make_bar, monkeypatch)
    manager = bar.autohide_manager
    assert manager is not None
    motion = manager._motion
    full_window = bar.geometry()
    manager.collapse()
    _play(motion, until=100)
    width, height = bar.bar_frame.width(), bar.bar_frame.height()
    assert 22 < height < 40 and width < full_window.width()

    revealed: list[bool] = []
    monkeypatch.setattr(manager, "_reveal", lambda: revealed.append(True))
    manager.request_show()
    assert revealed == [True], "a pointer back on a collapsing bar skips the show delay"

    manager.expand()

    assert motion.expanding and not manager.is_peeking()
    assert (bar.bar_frame.width(), bar.bar_frame.height()) == (width, height), "reversing must not snap"
    looks = _play(motion)
    assert looks[0].width == pytest.approx(width, abs=1)
    assert bar.geometry() == full_window


@pytest.mark.parametrize("reason", ["windows animation effects off", "bar animation disabled"])
def test_reduced_motion_jumps_to_the_end_state(make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch, reason: str):
    bar = _motion_bar(make_bar, monkeypatch)
    manager = bar.autohide_manager
    assert manager is not None
    manager.collapse(animate=False)
    _wait(30)
    peek_window = bar.geometry()
    manager.expand(animate=False)
    _wait(30)
    full_window = bar.geometry()
    if reason == "windows animation effects off":
        monkeypatch.setattr(bar_motion, "animations_enabled", lambda: False)
    else:
        bar.animation["enabled"] = False

    manager.collapse()
    assert not manager._motion.active
    _wait(30)
    assert bar.geometry() == peek_window

    manager.expand()
    assert not manager._motion.active
    _wait(30)
    assert bar.geometry() == full_window
    assert all(widget.isVisible() for widgets in bar.widgets.values() for widget in widgets)


def test_popup_still_widens_the_bar_after_an_expand(make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch):
    bar = _motion_bar(make_bar, monkeypatch)
    manager = bar.autohide_manager
    assert manager is not None
    tray = bar.widgets["right"][0]
    clock = bar.widgets["center"][0]
    manager.collapse(animate=False)
    manager.expand()
    _play(manager._motion)
    _wait(20)
    resting_width, clock_x = bar.width(), _x_center(clock)

    popup = PopupWidget(tray, bar_anchored=True)
    popup.setFixedSize(resting_width + 120, 60)
    popup.setPosition(alignment="center")
    popup.show()
    _wait(20)

    assert bar.width() == popup.width() == bar.bar_frame.width()
    assert bar.x() == popup.x()
    assert abs(_x_center(clock) - clock_x) <= 1

    popup.hide()
    _wait(20)
    assert bar.width() == resting_width


def test_popup_opening_mid_motion_ends_the_motion_first(make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch):
    bar = _motion_bar(make_bar, monkeypatch)
    manager = bar.autohide_manager
    assert manager is not None
    tray = bar.widgets["right"][0]
    manager.collapse(animate=False)
    manager.expand()
    _play(manager._motion, until=80)

    popup = PopupWidget(tray, bar_anchored=True)
    popup.setFixedSize(bar.width() + 200, 60)
    popup.setPosition(alignment="center")
    popup.show()
    _wait(20)

    assert not manager._motion.active
    assert bar.width() == popup.width() == bar.bar_frame.width()
    popup.hide()


def _shot(x: int, y: int, width: int, height: int, baseline: float) -> bar_motion.Shot:
    return bar_motion.Shot(
        QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied), QRect(x, y, width, height), baseline
    )


def test_clock_and_date_gap_moves_steadily_from_the_peek_gap_to_the_full_gap():
    clock = bar_motion.Piece(_shot(20, 3, 30, 16, 12), _shot(100, 10, 40, 28, 20))
    date = bar_motion.Piece(_shot(54, 3, 30, 16, 12), _shot(160, 10, 60, 28, 20))
    scene = bar_motion.Scene(QSize(100, 22), QSize(300, 48), [clock, date], [], QRect())
    gaps, baselines = [], []

    for step in range(21):
        t = step / 20
        frame_width = 100 + 200 * t
        clock_left, clock_width, clock_baseline = scene.piece_box(clock, frame_width, t)
        date_left, _, date_baseline = scene.piece_box(date, frame_width, t)
        gaps.append(date_left - (clock_left + clock_width))
        baselines.append((clock_baseline, date_baseline))
        assert date_left > clock_left + clock_width, "the date never touches the clock"

    assert gaps[0] == pytest.approx(4) and gaps[-1] == pytest.approx(20)
    assert all(b >= a for a, b in zip(gaps, gaps[1:], strict=False))
    assert all(clock == date for clock, date in baselines), "both texts share one baseline"
    assert baselines == sorted(baselines), "the baseline moves one way, so the digits never bob"


def test_motion_keeps_the_date_right_of_the_clock_on_every_frame(make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch):
    bar = _motion_bar(make_bar, monkeypatch, center=("clock", "date"))
    manager = bar.autohide_manager
    assert manager is not None
    motion = manager._motion
    manager.collapse(animate=False)
    _wait(30)
    manager.expand()
    motion._timer.stop()
    scene = motion._scene
    assert scene is not None and len(scene.pieces) == 2
    clock, date = sorted(scene.pieces, key=lambda piece: piece.full.rect.x())

    gaps = []
    for elapsed in range(0, 200, 8):
        motion.seek(elapsed)
        left, width, _ = scene.piece_box(clock, motion._look.width, motion._look.text)
        date_left, _, _ = scene.piece_box(date, motion._look.width, motion._look.text)
        gaps.append(date_left - (left + width))
        assert gaps[-1] >= -1e-6, "the date never passes under the clock"
    assert all(b >= a - 1e-6 for a, b in zip(gaps, gaps[1:], strict=False)) or all(
        b <= a + 1e-6 for a, b in zip(gaps, gaps[1:], strict=False)
    )
    motion.finish()


def test_end_states_are_rendered_ahead_so_a_hover_starts_without_setup(
    make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch
):
    bar = _motion_bar(make_bar, monkeypatch)
    manager = bar.autohide_manager
    assert manager is not None
    motion = manager._motion
    geometry, visible = bar.geometry(), [w.isVisible() for ws in bar.widgets.values() for w in ws]

    motion.refresh_cache()
    motion.refresh_cache()  # the second poll sees the same content, so it is stable

    assert motion._cache is not None
    assert bar.geometry() == geometry and visible == [w.isVisible() for ws in bar.widgets.values() for w in ws]
    builds = []
    monkeypatch.setattr(motion, "_build", lambda hidden: builds.append(hidden))
    manager.collapse()
    assert builds == [], "a hover uses the pre-rendered states"
    motion.finish()
    assert manager.is_peeking() and not bar.widgets["left"][0].isVisible()

    cached = motion._cache.signature
    bar.widgets["center"][0].setText("changed")
    assert motion._signature() != cached, "a content change makes the cache stale"


def test_frames_follow_the_screen_refresh_rate(make_bar: MakeBar, monkeypatch: pytest.MonkeyPatch):
    bar = _motion_bar(make_bar, monkeypatch)
    manager = bar.autohide_manager
    assert manager is not None

    class _Screen:
        def __init__(self, hz: float) -> None:
            self.hz = hz

        def refreshRate(self) -> float:
            return self.hz

    monkeypatch.setattr(bar, "screen", lambda: _Screen(144.0))
    assert manager._motion.frame_interval() == 6
    monkeypatch.setattr(bar, "screen", lambda: _Screen(0.0))
    assert manager._motion.frame_interval() == 16
