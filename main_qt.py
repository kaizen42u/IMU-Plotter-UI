"""Main entry point for IMU Plotter UI — Qt edition."""

import sys
import os

# Ensure project root is on the path so app modules import correctly
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from configManager import get_active_config_path, list_config_profiles
from config_store import pool
from serial_response_parser import SerialResponseParser
from apps.qt_serial_terminal import SerialTerminalWidget
from apps.qt_com_port import COMPortWindow
from apps.qt_terminal_config import TerminalConfigWindow
from apps.qt_dshot import DShotWindow
from apps.qt_bdshot import BDShotWindow
from apps.qt_mpu6050 import MPU6050Window
from apps.qt_ina228 import INA228Window
from apps.qt_esc_control import ESCControlWindow
from apps.qt_light_control import LightControlWindow
from apps.qt_control_pad import ControlPadWindow
from apps.qt_vc288 import VC288Window
from apps.qt_leakage import LeakageWindow
from apps.qt_eeprom import EEPROMWindow
from apps.qt_gpio import GPIOWindow
from apps.qt_ledc import LEDCWindow
from apps.qt_sdm import SDMWindow
from apps.qt_am32 import AM32Window
from apps.qt_bno085 import BNO085Window
from apps.qt_tasks import TasksWindow
from apps.qt_events import EventWindow
from apps.qt_imu_plotter2 import IMUPlotter2Window
from apps.qt_parser_debug import ParserDebugWindow


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Submarine Control Terminal")
        self.resize(1100, 740)

        # Registry of all child windows — populated by _open_win().
        # closeEvent and profile reload iterate this; no manual lists needed.
        self._child_windows: list[QWidget] = []

        # Per-window handles for lazy creation checks (None = not yet created)
        self._mpu6050_window: MPU6050Window | None = None
        self._ina228_window:  INA228Window  | None = None
        self._esc_window: ESCControlWindow | None = None
        self._light_window: LightControlWindow | None = None
        self._pad_window: ControlPadWindow | None = None
        self._vc288_window: VC288Window | None = None
        self._leakage_window: LeakageWindow | None = None
        self._ledc_window: LEDCWindow | None = None
        self._sdm_window:   SDMWindow   | None = None
        self._tasks_window:  TasksWindow  | None = None
        self._events_window: EventWindow  | None = None
        self._imu2_window: IMUPlotter2Window | None = None
        self._am32_window:   AM32Window   | None = None
        self._bno085_window: BNO085Window | None = None
        self._eeprom_window: EEPROMWindow | None = None
        self._gpio_window: GPIOWindow | None = None
        self._com_port_window: COMPortWindow | None = None
        self._terminal_config_window: TerminalConfigWindow | None = None
        self._dshot_window: DShotWindow | None = None
        self._bdshot_window: BDShotWindow | None = None

        self._build_ui()
        self._build_menu()
        # Sync every checkable menu action to the terminal's actual state (loaded
        # from the profile). Otherwise a mismatch (e.g. logging on at boot but the
        # menu unchecked) makes the first click a no-op — setChecked() to a value
        # the widget already holds emits no toggled signal.
        self._act_events.setChecked(self._serial._show_events)
        self._act_echo.setChecked(self._serial._show_echo)
        self._act_logging.setChecked(self._serial._logging_checkbox.isChecked())
        self._act_autoscroll.setChecked(self._serial._autoscroll_cb.isChecked())
        # Defer auto-connect until after the event loop starts so the window
        # is visible before the serial.connect() call blocks briefly.
        QTimer.singleShot(300, self._serial.try_auto_connect)

    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        mb = self.menuBar()

        # ── File ──────────────────────────────────────────────────────────
        file_menu = mb.addMenu("&File")

        act_clear = QAction("Clear Terminal", self)
        act_clear.setShortcut("Ctrl+L")
        act_clear.triggered.connect(lambda: self._serial._terminal.clear_terminal())
        file_menu.addAction(act_clear)

        file_menu.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut("Alt+F4")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # ── Connection ────────────────────────────────────────────────────
        conn_menu = mb.addMenu("&Connection")

        act_com_port = QAction("COM Port Settings…", self)
        act_com_port.setShortcut("Ctrl+P")
        act_com_port.triggered.connect(self._toggle_com_port)
        conn_menu.addAction(act_com_port)

        conn_menu.addSeparator()

        self._act_connect = QAction("Connect", self)
        self._act_connect.setShortcut("Ctrl+K")
        self._act_connect.triggered.connect(self._serial.connect_from_settings)
        conn_menu.addAction(self._act_connect)

        self._act_disconnect = QAction("Disconnect", self)
        self._act_disconnect.triggered.connect(self._serial.disconnect_from)
        self._act_disconnect.setEnabled(False)
        conn_menu.addAction(self._act_disconnect)

        self._serial.connection_changed.connect(self._on_connection_changed)

        conn_menu.addSeparator()

        self._act_autoscroll = QAction("Auto Scroll", self, checkable=True)
        self._act_autoscroll.setChecked(True)
        self._act_autoscroll.triggered.connect(
            lambda checked: self._serial._autoscroll_cb.setChecked(checked)
        )
        conn_menu.addAction(self._act_autoscroll)

        self._act_logging = QAction("Logging", self, checkable=True)
        self._act_logging.triggered.connect(
            lambda checked: self._serial._logging_checkbox.setChecked(checked)
        )
        conn_menu.addAction(self._act_logging)

        self._act_events = QAction("Show Events", self, checkable=True, checked=True)
        self._act_events.triggered.connect(self._sync_events_action)
        conn_menu.addAction(self._act_events)

        self._act_echo = QAction("Local Echo", self, checkable=True, checked=True)
        self._act_echo.triggered.connect(self._sync_echo_action)
        conn_menu.addAction(self._act_echo)

        # Keep menu items in sync when the widget checkboxes change.
        self._serial._autoscroll_cb.toggled.connect(self._act_autoscroll.setChecked)
        self._serial._logging_checkbox.toggled.connect(self._act_logging.setChecked)

        # ── Windows ───────────────────────────────────────────────────────
        win_menu = mb.addMenu("&Windows")

        def _win_action(label: str, slot, menu=win_menu) -> QAction:
            a = QAction(label, self)
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        _win_action("IMU Plotter",          self._toggle_imu2)
        _win_action("Control Pad",          self._toggle_pad)

        # ── Peripheral ────────────────────────────────────────────────────
        periph_menu = mb.addMenu("&Peripheral")
        _win_action("LEDC",                 self._toggle_ledc,   periph_menu)
        _win_action("SDM",                  self._toggle_sdm,    periph_menu)
        _win_action("EEPROM",               self._toggle_eeprom, periph_menu)
        _win_action("GPIO",                 self._toggle_gpio,   periph_menu)

        # ── Devices ───────────────────────────────────────────────────────
        devices_menu = mb.addMenu("&Devices")
        esc_menu = devices_menu.addMenu("ESC")
        _win_action("DShot",                self._toggle_dshot,  esc_menu)
        _win_action("bDShot",               self._toggle_bdshot, esc_menu)
        _win_action("PWM",                  self._toggle_esc,    esc_menu)
        _win_action("Light Control",        self._toggle_light,  devices_menu)
        _win_action("AM32 Config",          self._toggle_am32,   devices_menu)
        imu_menu = devices_menu.addMenu("IMU")
        _win_action("BNO085",               self._toggle_bno085,  imu_menu)
        _win_action("MPU6050",              self._toggle_mpu6050, imu_menu)
        pmic_menu = devices_menu.addMenu("PMIC")
        _win_action("VC288",                self._toggle_vc288,   pmic_menu)
        _win_action("INA228",               self._toggle_ina228,  pmic_menu)
        _win_action("Leakage Sensor",       self._toggle_leakage, devices_menu)

        # ── Debug ─────────────────────────────────────────────────────────
        debug_menu = mb.addMenu("&Debug")
        _win_action("RTOS Tasks",           self._toggle_tasks,  debug_menu)
        _win_action("Events",               self._toggle_events, debug_menu)
        act_parser_dbg = QAction("Response Parser…", self)
        act_parser_dbg.triggered.connect(self._toggle_parser_debug)
        debug_menu.addAction(act_parser_dbg)

        # ── Settings ──────────────────────────────────────────────────────
        settings_menu = mb.addMenu("&Settings")

        act_term = QAction("Terminal…", self)
        act_term.triggered.connect(self._toggle_terminal_config)
        settings_menu.addAction(act_term)

        settings_menu.addSeparator()

        act_cfg = QAction("Config Profile…", self)
        act_cfg.triggered.connect(self._open_profile_dialog)
        settings_menu.addAction(act_cfg)

        # ── Help ─────────────────────────────────────────────────────────
        help_menu = mb.addMenu("&Help")

        act_about = QAction("&About", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    # ── Menu helpers ──────────────────────────────────────────────────────

    def _on_connection_changed(self, connected: bool) -> None:
        self._act_connect.setEnabled(not connected)
        self._act_disconnect.setEnabled(connected)

    def _sync_events_action(self, checked: bool) -> None:
        self._serial._show_events = checked

    def _sync_echo_action(self, checked: bool) -> None:
        self._serial._show_echo = checked

    def _open_profile_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Config Profile")
        dlg.setMinimumWidth(380)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Select a configuration profile:"))

        profile_list = QListWidget()
        profile_list.setAlternatingRowColors(True)
        layout.addWidget(profile_list)

        def _reload_list(select_name: str | None = None) -> None:
            profiles = list_config_profiles()
            active = get_active_config_path()
            profile_list.clear()
            profile_list.setProperty("_profiles", profiles)
            for name, path in profiles.items():
                item = QListWidgetItem(name)
                try:
                    is_active = path.resolve() == active.resolve()
                except Exception:
                    is_active = False
                if is_active:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setText(name + "  ✓")
                profile_list.addItem(item)
                if select_name and name == select_name:
                    profile_list.setCurrentItem(item)
                elif is_active and select_name is None:
                    profile_list.setCurrentItem(item)

        _reload_list()

        btn_row = QHBoxLayout()

        apply_btn = QPushButton("Apply")
        def _apply() -> None:
            item = profile_list.currentItem()
            if not item:
                return
            raw_name = item.text().removesuffix("  ✓")
            # Save current window states to the outgoing profile first
            self._save_all_configs()
            self._serial._profile_combo.setCurrentText(raw_name)
            # Sync all open windows to the new profile's values
            for win in self._child_windows:
                if hasattr(win, "reload_from_config"):
                    win.reload_from_config()
            _reload_list(raw_name)

        apply_btn.clicked.connect(_apply)
        profile_list.itemDoubleClicked.connect(lambda _: _apply())

        new_btn = QPushButton("New Profile…")
        def _new_profile() -> None:
            name, ok = QInputDialog.getText(dlg, "New Profile", "Profile name:")
            if not ok or not name.strip():
                return
            name = name.strip()
            fname = name if name.endswith(".json") else name + ".json"
            from pathlib import Path
            profiles_dir = Path(__file__).parent / "profiles"
            profiles_dir.mkdir(exist_ok=True)
            dest = profiles_dir / fname
            if dest.exists():
                QMessageBox.warning(dlg, "Exists", f"{fname} already exists.")
                return
            try:
                dest.write_text("{}\n")
            except Exception as e:
                QMessageBox.critical(dlg, "Error", str(e))
                return
            self._serial._load_profiles()
            _reload_list(f"profiles/{fname}")

        new_btn.clicked.connect(_new_profile)

        btn_row.addWidget(apply_btn)
        btn_row.addStretch()
        btn_row.addWidget(new_btn)
        layout.addLayout(btn_row)

        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn.rejected.connect(dlg.reject)
        layout.addWidget(close_btn)

        dlg.exec()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About IMU Plotter UI",
            "<b>IMU Plotter UI</b><br>"
            "Submarine Control Terminal<br><br>"
            "Qt edition — PySide6",
        )

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        self._serial = SerialTerminalWidget()
        self._response_parser = SerialResponseParser(self._serial)
        # Create hidden immediately so hooks are registered before the window opens.
        self._parser_debug_window = self._open_win(ParserDebugWindow(self._response_parser))
        QHBoxLayout(root).addWidget(self._serial)

    # ------------------------------------------------------------------
    # Toggle helpers — create on first open, show/hide on subsequent clicks
    # ------------------------------------------------------------------

    def _open_win(self, win: QWidget) -> QWidget:
        """Register a child window so closeEvent and profile reload find it automatically."""
        win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._child_windows.append(win)
        return win

    def _toggle_dshot(self) -> None:
        if self._dshot_window is None:
            self._dshot_window = self._open_win(DShotWindow(self._serial))
        if self._pad_window is not None:
            self._pad_window.set_dshot_app(self._dshot_window)
        self._toggle_win(self._dshot_window)

    def _toggle_bdshot(self) -> None:
        if self._bdshot_window is None:
            self._bdshot_window = self._open_win(BDShotWindow(self._serial, self._response_parser))
        if self._pad_window is not None:
            self._pad_window.set_bdshot_app(self._bdshot_window)
        self._toggle_win(self._bdshot_window)

    def _toggle_terminal_config(self) -> None:
        if self._terminal_config_window is None:
            self._terminal_config_window = self._open_win(TerminalConfigWindow(self._serial))
        self._toggle_win(self._terminal_config_window)

    def _toggle_com_port(self) -> None:
        if self._com_port_window is None:
            self._com_port_window = self._open_win(COMPortWindow(self._serial))
        self._toggle_win(self._com_port_window)

    def _toggle_mpu6050(self) -> None:
        if self._mpu6050_window is None:
            self._mpu6050_window = self._open_win(MPU6050Window(self._serial, self._response_parser))
        self._toggle_win(self._mpu6050_window)

    def _toggle_ina228(self) -> None:
        if self._ina228_window is None:
            self._ina228_window = self._open_win(INA228Window(self._serial, self._response_parser))
        self._toggle_win(self._ina228_window)

    def _toggle_esc(self) -> None:
        if self._esc_window is None:
            self._esc_window = self._open_win(ESCControlWindow(self._serial))
        if self._pad_window is not None:
            self._pad_window.set_esc_control_app(self._esc_window)
        self._toggle_win(self._esc_window)

    def _toggle_light(self) -> None:
        if self._light_window is None:
            self._light_window = self._open_win(LightControlWindow(self._serial))
        if self._pad_window is not None:
            self._pad_window.set_light_control_app(self._light_window)
        self._toggle_win(self._light_window)

    def _toggle_pad(self) -> None:
        # Ensure all ESC backends exist (hidden is fine) so the pad's
        # PWM/DShot/bDShot selector can drive any without opening them first.
        if self._esc_window is None:
            self._esc_window = self._open_win(ESCControlWindow(self._serial))
        if self._dshot_window is None:
            self._dshot_window = self._open_win(DShotWindow(self._serial))
        if self._bdshot_window is None:
            self._bdshot_window = self._open_win(BDShotWindow(self._serial, self._response_parser))
        if self._pad_window is None:
            self._pad_window = self._open_win(ControlPadWindow(
                self._serial,
                light_control_app=self._light_window,
                esc_control_app=self._esc_window,
                dshot_app=self._dshot_window,
                bdshot_app=self._bdshot_window,
            ))
        else:
            self._pad_window.set_light_control_app(self._light_window)
            self._pad_window.set_esc_control_app(self._esc_window)
            self._pad_window.set_dshot_app(self._dshot_window)
            self._pad_window.set_bdshot_app(self._bdshot_window)
        self._toggle_win(self._pad_window)

    def _toggle_vc288(self) -> None:
        if self._vc288_window is None:
            self._vc288_window = self._open_win(VC288Window(self._serial, self._response_parser))
        self._toggle_win(self._vc288_window)

    def _toggle_leakage(self) -> None:
        if self._leakage_window is None:
            self._leakage_window = self._open_win(LeakageWindow(self._serial))
        self._toggle_win(self._leakage_window)

    def _toggle_ledc(self) -> None:
        if self._ledc_window is None:
            self._ledc_window = self._open_win(LEDCWindow(self._serial, self._response_parser))
        self._toggle_win(self._ledc_window)

    def _toggle_sdm(self) -> None:
        if self._sdm_window is None:
            self._sdm_window = self._open_win(SDMWindow(self._serial, self._response_parser))
        self._toggle_win(self._sdm_window)

    def _toggle_tasks(self) -> None:
        if self._tasks_window is None:
            self._tasks_window = self._open_win(TasksWindow(self._serial, self._response_parser))
        self._toggle_win(self._tasks_window)

    def _toggle_events(self) -> None:
        if self._events_window is None:
            self._events_window = self._open_win(EventWindow(self._serial, self._response_parser))
        self._toggle_win(self._events_window)

    def _toggle_imu2(self) -> None:
        if self._imu2_window is None:
            self._imu2_window = self._open_win(IMUPlotter2Window(self._serial, self._response_parser))
        self._toggle_win(self._imu2_window)

    def _toggle_am32(self) -> None:
        if self._am32_window is None:
            self._am32_window = self._open_win(AM32Window(self._serial, self._response_parser))
        self._toggle_win(self._am32_window)

    def _toggle_bno085(self) -> None:
        if self._bno085_window is None:
            self._bno085_window = self._open_win(BNO085Window(self._serial, self._response_parser))
        self._toggle_win(self._bno085_window)

    def _toggle_eeprom(self) -> None:
        if self._eeprom_window is None:
            self._eeprom_window = self._open_win(EEPROMWindow(self._serial, self._response_parser))
        self._toggle_win(self._eeprom_window)

    def _toggle_gpio(self) -> None:
        if self._gpio_window is None:
            self._gpio_window = self._open_win(GPIOWindow(self._serial, self._response_parser))
        self._toggle_win(self._gpio_window)

    def _toggle_parser_debug(self) -> None:
        self._toggle_win(self._parser_debug_window)

    @staticmethod
    def _toggle_win(win: QWidget) -> None:
        if win.isVisible():
            win.hide()
        else:
            win.show()
            win.raise_()
            win.activateWindow()

    # ------------------------------------------------------------------
    def _save_all_configs(self) -> None:
        """Flush every open window's UI state into the pool, then write once."""
        for win in (
            self._com_port_window,
            self._dshot_window,
            self._bdshot_window,
            self._mpu6050_window,
            self._esc_window,
            self._light_window,
            self._pad_window,
            self._vc288_window,
            self._leakage_window,
            self._ledc_window,
        ):
            if win is not None and hasattr(win, "_save_config"):
                win._save_config()
        self._serial._save_config()
        pool.save()

    def closeEvent(self, event) -> None:
        self._save_all_configs()
        for win in self._child_windows:
            win.close()
        self._serial.close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("IMU Plotter UI")
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QProxyStyle, QStyle
    class _BigSlider(QProxyStyle):
        _HANDLE = 24   # handle size (px)
        _GROOVE = 10   # groove thickness (px)

        def pixelMetric(self, metric, option=None, widget=None):
            if metric in (
                QStyle.PixelMetric.PM_SliderThickness,
                QStyle.PixelMetric.PM_SliderLength,
                QStyle.PixelMetric.PM_SliderControlThickness,
            ):
                return self._HANDLE
            return super().pixelMetric(metric, option, widget)

        def subControlRect(self, control, option, subControl, widget=None):
            rect = super().subControlRect(control, option, subControl, widget)
            if (control == QStyle.ComplexControl.CC_Slider and
                    subControl == QStyle.SubControl.SC_SliderGroove):
                center = option.rect.center()
                if option.orientation == _Qt.Orientation.Horizontal:
                    rect.setHeight(self._GROOVE)
                    rect.moveCenter(center)
                else:
                    rect.setWidth(self._GROOVE)
                    rect.moveCenter(center)
            return rect

    app.setStyle(_BigSlider())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
