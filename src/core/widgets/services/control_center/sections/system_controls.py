import io
from collections.abc import Callable
from functools import partial
from typing import Any, override

from PIL import Image
from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QIcon, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget

from core.bar_helper import GlobalState
from core.utils.qobject import is_valid_qobject
from core.utils.shell_utils import shell_open
from core.utils.tooltip import set_tooltip
from core.utils.utilities import refresh_widget_style
from core.utils.win32.utils import apply_qmenu_style
from core.validation.widgets.yasb.control_center import SystemControlsConfig
from core.widgets.services.control_center.sections.quick_actions import ActionButton
from core.widgets.services.power_menu.power_commands import PowerOperations
from core.widgets.services.power_menu.user_info import get_user_avatar_path, get_windows_username


class SystemControlsSectionWidget(QFrame):
    """Section containing system-level controls: user profile, settings, and power menu."""

    def __init__(
        self, parent: QWidget, config: SystemControlsConfig, refresh_popup: Callable[[], None], tooltip: bool = False
    ):
        super().__init__(parent)
        self.config = config
        self.refresh_popup = refresh_popup
        self._tooltip = tooltip
        self.setProperty("class", "section system-controls")

        self._power_ops = PowerOperations(main_window=parent)

        self._settings_btn: QPushButton | None = None
        self._settings_menu: QMenu | None = None
        self._power_btn: QPushButton | None = None
        self._power_menu: QMenu | None = None
        self._profile_image_btn: QPushButton | None = None
        self._profile_menu: QMenu | None = None
        self._profile_dpr: float | None = None
        self._power_list: QFrame | None = None
        self._settings_list: QFrame | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        layout = QHBoxLayout()
        outer.addLayout(layout)

        self._build_profile_controls(layout)

        layout.addStretch(1)

        self._settings_btn = QPushButton(config.settings_icon, self)
        self._settings_btn.setProperty("class", "button settings")
        if config.settings_style == "list":
            self._settings_list = self._build_settings_list()
            outer.addWidget(self._settings_list)
            self._settings_btn.clicked.connect(lambda: self._set_settings_list_open(self._settings_list.isHidden()))
        else:
            self._settings_btn.clicked.connect(self._show_settings_menu)
        if self._tooltip:
            set_tooltip(self._settings_btn, "Settings", position="top")
        layout.addWidget(self._settings_btn)

        self._power_btn = QPushButton(config.power_icon, self)
        self._power_btn.setProperty("class", "button power")
        if config.power_style == "list":
            self._power_list = self._build_power_list()
            outer.addWidget(self._power_list)
            self._power_btn.clicked.connect(lambda: self._set_power_list_open(self._power_list.isHidden()))
        else:
            self._power_btn.clicked.connect(self._show_power_menu)
        if self._tooltip:
            set_tooltip(self._power_btn, "Power", position="top")
        layout.addWidget(self._power_btn)

    def _build_power_list(self) -> QFrame:
        power_list = QFrame(self)
        power_list.setProperty("class", "power-list")
        grid = QGridLayout(power_list)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        actions = [
            ("lock", self.config.lock_icon, "Lock", self._power_ops.lock),
            ("signout", "\uf3b1", "Sign out", self._power_ops.signout),
            ("sleep", "\ue708", "Sleep", self._power_ops.sleep),
            ("restart", "\ue777", "Restart", self._power_ops.restart),
            ("shutdown", self.config.power_icon, "Shut down", self._power_ops.shutdown),
        ]
        # Two columns of tiles; Shut down, the last and hardest to undo, takes the whole bottom row on its own.
        for index, (name, icon, title, run) in enumerate(actions):
            row = ActionButton(power_list)
            row.setProperty("class", f"power-item {name}")
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            for text, part_class in ((icon, "icon"), (title, "label")):
                part = QLabel(text, row)
                part.setProperty("class", part_class)
                row_layout.addWidget(part)
            row_layout.addStretch(1)
            row.clicked.connect(partial(self._run_power_action, run))
            last = index == len(actions) - 1
            grid.addWidget(row, index // 2, 0 if last else index % 2, 1, 2 if last else 1)
        power_list.hide()
        return power_list

    def _build_settings_list(self) -> QFrame:
        settings_list = QFrame(self)
        settings_list.setProperty("class", "settings-list")
        column = QVBoxLayout(settings_list)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        for group in self.config.settings_groups:
            header = QFrame(settings_list)
            header.setProperty("class", "settings-group")
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(group.label.upper(), header)
            label.setProperty("class", "settings-group-label")
            rule = QFrame(header)
            rule.setProperty("class", "settings-group-rule")
            header_layout.addWidget(label)
            header_layout.addWidget(rule, 1)
            column.addWidget(header)
            for item in group.items:
                column.addWidget(self._build_settings_row(settings_list, item.icon, item.label, item.uri))
        separator = QFrame(settings_list)
        separator.setProperty("class", "settings-separator")
        column.addWidget(separator)
        column.addWidget(
            self._build_settings_row(settings_list, self.config.settings_icon, "All Settings", "ms-settings:")
        )
        settings_list.hide()
        return settings_list

    def _build_settings_row(self, parent: QFrame, icon: str, title: str, uri: str) -> ActionButton:
        row = ActionButton(parent)
        row.setProperty("class", "settings-item")
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        for text, part_class in ((icon, "icon"), (title, "label")):
            part = QLabel(text, row)
            part.setProperty("class", part_class)
            row_layout.addWidget(part)
        row_layout.addStretch(1)
        row.clicked.connect(partial(self._open_settings_page, uri))
        return row

    def _set_unfold_open(self, unfold: QFrame | None, btn: QPushButton | None, name: str, is_open: bool) -> None:
        if unfold is None or btn is None or unfold.isHidden() != is_open:
            return
        unfold.setVisible(is_open)
        btn.setProperty("class", f"button {name} active" if is_open else f"button {name}")
        refresh_widget_style(btn)
        # Layouts recompute their size hint only after the show or hide event, so resize the popup on the next loop turn
        QTimer.singleShot(0, self.window().adjustSize)

    # The two lists share the space under the header, so opening one folds the other
    def _set_power_list_open(self, is_open: bool) -> None:
        if is_open:
            self._set_unfold_open(self._settings_list, self._settings_btn, "settings", False)
        self._set_unfold_open(self._power_list, self._power_btn, "power", is_open)

    def _set_settings_list_open(self, is_open: bool) -> None:
        if is_open:
            self._set_unfold_open(self._power_list, self._power_btn, "power", False)
        self._set_unfold_open(self._settings_list, self._settings_btn, "settings", is_open)

    def _run_power_action(self, run: Callable[[], None]) -> None:
        self.window().close()
        run()

    def _open_settings_page(self, uri: str) -> None:
        self.window().close()
        shell_open(uri)

    def _build_profile_controls(self, layout: QHBoxLayout):
        self._profile_image_btn = QPushButton(self)
        self._profile_image_btn.setProperty("class", "button profile-image")
        self._update_profile_image()
        self._profile_image_btn.clicked.connect(self._show_profile_menu)
        if self._tooltip:
            set_tooltip(self._profile_image_btn, get_windows_username(), position="top")
        layout.addWidget(self._profile_image_btn)

    @override
    def event(self, e: QEvent | None) -> bool:
        # Built before the popup has a screen, so the scale is only known once it is shown
        if e is not None and e.type() in (QEvent.Type.Show, QEvent.Type.DevicePixelRatioChange):
            self._update_profile_image()
        return super().event(e)

    def _update_profile_image(self) -> None:
        dpr = self.devicePixelRatioF()
        if dpr == self._profile_dpr or not is_valid_qobject(self._profile_image_btn):
            return
        self._profile_dpr = dpr
        size = self.config.profile_image_size
        icon = self._build_profile_image_icon(size, dpr)
        if icon is not None:
            self._profile_image_btn.setIcon(icon)
            self._profile_image_btn.setIconSize(QSize(size, size))

    def _build_profile_image_icon(self, size: int, dpr: float) -> QIcon | None:
        profile_image_path = get_user_avatar_path()
        if not profile_image_path:
            return None
        phys = max(1, round(size * dpr))

        try:
            with Image.open(profile_image_path) as image:
                if image.mode != "RGBA":
                    image = image.convert("RGBA")

                width, height = image.size
                if width > height:
                    left = (width - height) // 2
                    square = image.crop((left, 0, left + height, height))
                elif height > width:
                    top = (height - width) // 2
                    square = image.crop((0, top, width, top + width))
                else:
                    square = image

                resized = square.resize((phys, phys), Image.LANCZOS)
                buffer = io.BytesIO()
                resized.save(buffer, format="PNG")
                pixmap = QPixmap()
                if not pixmap.loadFromData(buffer.getvalue()):
                    return None
        except Exception:
            return None

        rounded = QPixmap(phys, phys)
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, phys, phys)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        rounded.setDevicePixelRatio(dpr)
        return QIcon(rounded)

    def _create_context_menu(self) -> QMenu:
        menu = QMenu(self.window())
        apply_qmenu_style(menu)
        menu.setProperty("class", "context-menu dark" if GlobalState.is_dark() else "context-menu")
        return menu

    @staticmethod
    def _populate_menu(menu: QMenu, items: list[tuple[str, Callable[..., Any]] | None]):
        for item in items:
            if item is None:
                menu.addSeparator()
            else:
                label, callback = item
                action = QAction(label, menu)
                menu.addAction(action)
                action.triggered.connect(callback)

    @staticmethod
    def _open_link(url: str, checked: bool = False) -> None:
        shell_open(url)

    def _show_settings_menu(self):
        if self._settings_menu and is_valid_qobject(self._settings_menu) and self._settings_menu.isVisible():
            self._settings_menu.close()
            return
        btn = self._settings_btn
        if btn is None:
            return

        menu = self._create_context_menu()
        links = [
            ("Windows Update", "ms-settings:windowsupdate"),
            ("Network && Internet", "ms-settings:network"),
            ("Bluetooth && Devices", "ms-settings:bluetooth"),
            ("Sound", "ms-settings:sound"),
            ("Notifications", "ms-settings:notifications"),
            ("Power && Battery", "ms-settings:powersleep"),
            ("Apps", "ms-settings:appsfeatures"),
            ("Accounts", "ms-settings:yourinfo"),
            ("Privacy && Security", "ms-settings:privacy"),
            None,
            ("All Settings", "ms-settings:"),
        ]
        self._populate_menu(
            menu,
            [link if link is None else (link[0], partial(self._open_link, link[1])) for link in links],
        )

        self._settings_menu = menu
        pos = btn.mapToGlobal(QPoint(btn.width() - menu.sizeHint().width(), btn.height() + 6))
        btn.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
        btn.update()
        menu.popup(pos)

    def _show_profile_menu(self):
        if self._profile_menu and is_valid_qobject(self._profile_menu) and self._profile_menu.isVisible():
            self._profile_menu.close()
            return
        btn = self._profile_image_btn
        if btn is None:
            return

        menu = self._create_context_menu()
        username_action = QAction(get_windows_username(), menu)
        menu.addAction(username_action)
        username_action.triggered.connect(partial(self._open_link, "ms-settings:yourinfo"))
        menu.addSeparator()
        self._populate_menu(
            menu,
            [
                ("Lock", self._power_ops.lock),
                ("Sign Out", self._power_ops.signout),
            ],
        )

        self._profile_menu = menu
        pos = btn.mapToGlobal(QPoint(0, btn.height() + 6))
        btn.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
        btn.update()
        menu.popup(pos)

    def _show_power_menu(self):
        if self._power_menu and is_valid_qobject(self._power_menu) and self._power_menu.isVisible():
            self._power_menu.close()
            return
        btn = self._power_btn
        if btn is None:
            return

        menu = self._create_context_menu()
        self._populate_menu(
            menu,
            [
                ("Sleep", self._power_ops.sleep),
                ("Hibernate", self._power_ops.hibernate),
                ("Restart", self._power_ops.restart),
                ("Shut Down", self._power_ops.shutdown),
            ],
        )

        self._power_menu = menu
        pos = btn.mapToGlobal(QPoint(btn.width() - menu.sizeHint().width(), btn.height() + 6))
        btn.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
        btn.update()
        menu.popup(pos)

    def refresh_state(self) -> None:
        if self._settings_menu and is_valid_qobject(self._settings_menu):
            self._settings_menu.close()
        if self._profile_menu and is_valid_qobject(self._profile_menu):
            self._profile_menu.close()
        if self._power_menu and is_valid_qobject(self._power_menu):
            self._power_menu.close()
        self._set_power_list_open(False)
        self._set_settings_list_open(False)
