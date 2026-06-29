"""Main entry point for IMU Plotter UI — Qt edition."""

import sys
import os

# Ensure project root is on the path so app modules import correctly
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtCore import Qt
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
from apps.qt_imu_plotter import IMUPlotterWindow
from apps.qt_mpu6050_plotter import MPU6050PlotterWindow
from apps.qt_esc_control import ESCControlWindow
from apps.qt_light_control import LightControlWindow
from apps.qt_control_pad import ControlPadWindow
from apps.qt_vc288 import VC288Window
from apps.qt_leakage import LeakageWindow
from apps.qt_eeprom import EEPROMWindow
from apps.qt_ledc import LEDCWindow
from apps.qt_parser_debug import ParserDebugWindow


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Submarine Control Terminal")
        self.resize(1100, 740)

        # All child windows — created lazily on first toggle
        self._imu_window: IMUPlotterWindow | None = None
        self._mpu_window: MPU6050PlotterWindow | None = None
        self._esc_window: ESCControlWindow | None = None
        self._light_window: LightControlWindow | None = None
        self._pad_window: ControlPadWindow | None = None
        self._vc288_window: VC288Window | None = None
        self._leakage_window: LeakageWindow | None = None
        self._ledc_window: LEDCWindow | None = None
        self._eeprom_window: EEPROMWindow | None = None
        self._parser_debug_window: ParserDebugWindow | None = None
        self._com_port_window: COMPortWindow | None = None
        self._terminal_config_window: TerminalConfigWindow | None = None
        self._dshot_window: DShotWindow | None = None

        self._build_ui()
        self._build_menu()

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

        _win_action("DShot Control",        self._toggle_dshot)
        _win_action("IMU Plotter (BNO085)", self._toggle_imu)
        _win_action("MPU6050 Plotter",      self._toggle_mpu)
        _win_action("ESC Control",          self._toggle_esc)
        _win_action("Light Control",        self._toggle_light)
        _win_action("Control Pad",          self._toggle_pad)
        _win_action("VC288 Sensor",         self._toggle_vc288)
        _win_action("Leakage Sensor",       self._toggle_leakage)

        # ── Peripheral ────────────────────────────────────────────────────
        periph_menu = mb.addMenu("&Peripheral")
        _win_action("LEDC",                 self._toggle_ledc,  periph_menu)
        _win_action("EEPROM",               self._toggle_eeprom, periph_menu)

        # ── Debug ─────────────────────────────────────────────────────────
        debug_menu = mb.addMenu("&Debug")
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
            for win in (
                self._com_port_window,
                self._light_window,
                self._dshot_window,
                self._esc_window,
                self._imu_window,
                self._mpu_window,
                self._vc288_window,
                self._leakage_window,
                self._ledc_window,
                self._pad_window,
            ):
                if win is not None and hasattr(win, "reload_from_config"):
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
        QHBoxLayout(root).addWidget(self._serial)

    # ------------------------------------------------------------------
    # Toggle helpers — create on first open, show/hide on subsequent clicks
    # ------------------------------------------------------------------

    def _toggle_dshot(self) -> None:
        if self._dshot_window is None:
            self._dshot_window = DShotWindow(self._serial)
            self._dshot_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._toggle_win(self._dshot_window)

    def _toggle_terminal_config(self) -> None:
        if self._terminal_config_window is None:
            self._terminal_config_window = TerminalConfigWindow(self._serial)
            self._terminal_config_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._toggle_win(self._terminal_config_window)

    def _toggle_com_port(self) -> None:
        if self._com_port_window is None:
            self._com_port_window = COMPortWindow(self._serial)
            self._com_port_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._toggle_win(self._com_port_window)

    def _toggle_imu(self) -> None:
        if self._imu_window is None:
            self._imu_window = IMUPlotterWindow(self._serial)
            self._imu_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._toggle_win(self._imu_window)

    def _toggle_mpu(self) -> None:
        if self._mpu_window is None:
            self._mpu_window = MPU6050PlotterWindow(self._serial)
            self._mpu_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._toggle_win(self._mpu_window)

    def _toggle_esc(self) -> None:
        if self._esc_window is None:
            self._esc_window = ESCControlWindow(self._serial)
            self._esc_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
            if self._pad_window is not None:
                self._pad_window.set_esc_control_app(self._esc_window)
        else:
            if self._pad_window is not None:
                self._pad_window.set_esc_control_app(self._esc_window)
        self._toggle_win(self._esc_window)

    def _toggle_light(self) -> None:
        if self._light_window is None:
            self._light_window = LightControlWindow(self._serial)
            self._light_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
            if self._pad_window is not None:
                self._pad_window.set_light_control_app(self._light_window)
        else:
            if self._pad_window is not None:
                self._pad_window.set_light_control_app(self._light_window)
        self._toggle_win(self._light_window)

    def _toggle_pad(self) -> None:
        if self._pad_window is None:
            self._pad_window = ControlPadWindow(
                self._serial,
                light_control_app=self._light_window,
                esc_control_app=self._esc_window,
            )
            self._pad_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        else:
            self._pad_window.set_light_control_app(self._light_window)
            self._pad_window.set_esc_control_app(self._esc_window)
        self._toggle_win(self._pad_window)

    def _toggle_vc288(self) -> None:
        if self._vc288_window is None:
            self._vc288_window = VC288Window(self._serial)
            self._vc288_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._toggle_win(self._vc288_window)

    def _toggle_leakage(self) -> None:
        if self._leakage_window is None:
            self._leakage_window = LeakageWindow(self._serial)
            self._leakage_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._toggle_win(self._leakage_window)

    def _toggle_ledc(self) -> None:
        if self._ledc_window is None:
            self._ledc_window = LEDCWindow(self._serial, self._response_parser)
            self._ledc_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._toggle_win(self._ledc_window)

    def _toggle_eeprom(self) -> None:
        if self._eeprom_window is None:
            self._eeprom_window = EEPROMWindow(self._serial, self._response_parser)
            self._eeprom_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._toggle_win(self._eeprom_window)

    def _toggle_parser_debug(self) -> None:
        if self._parser_debug_window is None:
            self._parser_debug_window = ParserDebugWindow(self._response_parser)
            self._parser_debug_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
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
            self._imu_window,
            self._mpu_window,
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
        for win in (
            self._dshot_window,
            self._terminal_config_window,
            self._com_port_window,
            self._imu_window,
            self._mpu_window,
            self._esc_window,
            self._light_window,
            self._pad_window,
            self._vc288_window,
            self._leakage_window,
            self._ledc_window,
        ):
            if win is not None:
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
