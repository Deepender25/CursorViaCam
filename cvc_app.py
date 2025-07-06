import cv2
import mediapipe as mp
import pyautogui
pyautogui.FAILSAFE = False
import sys
import os
import time
import numpy as np
from collections import deque

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QComboBox, QSlider, QCheckBox, QFrame, QGridLayout, QSizePolicy, QErrorMessage,
    QInputDialog, QMessageBox, QSpacerItem, QStackedWidget, QScrollArea
)
from PyQt6.QtGui import QImage, QPixmap, QIcon, QPainter, QPen, QColor, QScreen, QFont
from PyQt6.QtCore import Qt, QTimer, QSize, QPoint, QRect

from constants import (
    IS_WINDOWS, CONFIG_FILE, MIN_TRACK_AREA_LEVEL, MAX_TRACK_AREA_LEVEL,
    DEFAULT_PADDING_VALUE, MIN_GAP_LEVEL, MAX_GAP_LEVEL, DEFAULT_GAP_LEVEL, MIDDLE_CLICK_HOLD_DURATION,
    DOUBLE_BLINK_INTERVAL, EDGE_MAP_MARGIN_PX, TUTORIAL_STATE_IDLE,
    TUTORIAL_STATE_SHOWING_INTRO, TUTORIAL_STATE_WAITING_LEFT_CLICK,
    TUTORIAL_STATE_SHOWING_LEFT_SUCCESS, TUTORIAL_STATE_WAITING_DOUBLE_CLICK,
    TUTORIAL_STATE_SHOWING_DOUBLE_SUCCESS, TUTORIAL_STATE_WAITING_MIDDLE_CLICK,
    TUTORIAL_STATE_SHOWING_MIDDLE_SUCCESS, TUTORIAL_STATE_SHOWING_HIGHLIGHTER_INFO,
    TUTORIAL_STATE_SHOWING_CONTROLS_INFO, TUTORIAL_STATE_COMPLETE, TUTORIAL_STATE_SKIPPED,
    COLOR_IDLE, COLOR_RUN, COLOR_WARN, COLOR_ERROR, COLOR_START, COLOR_INFO_BLUE, COLOR_TUTORIAL,
    BLINK_THRESHOLD_MAP
)
from utils import (
    level_to_gap_px_static, gap_px_to_level_static,
    level_to_padding_static, padding_to_level_static, hex_to_bgr
)
from settings_manager import get_default_settings, load_profiles, save_profiles
from cursor_highlighter import CursorHighlighterWindow
from smooth_cursor import SmoothCursor

# Global Constants & Initializations
ALL_PROFILES_DATA = load_profiles()
ACTIVE_PROFILE_NAME = ALL_PROFILES_DATA.get("active_profile", "Default")
if ACTIVE_PROFILE_NAME not in ALL_PROFILES_DATA.get("profiles", {}):
    print(f"Correcting active profile: '{ACTIVE_PROFILE_NAME}' not found, using 'Default'.")
    ACTIVE_PROFILE_NAME = "Default"; ALL_PROFILES_DATA["active_profile"] = "Default"
    save_profiles(ALL_PROFILES_DATA)

SETTINGS = ALL_PROFILES_DATA.get("profiles", {}).get(ACTIVE_PROFILE_NAME, get_default_settings())
TUTORIAL_COMPLETED = ALL_PROFILES_DATA.get("tutorial_completed", False)

try: SCREEN_W, SCREEN_H = pyautogui.size()
except Exception as e_scr_size: print(f"Warning: pyautogui.size() failed: {e_scr_size}. Using fallback."); SCREEN_W, SCREEN_H = 1920, 1080

MP_FACE_MESH = mp.solutions.face_mesh


class CursorViaCamApp(QWidget):
    def __init__(self):
        super().__init__()
        self.all_profiles_data = ALL_PROFILES_DATA
        self.active_profile_name = ACTIVE_PROFILE_NAME
        self.settings = self.all_profiles_data["profiles"].get(self.active_profile_name, get_default_settings()).copy()
        self.tutorial_completed = TUTORIAL_COMPLETED
        self.smooth_cursor = SmoothCursor()
        self.cursor_highlighter = CursorHighlighterWindow()

        self.rect_padding = 0
        self.current_gap_level = 0
        self.outer_rect_gap = 0
        self.blink_threshold = 0
        self.long_blink_threshold = 0
        self.double_blink_interval = 0
        self.enable_cursor_highlight = False

        self.running = False; self._internal_tracking_active = False; self.cam = None; self.face_mesh = None
        self.was_out_of_bounds = True; self.blink_start_time = 0
        self.both_eyes_closed_start_time = 0
        self.last_both_eyes_closed_end_time = 0
        self.available_cameras = []
        self.last_valid_gaze_normalized = None

        self.timer = QTimer(self); self.timer.timeout.connect(self.update_frame)
        self.frame_processing_time = 0; self.last_frame_time = time.perf_counter()
        self.fps_history = deque(maxlen=10)

        self.error_dialog = QErrorMessage(self); self.error_dialog.setWindowTitle("CursorViaCam Error")
        self.tutorial_state = TUTORIAL_STATE_IDLE

        self.apply_settings_to_runtime()
        self.initUI()
        self.apply_settings_to_ui()
        self.cursor_highlighter.set_visibility(self.enable_cursor_highlight)

        self.center_window()
        self.initialize_dependencies()
        self.update_performance_display()
        self.update_status("Initializing", COLOR_START)

        if self.cam and self.cam.isOpened() and self.face_mesh:
            self.timer.start(15)
            self._internal_tracking_active = True
            if not self.tutorial_completed:
                QTimer.singleShot(500, self.run_tutorial)
            else:
                QTimer.singleShot(500, lambda: self.update_status("Idle", COLOR_IDLE))
                self.set_settings_controls_enabled(True)
                self.rerun_tutorial_button.setVisible(True)
                self.start_button.setEnabled(True)
                self.right_stack.setCurrentWidget(self.control_frame)
        else:
             self._internal_tracking_active = False
             error_msg = "CAM/MP Error" if not (self.cam and self.cam.isOpened() and self.face_mesh) else ("CAM Error" if not (self.cam and self.cam.isOpened()) else "MP Init Fail")
             QTimer.singleShot(500, lambda: self.update_status(error_msg, COLOR_ERROR))
             self.set_settings_controls_enabled(False)
             self.start_button.setEnabled(False)
             self.rerun_tutorial_button.setVisible(False)

    def _level_to_padding(self, level): return level_to_padding_static(level)
    def _padding_to_level(self, padding): return padding_to_level_static(padding)
    def _level_to_gap_px(self, level): return level_to_gap_px_static(level)

    def center_window(self):
        try:
            screen = QApplication.primaryScreen()
            if not screen: return
            available_geometry = screen.availableGeometry()
            window_geometry = self.frameGeometry()
            center_point = available_geometry.center()
            window_geometry.moveCenter(center_point)
            self.move(window_geometry.topLeft())
        except Exception as e: print(f"Error centering window: {e}")

    def initialize_dependencies(self):
        self.initialize_face_mesh()
        current_cam_index = self.settings.get("camera_index", 0)
        self.init_camera(current_cam_index)

    def apply_settings_to_runtime(self):
        default_settings = get_default_settings()

        self.rect_padding = self.settings.get("rect_padding", default_settings["rect_padding"])
        self.current_gap_level = self.settings.get("outer_gap_level", default_settings["outer_gap_level"])
        self.outer_rect_gap = self._level_to_gap_px(self.current_gap_level)
        self.blink_threshold = BLINK_THRESHOLD_MAP.get( self.settings.get("blink_threshold_level", default_settings["blink_threshold_level"]), BLINK_THRESHOLD_MAP[default_settings["blink_threshold_level"]])
        self.long_blink_threshold = self.settings.get("long_blink_threshold", default_settings["long_blink_threshold"])
        self.double_blink_interval = self.settings.get("double_blink_interval", default_settings["double_blink_interval"])
        self.enable_cursor_highlight = self.settings.get("enable_cursor_highlight", default_settings["enable_cursor_highlight"])

        self.smooth_cursor.set_smoothing_params(
            window=self.settings.get("smooth_window_internal", default_settings["smooth_window_internal"])
        )
        enable_sticking_setting = self.settings.get("enable_button_sticking", default_settings["enable_button_sticking"])
        self.smooth_cursor.enable_sticking = enable_sticking_setting and IS_WINDOWS
        if not self.smooth_cursor.enable_sticking: self.smooth_cursor.reset_sticking()

        if hasattr(self, 'cursor_highlighter') and self.cursor_highlighter:
             self.cursor_highlighter.set_visibility(self.enable_cursor_highlight)

    def initUI(self):
        self.setWindowTitle("CursorViaCam Control (PyQt6)")
        initial_width, initial_height = 900, 450
        self.setGeometry(100, 100, initial_width, initial_height); self.setMinimumSize(initial_width, initial_height); self.setMaximumSize(initial_width, initial_height)

        try:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(base_path, "CursorViaCam(Whightbg).ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
            else:
                print(f"Warning: Icon '{icon_path}' not found.")
        except Exception as e_icon:
            print(f"Error loading icon: {e_icon}")

        main_layout = QHBoxLayout(self); left_layout = QVBoxLayout(); right_layout = QVBoxLayout()

        self.camera_label = QLabel("Initializing Camera...")
        camera_feed_width, camera_feed_height = 540, 405
        self.camera_label.setFixedSize(camera_feed_width, camera_feed_height); self.camera_label.setStyleSheet("background-color: black; color: red; border: 1px solid gray;"); self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.camera_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        perf_layout = QHBoxLayout(); self.fps_label = QLabel("FPS: --"); self.proc_time_label = QLabel("Proc: -- ms")
        perf_layout.addWidget(self.fps_label); perf_layout.addStretch(1); perf_layout.addWidget(self.proc_time_label)
        left_layout.addLayout(perf_layout); left_layout.addStretch(1)

        self.right_stack = QStackedWidget()

        self.control_frame = QFrame(); self.control_frame.setFrameShape(QFrame.Shape.StyledPanel)
        control_layout = QVBoxLayout(self.control_frame); control_layout.setSpacing(8)

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Tracking"); self.start_button.setToolTip("Start processing camera feed and controlling the cursor.")
        self.stop_button = QPushButton("Stop Tracking"); self.stop_button.setToolTip("Stop processing camera feed and release cursor control.")
        button_style = "QPushButton { font-size: 11pt; padding: 8px; min-height: 35px; }"; self.start_button.setStyleSheet(button_style); self.stop_button.setStyleSheet(button_style)
        button_layout.addWidget(self.start_button); button_layout.addWidget(self.stop_button); control_layout.addLayout(button_layout)

        profile_frame = QFrame(); profile_frame.setFrameShape(QFrame.Shape.StyledPanel)
        profile_layout_outer = QVBoxLayout(profile_frame); profile_layout_inner = QHBoxLayout()
        profile_layout_outer.addWidget(QLabel("Profile:")); self.profile_combo = QComboBox(); self.profile_combo.setToolTip("Select the active settings profile.")
        self.save_profile_button = QPushButton("Save As..."); self.save_profile_button.setToolTip("Save current settings as a new profile")
        self.delete_profile_button = QPushButton("Delete"); self.delete_profile_button.setToolTip("Delete the selected profile (cannot delete 'Default')")
        profile_layout_inner.addWidget(self.profile_combo, 2); profile_layout_inner.addWidget(self.save_profile_button, 1); profile_layout_inner.addWidget(self.delete_profile_button, 1)
        profile_layout_outer.addLayout(profile_layout_inner); control_layout.addWidget(profile_frame)

        grid_layout = QGridLayout(); grid_layout.setVerticalSpacing(6); grid_layout.setHorizontalSpacing(10)
        grid_row = 0
        grid_layout.addWidget(QLabel("Camera:"), grid_row, 0); self.camera_selector = QComboBox(); self.camera_selector.setToolTip("Select the camera device to use for tracking.")
        self.populate_camera_selector(); grid_layout.addWidget(self.camera_selector, grid_row, 1, 1, 2); grid_row += 1
        grid_layout.addWidget(QLabel("Track Area Level:"), grid_row, 0); self.padding_slider = QSlider(Qt.Orientation.Horizontal)
        self.padding_slider.setToolTip("Adjust Track Area Level: Controls dead zone size.\nHigher level = Smaller dead zone."); self.padding_slider.setRange(MIN_TRACK_AREA_LEVEL, MAX_TRACK_AREA_LEVEL)
        self.padding_value_label = QLabel("Level -"); self.padding_value_label.setMinimumWidth(70); self.padding_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid_layout.addWidget(self.padding_slider, grid_row, 1); grid_layout.addWidget(self.padding_value_label, grid_row, 2); grid_row += 1
        grid_layout.addWidget(QLabel("Outer Gap Level:"), grid_row, 0); self.gap_level_slider = QSlider(Qt.Orientation.Horizontal)
        self.gap_level_slider.setToolTip("Adjust Outer Gap Level: Space between move/click areas."); self.gap_level_slider.setRange(MIN_GAP_LEVEL, MAX_GAP_LEVEL)
        self.gap_level_value_label = QLabel("Level -"); self.gap_level_value_label.setMinimumWidth(50); self.gap_level_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid_layout.addWidget(self.gap_level_slider, grid_row, 1); grid_layout.addWidget(self.gap_level_value_label, grid_row, 2); grid_row += 1
        grid_layout.addWidget(QLabel("Blink Sens:"), grid_row, 0); self.blink_selector = QComboBox(); self.blink_selector.setToolTip("Set sensitivity for blink detection.")
        self.blink_selector.addItems(list(BLINK_THRESHOLD_MAP.keys())); grid_layout.addWidget(self.blink_selector, grid_row, 1, 1, 2); grid_row += 1

        grid_layout.setColumnStretch(0, 0); grid_layout.setColumnStretch(1, 1); grid_layout.setColumnStretch(2, 0)
        control_layout.addLayout(grid_layout)

        checkbox_layout = QVBoxLayout(); checkbox_layout.setSpacing(4)
        self.sticking_checkbox = QCheckBox("Button Sticking (Win Only)"); self.sticking_checkbox.setToolTip("Enable cursor 'sticking' (Windows only)."); self.sticking_checkbox.setEnabled(IS_WINDOWS)
        checkbox_layout.addWidget(self.sticking_checkbox)

        self.highlight_checkbox = QCheckBox("Cursor Highlighter")
        self.highlight_checkbox.setToolTip("Show a colored ring around the cursor indicating tracking status.")
        checkbox_layout.addWidget(self.highlight_checkbox)
        control_layout.addLayout(checkbox_layout)

        control_layout.addStretch(1)

        self.rerun_tutorial_button = QPushButton("Run Tutorial"); self.rerun_tutorial_button.setToolTip("Run the setup tutorial again.")
        control_layout.addWidget(self.rerun_tutorial_button);
        self.right_stack.addWidget(self.control_frame)

        self.tutorial_widget = QWidget()
        tutorial_layout = QVBoxLayout(self.tutorial_widget)
        tutorial_layout.setContentsMargins(15, 15, 15, 15)
        tutorial_layout.setSpacing(15)

        self.tutorial_title_label = QLabel("CursorViaCam Tutorial")
        font = self.tutorial_title_label.font()
        font.setPointSize(14); font.setBold(True)
        self.tutorial_title_label.setFont(font)
        self.tutorial_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tutorial_layout.addWidget(self.tutorial_title_label)

        self.tutorial_scroll_area = QScrollArea()
        self.tutorial_scroll_area.setWidgetResizable(True)
        self.tutorial_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.tutorial_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tutorial_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.tutorial_text_label = QLabel("Tutorial instructions...")
        font = self.tutorial_text_label.font()
        font.setPointSize(11)
        self.tutorial_text_label.setFont(font)
        self.tutorial_text_label.setWordWrap(True)
        self.tutorial_text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.tutorial_text_label.setTextFormat(Qt.TextFormat.RichText)

        self.tutorial_scroll_area.setWidget(self.tutorial_text_label)

        tutorial_layout.addWidget(self.tutorial_scroll_area, 1)

        tutorial_button_layout = QHBoxLayout()
        self.tutorial_skip_button = QPushButton("Skip Tutorial")
        self.tutorial_next_button = QPushButton("Next")
        tutorial_button_layout.addWidget(self.tutorial_skip_button)
        tutorial_button_layout.addStretch(1)
        tutorial_button_layout.addWidget(self.tutorial_next_button)
        tutorial_layout.addLayout(tutorial_button_layout)

        self.right_stack.addWidget(self.tutorial_widget)

        right_layout.addWidget(self.right_stack)
        self.status_label = QLabel("Initializing"); self.status_label.setMinimumHeight(35); self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.status_label.setStyleSheet("border: 1px solid gray; border-radius: 4px; padding: 5px;")
        right_layout.addWidget(self.status_label)

        main_layout.setContentsMargins(12, 12, 12, 12); main_layout.setSpacing(15)
        main_layout.addLayout(left_layout, 5); main_layout.addLayout(right_layout, 4)
        self.setLayout(main_layout)

        self.connect_signals()
        self.populate_profile_selector()

    def populate_camera_selector(self):
        self.available_cameras = self.get_available_cameras()
        self.camera_selector.clear()
        saved_cam_index = self.settings.get("camera_index", 0)
        qt_index_to_select = -1

        if self.available_cameras:
            for i, cam_info in enumerate(self.available_cameras):
                self.camera_selector.addItem(cam_info['name'], userData=cam_info['index'])
                if cam_info['index'] == saved_cam_index:
                    qt_index_to_select = i

            if qt_index_to_select == -1 and len(self.available_cameras) > 0:
                print(f"Warning: Saved camera index {saved_cam_index} not found. Selecting first available camera.")
                qt_index_to_select = 0
                first_cam_data = self.camera_selector.itemData(0)
                if first_cam_data is not None:
                    self.settings["camera_index"] = first_cam_data

            if qt_index_to_select != -1:
                self.camera_selector.setCurrentIndex(qt_index_to_select)

            self.camera_selector.setEnabled(True)
        else:
            self.camera_selector.addItem("No Cameras Found")
            self.camera_selector.setEnabled(False)

    def get_available_cameras(self, max_to_check=5):
        available = []; print("Detecting cameras...")
        for i in range(max_to_check):
            cap_test = None; backend_name = "Default"; name = f"Camera {i}"
            preferred_api = cv2.CAP_DSHOW if IS_WINDOWS else cv2.CAP_ANY

            try:
                cap_test = cv2.VideoCapture(i, preferred_api)
                if cap_test and cap_test.isOpened():
                    backend_name = "DSHOW" if preferred_api == cv2.CAP_DSHOW else "OS Default"
                else:
                    if cap_test: cap_test.release(); cap_test = None
                    cap_test = cv2.VideoCapture(i, cv2.CAP_ANY)
                    if cap_test and cap_test.isOpened():
                        backend_name = "CAP_ANY"
                    else:
                        if cap_test: cap_test.release(); cap_test = None
                        continue

                if cap_test and cap_test.isOpened():
                    ret, frame = cap_test.read()
                    if ret and frame is not None:
                        h, w, _ = frame.shape
                        if w > 0 and h > 0:
                            available.append({'index': i, 'name': name, 'backend': backend_name}); print(f"  Found: {name} ({w}x{h})")
                        else: print(f"  Skipping {name}: Invalid resolution {w}x{h}")
                    else: print(f"  Skipping {name}: Failed to read frame")
            except Exception as e: print(f"Error checking camera {i}: {e}")
            finally:
                if cap_test and cap_test.isOpened(): cap_test.release()

        if not available: print("Warning: No cameras detected!"); self.show_error_message("No working cameras detected.")
        return available

    def show_error_message(self, message):
        if not hasattr(self, 'error_dialog') or self.error_dialog is None:
           self.error_dialog = QErrorMessage(self)
           self.error_dialog.setWindowTitle("CursorViaCam Error")
        self.error_dialog.showMessage(message)

    def connect_signals(self):
        self.start_button.clicked.connect(self.start_tracking)
        self.stop_button.clicked.connect(self.stop_tracking)
        self.profile_combo.activated.connect(self.select_profile)
        self.save_profile_button.clicked.connect(self.save_profile_as)
        self.delete_profile_button.clicked.connect(self.delete_profile)
        self.camera_selector.currentIndexChanged.connect(self.update_camera_selection)
        self.padding_slider.valueChanged.connect(self.update_padding_level_display)
        self.padding_slider.sliderReleased.connect(self.save_padding_level_setting)
        self.gap_level_slider.valueChanged.connect(self.update_gap_level_display)
        self.gap_level_slider.sliderReleased.connect(self.save_gap_level_setting)
        self.blink_selector.activated.connect(self.update_blink_threshold_selection)
        self.sticking_checkbox.stateChanged.connect(self.toggle_sticking)
        self.highlight_checkbox.stateChanged.connect(self.toggle_highlight)
        self.rerun_tutorial_button.clicked.connect(lambda: self.run_tutorial())
        self.tutorial_skip_button.clicked.connect(self.mark_tutorial_skipped)

    def apply_settings_to_ui(self):
        self.block_setting_signals(True)

        profile_index = self.profile_combo.findText(self.active_profile_name)
        if profile_index != -1: self.profile_combo.setCurrentIndex(profile_index)
        self.delete_profile_button.setEnabled(self.active_profile_name != "Default")

        saved_cam_index = self.settings.get("camera_index", 0)
        qt_cam_idx_to_select = self.camera_selector.findData(saved_cam_index)
        if qt_cam_idx_to_select != -1:
            self.camera_selector.setCurrentIndex(qt_cam_idx_to_select)
        elif self.camera_selector.count() > 0:
             print(f"Warning: Saved camera index {saved_cam_index} not found in UI selector. Setting UI to first.")
             self.camera_selector.setCurrentIndex(0)

        current_padding = self.settings.get("rect_padding", DEFAULT_PADDING_VALUE)
        level_padding = self._padding_to_level(current_padding)
        self.padding_slider.setValue(level_padding)
        self.padding_value_label.setText(f"Level {level_padding}")

        level_gap = self.settings.get('outer_gap_level', DEFAULT_GAP_LEVEL)
        self.gap_level_slider.setValue(level_gap)
        self.gap_level_value_label.setText(f"Level {level_gap}")

        blink_level_str = self.settings.get("blink_threshold_level", "Medium")
        blink_idx = self.blink_selector.findText(blink_level_str)
        if blink_idx != -1: self.blink_selector.setCurrentIndex(blink_idx)
        else: self.blink_selector.setCurrentIndex(self.blink_selector.findText("Medium"))

        enable_sticking = self.settings.get("enable_button_sticking", IS_WINDOWS) and IS_WINDOWS
        self.sticking_checkbox.setChecked(enable_sticking)
        self.sticking_checkbox.setEnabled(IS_WINDOWS)

        enable_highlight = self.settings.get("enable_cursor_highlight", False)
        self.highlight_checkbox.setChecked(enable_highlight)

        self.block_setting_signals(False)

    def block_setting_signals(self, block):
        widgets_to_block = [
            self.padding_slider, self.gap_level_slider,
            self.blink_selector, self.sticking_checkbox, self.highlight_checkbox,
            self.camera_selector, self.profile_combo,
        ]
        for widget in widgets_to_block:
            if widget:
                try: widget.blockSignals(block)
                except Exception as e: print(f"Error blocking signals for {widget}: {e}")

    def populate_profile_selector(self):
        self.block_setting_signals(True); self.profile_combo.clear()

        if not self.all_profiles_data.get("profiles"):
            print("No profiles found, creating default.")
            self.all_profiles_data["profiles"] = {"Default": get_default_settings()}
            self.all_profiles_data["active_profile"] = "Default"; self.active_profile_name = "Default"
            save_profiles(self.all_profiles_data)

        profile_names = sorted(self.all_profiles_data["profiles"].keys()); self.profile_combo.addItems(profile_names)

        active_index = self.profile_combo.findText(self.active_profile_name)
        if active_index != -1:
            self.profile_combo.setCurrentIndex(active_index)
        elif profile_names:
            print(f"Warning: Active profile '{self.active_profile_name}' not in list. Selecting '{profile_names[0]}'.")
            self.active_profile_name = profile_names[0]
            self.all_profiles_data["active_profile"] = self.active_profile_name
            self.settings = self.all_profiles_data["profiles"].get(self.active_profile_name, get_default_settings()).copy()
            self.profile_combo.setCurrentIndex(0)
            save_profiles(self.all_profiles_data)
        else: print("Error: No profiles available after attempting default creation.")

        self.delete_profile_button.setEnabled(self.active_profile_name != "Default")
        self.block_setting_signals(False)

    def select_profile(self, index):
        if not self._is_ok_to_change_settings():
             self.block_setting_signals(True)
             current_profile_idx = self.profile_combo.findText(self.active_profile_name)
             if current_profile_idx != -1: self.profile_combo.setCurrentIndex(current_profile_idx)
             self.block_setting_signals(False)
             return

        selected_profile_name = self.profile_combo.itemText(index)
        if not selected_profile_name or selected_profile_name == self.active_profile_name: return

        print(f"Switching to profile: {selected_profile_name}")

        self.update_settings_from_runtime()
        if self.active_profile_name in self.all_profiles_data["profiles"]:
            self.all_profiles_data["profiles"][self.active_profile_name] = self.settings.copy()
        else:
            print(f"Warning: Outgoing active profile '{self.active_profile_name}' not found in data. Cannot save its state.")

        self.active_profile_name = selected_profile_name
        self.all_profiles_data["active_profile"] = self.active_profile_name
        self.settings = self.all_profiles_data["profiles"].get(self.active_profile_name, get_default_settings()).copy()

        self.apply_settings_to_runtime()
        self.apply_settings_to_ui()

        self._check_and_handle_camera_change_for_profile()

        save_profiles(self.all_profiles_data)

        self.update_status(f"Profile '{self.active_profile_name}' loaded", COLOR_IDLE)
        self.delete_profile_button.setEnabled(self.active_profile_name != "Default")

    def save_profile_as(self):
        if not self._is_ok_to_change_settings(): return
        profile_name, ok = QInputDialog.getText(self, "Save Profile As", "Enter profile name:")
        if ok and profile_name:
            profile_name = profile_name.strip()
            if not profile_name: QMessageBox.warning(self, "Invalid Name", "Profile name cannot be empty."); return

            if profile_name in self.all_profiles_data["profiles"] and profile_name != "Default":
                 reply = QMessageBox.question(self, "Profile Exists", f"Overwrite existing profile '{profile_name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                 if reply == QMessageBox.StandardButton.No: return

            self.update_settings_from_runtime()
            self.all_profiles_data["profiles"][profile_name] = self.settings.copy()
            self.active_profile_name = profile_name
            self.all_profiles_data["active_profile"] = profile_name
            save_profiles(self.all_profiles_data)
            self.populate_profile_selector()
            self.update_status(f"Profile '{profile_name}' saved", COLOR_IDLE)
        elif ok and not profile_name:
            QMessageBox.warning(self, "Invalid Name", "Profile name cannot be empty.")

    def delete_profile(self):
        if not self._is_ok_to_change_settings(): return
        profile_to_delete = self.profile_combo.currentText()

        if profile_to_delete == "Default":
            QMessageBox.warning(self, "Cannot Delete", "'Default' profile cannot be deleted."); return
        if not profile_to_delete or profile_to_delete not in self.all_profiles_data["profiles"]:
             QMessageBox.warning(self, "Error", f"Cannot delete invalid profile '{profile_to_delete}'."); self.populate_profile_selector(); return

        reply = QMessageBox.question(self, "Confirm Delete", f"Delete profile '{profile_to_delete}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            del self.all_profiles_data["profiles"][profile_to_delete]
            self.active_profile_name = "Default"; self.all_profiles_data["active_profile"] = "Default"
            self.settings = self.all_profiles_data["profiles"].get("Default", get_default_settings()).copy()
            save_profiles(self.all_profiles_data)
            self.populate_profile_selector()
            self.apply_settings_to_runtime()
            self.apply_settings_to_ui()
            self._check_and_handle_camera_change_for_profile()
            self.update_status(f"Profile '{profile_to_delete}' deleted", COLOR_IDLE)

    def _is_ok_to_change_settings(self):
        is_tutorial_active = not (self.tutorial_state == TUTORIAL_STATE_IDLE or
                               self.tutorial_state == TUTORIAL_STATE_COMPLETE or
                               self.tutorial_state == TUTORIAL_STATE_SKIPPED)
        if is_tutorial_active:
             return False
        return True

    def _check_and_handle_camera_change_for_profile(self):
        new_cam_index_setting = self.settings.get("camera_index")

        current_qt_cam_idx = self.camera_selector.currentIndex()
        current_cam_runtime_index = None
        if current_qt_cam_idx >= 0:
            current_cam_runtime_index = self.camera_selector.itemData(current_qt_cam_idx)

        if new_cam_index_setting is not None and new_cam_index_setting != current_cam_runtime_index:
            print(f"Profile load indicates camera change needed (Current UI: {current_cam_runtime_index}, New Profile Setting: {new_cam_index_setting}).")
            new_qt_idx = self.camera_selector.findData(new_cam_index_setting)
            if new_qt_idx != -1:
                 if self.camera_selector.currentIndex() != new_qt_idx:
                     print("Forcing camera change based on profile setting.")
                     self.handle_camera_change(new_qt_idx, called_internally=True)
                 else:
                     print("Camera index already correctly set in UI by profile load.")
                     if not (self.cam and self.cam.isOpened()):
                          print("Camera not open, attempting re-initialization based on profile.")
                          self.handle_camera_change(new_qt_idx, called_internally=True)
            else:
                 print(f"Warning: Camera index {new_cam_index_setting} from profile not found in available cameras.")
                 if current_cam_runtime_index is not None:
                     self.settings["camera_index"] = current_cam_runtime_index
                     print(f"Reverted profile camera index setting in memory to current UI index: {current_cam_runtime_index}")
                     self.save_current_profile_settings()
                 elif self.camera_selector.count() > 0:
                     first_cam_data = self.camera_selector.itemData(0)
                     if first_cam_data is not None:
                         self.settings["camera_index"] = first_cam_data
                         self.camera_selector.blockSignals(True)
                         self.camera_selector.setCurrentIndex(0)
                         self.camera_selector.blockSignals(False)
                         print(f"Reverted profile camera index setting in memory to first available index: {first_cam_data}")
                         self.save_current_profile_settings()

    def update_camera_selection(self, qt_index):
        if not self.camera_selector.signalsBlocked():
            if not self._is_ok_to_change_settings():
                QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before changing settings.")
                saved_cam_index = self.settings.get("camera_index", 0)
                previous_qt_idx = self.camera_selector.findData(saved_cam_index)
                if previous_qt_idx != -1:
                    self.camera_selector.blockSignals(True)
                    self.camera_selector.setCurrentIndex(previous_qt_idx)
                    self.camera_selector.blockSignals(False)
                return

            self.handle_camera_change(qt_index, called_internally=False)

    def handle_camera_change(self, qt_index, called_internally=False):
        if not called_internally and not self._is_ok_to_change_settings():
            return

        if qt_index < 0 or qt_index >= self.camera_selector.count():
             print(f"Camera change ignored: Invalid Qt index {qt_index}")
             return
        actual_cam_index = self.camera_selector.itemData(qt_index)
        if actual_cam_index is None:
             print(f"Camera change ignored: No data for Qt index {qt_index}")
             return
        selected_cam_info = next((c for c in self.available_cameras if c['index'] == actual_cam_index), None)
        if not selected_cam_info:
             print(f"Camera change ignored: Camera info not found for index {actual_cam_index}")
             return

        current_setting_cam_index = self.settings.get("camera_index", -1)

        if actual_cam_index == current_setting_cam_index and self.cam and self.cam.isOpened() and self._internal_tracking_active:
            return
        elif actual_cam_index == current_setting_cam_index:
             print(f"Camera index {actual_cam_index} selected, but camera not open. Attempting initialization.")

        was_running = self.running
        if self.running: self.stop_tracking()

        print(f"Switching camera to index {actual_cam_index} ({selected_cam_info['name']})...")
        selected_backend_name = selected_cam_info.get('backend', 'Default')

        if self.init_camera(actual_cam_index, preferred_backend=selected_backend_name):
            print(f"Camera {actual_cam_index} initialized successfully.")
            self.settings["camera_index"] = actual_cam_index
            if not called_internally:
                 self.save_current_profile_settings()
            elif called_internally and current_setting_cam_index != actual_cam_index:
                 print("Saving corrected camera index from profile load.")
                 self.save_current_profile_settings()

            self.update_status("Camera Changed", COLOR_IDLE)
            self._internal_tracking_active = True
            if not self.timer.isActive(): self.timer.start(15)
            if was_running and self._is_ok_to_change_settings():
                QTimer.singleShot(100, self.start_tracking)
            elif self._is_ok_to_change_settings():
                 self.start_button.setEnabled(True)
        else:
            print(f"Failed to initialize camera {actual_cam_index}.")
            self.update_status("CAM SWITCH FAIL!", COLOR_ERROR)
            self.display_error_on_feed(f"Failed to Open\n{selected_cam_info['name']}")
            self.show_error_message(f"Failed to open camera: {selected_cam_info['name']}")
            self._internal_tracking_active = False
            self.start_button.setEnabled(False)
            if self.timer.isActive(): self.timer.stop()

            previous_qt_idx = self.camera_selector.findData(current_setting_cam_index)
            if previous_qt_idx != -1 and current_setting_cam_index != actual_cam_index:
                print(f"Attempting to revert UI to previous camera {current_setting_cam_index}.")
                self.camera_selector.blockSignals(True)
                self.camera_selector.setCurrentIndex(previous_qt_idx)
                self.camera_selector.blockSignals(False)
            else:
                 if not called_internally:
                      self.settings["camera_index"] = actual_cam_index
                      self.save_current_profile_settings()

    def update_padding_level_display(self, level):
        if not self.padding_slider.signalsBlocked():
            if not self._is_ok_to_change_settings():
                 self.padding_slider.blockSignals(True)
                 level_padding = self._padding_to_level(self.settings.get("rect_padding", DEFAULT_PADDING_VALUE))
                 self.padding_slider.setValue(level_padding)
                 self.padding_slider.blockSignals(False)
                 return

            self.rect_padding = self._level_to_padding(level)
            self.padding_value_label.setText(f"Level {level}")

    def save_padding_level_setting(self):
        if not self.padding_slider.signalsBlocked():
            if not self._is_ok_to_change_settings():
                 QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before changing settings.")
                 self.padding_slider.blockSignals(True)
                 level_padding = self._padding_to_level(self.settings.get("rect_padding", DEFAULT_PADDING_VALUE))
                 self.padding_slider.setValue(level_padding)
                 self.padding_value_label.setText(f"Level {level_padding}")
                 self.padding_slider.blockSignals(False)
                 return
            level = self.padding_slider.value()
            self.settings["rect_padding"] = self._level_to_padding(level)
            self.apply_settings_to_runtime()
            self.save_current_profile_settings()

    def update_gap_level_display(self, level):
        if not self.gap_level_slider.signalsBlocked():
            if not self._is_ok_to_change_settings():
                 self.gap_level_slider.blockSignals(True)
                 level_gap = self.settings.get('outer_gap_level', DEFAULT_GAP_LEVEL)
                 self.gap_level_slider.setValue(level_gap)
                 self.gap_level_slider.blockSignals(False)
                 return

            self.current_gap_level = level
            self.outer_rect_gap = self._level_to_gap_px(level)
            self.gap_level_value_label.setText(f"Level {level}")

    def save_gap_level_setting(self):
        if not self.gap_level_slider.signalsBlocked():
            if not self._is_ok_to_change_settings():
                 QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before changing settings.")
                 self.gap_level_slider.blockSignals(True)
                 level_gap = self.settings.get('outer_gap_level', DEFAULT_GAP_LEVEL)
                 self.gap_level_slider.setValue(level_gap)
                 self.gap_level_value_label.setText(f"Level {level_gap}")
                 self.gap_level_slider.blockSignals(False)
                 return
            level = self.gap_level_slider.value()
            self.settings["outer_gap_level"] = level
            self.apply_settings_to_runtime()
            self.save_current_profile_settings()

    def update_blink_threshold_selection(self, index):
        if not self.blink_selector.signalsBlocked():
            if not self._is_ok_to_change_settings():
                 QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before changing settings.")
                 current_blink_level = self.settings.get("blink_threshold_level", "Medium")
                 self.blink_selector.blockSignals(True)
                 self.blink_selector.setCurrentText(current_blink_level)
                 self.blink_selector.blockSignals(False)
                 return

            selection = self.blink_selector.currentText()
            if selection in BLINK_THRESHOLD_MAP:
                self.settings["blink_threshold_level"] = selection
                self.apply_settings_to_runtime()
                self.save_current_profile_settings()

    def toggle_sticking(self, state_int):
        if not self.sticking_checkbox.signalsBlocked():
            if state_int == 1: return
            enabled = (state_int == Qt.CheckState.Checked.value)

            if not IS_WINDOWS and enabled:
                self.sticking_checkbox.blockSignals(True)
                self.sticking_checkbox.setChecked(False)
                self.sticking_checkbox.blockSignals(False)
                enabled = False
                self.show_error_message("Button Sticking is only available on Windows.")

            self.settings["enable_button_sticking"] = enabled
            self.apply_settings_to_runtime()
            self.save_current_profile_settings()

    def toggle_highlight(self, state_int):
        if not self.highlight_checkbox.signalsBlocked():
            if state_int == 1: return
            enabled = (state_int == Qt.CheckState.Checked.value)

            if not self._is_ok_to_change_settings():
                 QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before changing settings.")
                 self.highlight_checkbox.blockSignals(True)
                 current_highlight_setting = self.settings.get("enable_cursor_highlight", False)
                 self.highlight_checkbox.setChecked(current_highlight_setting)
                 self.highlight_checkbox.blockSignals(False)
                 return

            self.enable_cursor_highlight = enabled
            self.cursor_highlighter.set_visibility(enabled)

            if enabled:
                 try:
                     x, y = pyautogui.position()
                     self.cursor_highlighter.update_position(x, y)
                     status_color_hex = COLOR_IDLE
                     is_tutorial_running = not (self.tutorial_state == TUTORIAL_STATE_IDLE or
                                            self.tutorial_state == TUTORIAL_STATE_COMPLETE or
                                            self.tutorial_state == TUTORIAL_STATE_SKIPPED)
                     if is_tutorial_running:
                         status_color_hex = COLOR_TUTORIAL
                     elif self.running:
                         status_text = self.status_label.text().lower()
                         if "tracking" in status_text: status_color_hex = COLOR_RUN
                         elif "bound" in status_text: status_color_hex = COLOR_WARN
                         elif "face" in status_text: status_color_hex = COLOR_ERROR
                         elif "err" in status_text or "fail" in status_text: status_color_hex = COLOR_ERROR
                         else: status_color_hex = COLOR_RUN
                     elif not self._internal_tracking_active:
                         status_color_hex = COLOR_ERROR
                     else:
                         status_color_hex = COLOR_IDLE

                     self.cursor_highlighter.update_color(QColor(status_color_hex))

                 except Exception as e:
                     print(f"Error getting initial cursor pos for highlight: {e}")

            self.settings["enable_cursor_highlight"] = enabled
            self.save_current_profile_settings()

    def initialize_face_mesh(self):
        if self.face_mesh:
            try: self.face_mesh.close(); self.face_mesh = None
            except Exception as e: print(f"Error closing previous FaceMesh: {e}")
        print("Initializing MediaPipe Face Mesh..."); self.face_mesh = None
        try:
            self.face_mesh = MP_FACE_MESH.FaceMesh(max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.6, min_tracking_confidence=0.6)
            print("Face Mesh Initialized.")
        except Exception as e:
            print(f"FATAL: Error initializing FaceMesh: {e}"); self.face_mesh = None
            self.show_error_message(f"Failed to initialize MediaPipe Face Mesh:\n{e}\nTracking disabled.")

    def init_camera(self, index, preferred_backend="Default"):
        if self.cam and self.cam.isOpened():
            print("Releasing previous camera..."); self.cam.release(); self.cam = None

        print(f"Attempting camera index {index} (Preferred Backend: {preferred_backend})...")
        self.cam = None; success = False
        backends_to_try = []
        if IS_WINDOWS: backends_to_try.append((cv2.CAP_DSHOW, "DSHOW"))
        backends_to_try.append((cv2.CAP_ANY, "CAP_ANY"))

        for api, backend_str in backends_to_try:
            if preferred_backend != "Default" and api == cv2.CAP_ANY and any(b[1] == preferred_backend for b in backends_to_try):
                 if self.cam is None:
                     pass
                 else: pass

            print(f"  Trying backend: {backend_str} ({api})")
            try:
                self.cam = cv2.VideoCapture(index, api)
                if self.cam and self.cam.isOpened():
                    ret_test, frame_test = self.cam.read()
                    if not ret_test or frame_test is None:
                        print(f"    Backend {backend_str}: Failed initial frame read.")
                        self.cam.release(); self.cam = None; continue
                    h, w, _ = frame_test.shape
                    if w <= 0 or h <= 0:
                        print(f"    Backend {backend_str}: Invalid resolution {w}x{h}.")
                        self.cam.release(); self.cam = None; continue
                    print(f"    Camera {index} OK ({w}x{h}). Using Backend: {backend_str}")
                    success = True; break
                else:
                    print(f"    Backend {backend_str}: Failed to open.")
                    if self.cam: self.cam.release(); self.cam = None;
            except Exception as e_cam_try:
                print(f"    Backend {backend_str}: Error during init/read: {e_cam_try}")
                if self.cam: self.cam.release(); self.cam = None;

        if not success:
            print(f"Error: Failed to open camera {index} with all attempted backends.")
            return False
        return True

    def update_status(self, text, color_hex):
        try:
            r, g, b = int(color_hex[1:3], 16), int(color_hex[3:5], 16), int(color_hex[5:7], 16)
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            text_color = "black" if luminance > 0.5 else "white"
        except Exception: text_color = "white"

        style = f"QLabel {{ background-color: {color_hex}; color: {text_color}; border: 1px solid #333333; border-radius: 4px; padding: 5px; font-weight: bold; font-size: 11pt; }}"

        is_tutorial_running = not (
            self.tutorial_state == TUTORIAL_STATE_IDLE or
            self.tutorial_state == TUTORIAL_STATE_COMPLETE or
            self.tutorial_state == TUTORIAL_STATE_SKIPPED
        )

        if is_tutorial_running:
            tut_style = f"QLabel {{ background-color: {COLOR_TUTORIAL}; color: black; border: 1px solid #333333; border-radius: 4px; padding: 5px; font-weight: bold; font-size: 11pt; }}"
            self.status_label.setText("Tutorial Active")
            self.status_label.setStyleSheet(tut_style)
            if self.enable_cursor_highlight and self.cursor_highlighter:
                 self.cursor_highlighter.update_color(QColor(COLOR_TUTORIAL))
            return

        self.status_label.setText(text)
        self.status_label.setStyleSheet(style)

        if self.enable_cursor_highlight and self.cursor_highlighter:
            self.cursor_highlighter.update_color(QColor(color_hex))

    def update_performance_display(self):
        now = time.perf_counter(); elapsed = now - self.last_frame_time; self.last_frame_time = now
        if elapsed > 1e-6:
            current_fps = 1.0 / elapsed; self.fps_history.append(current_fps)
            avg_fps = sum(self.fps_history) / len(self.fps_history); self.fps_label.setText(f"FPS: {avg_fps:.1f}")
        self.proc_time_label.setText(f"Proc: {self.frame_processing_time:.1f} ms")

    def start_tracking(self):
        if not self._is_ok_to_change_settings():
            QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before starting tracking.")
            return
        if self.running: return
        if not (self.cam and self.cam.isOpened() and self.face_mesh and self._internal_tracking_active):
            self.update_status("System Not Ready", COLOR_ERROR); self.show_error_message("Cannot start: Camera or MediaPipe not ready."); return

        print("Tracking started.")
        self.running = True
        self.start_button.setEnabled(False); self.stop_button.setEnabled(True)
        self.set_settings_controls_enabled(False); self.rerun_tutorial_button.setVisible(False)
        self.update_status("Starting...", COLOR_START)
        self.smooth_cursor.last_smoothed_gaze_target = None; self.smooth_cursor.last_raw_position = None
        self.smooth_cursor.position_history.clear(); self.smooth_cursor.reset_sticking()
        self.blink_start_time = 0; self.both_eyes_closed_start_time = 0
        self.last_both_eyes_closed_end_time = 0
        self.was_out_of_bounds = True; self.last_valid_gaze_normalized = None
        QTimer.singleShot(200, lambda: self.update_status("Tracking", COLOR_RUN) if self.running else None)

    def stop_tracking(self):
        if not self.running: return
        print("Tracking stopped."); self.running = False
        can_start_again = (self.cam and self.cam.isOpened() and self.face_mesh and self._internal_tracking_active)
        self.start_button.setEnabled(can_start_again); self.stop_button.setEnabled(False)
        is_tutorial_finished_or_idle = self._is_ok_to_change_settings()
        if is_tutorial_finished_or_idle:
            self.set_settings_controls_enabled(True); self.rerun_tutorial_button.setVisible(True)
            self.update_status("Idle", COLOR_IDLE if can_start_again else COLOR_ERROR)
        else:
            self.set_settings_controls_enabled(False); self.rerun_tutorial_button.setVisible(False)
            self.update_status("Tutorial Active", COLOR_TUTORIAL)

        self.smooth_cursor.reset_sticking(); self.was_out_of_bounds = True; self.both_eyes_closed_start_time = 0
        self.blink_start_time = 0; self.last_both_eyes_closed_end_time = 0
        if self.enable_cursor_highlight and self.cursor_highlighter:
             idle_color = COLOR_ERROR if not can_start_again else COLOR_IDLE
             if not is_tutorial_finished_or_idle:
                 idle_color = COLOR_TUTORIAL
             self.cursor_highlighter.update_color(QColor(idle_color))

    def set_settings_controls_enabled(self, enabled):
        widgets_to_toggle = [
            self.profile_combo, self.save_profile_button, self.delete_profile_button,
            self.camera_selector, self.padding_slider, self.gap_level_slider,
            self.blink_selector, self.sticking_checkbox, self.highlight_checkbox,
            self.padding_value_label, self.gap_level_value_label
        ]
        camera_available = self.camera_selector.count() > 0 and "No Cameras Found" not in self.camera_selector.itemText(0)
        self.camera_selector.setEnabled(enabled and camera_available)

        for widget in widgets_to_toggle:
            if widget == self.camera_selector: continue
            if widget:
                can_enable_widget = enabled and (IS_WINDOWS if widget == self.sticking_checkbox else True)
                try: widget.setEnabled(can_enable_widget)
                except Exception as e: print(f"Error setting enabled state for {widget}: {e}")

        if enabled:
             is_default_profile = (self.profile_combo.currentText() == "Default")
             if self.delete_profile_button: self.delete_profile_button.setEnabled(not is_default_profile)

    def update_frame(self):
        start_time_frame = time.perf_counter()
        self.update_performance_display()

        is_tutorial_active = not (
            self.tutorial_state == TUTORIAL_STATE_IDLE or
            self.tutorial_state == TUTORIAL_STATE_COMPLETE or
            self.tutorial_state == TUTORIAL_STATE_SKIPPED
        )

        if not self._internal_tracking_active:
            if self.running: self.stop_tracking()
            if not is_tutorial_active:
                current_status_text = self.status_label.text()
                sys_error_detected = (
                    "CAM/MP Error" in current_status_text or
                    "CAM Error" in current_status_text or
                    "MP Init Fail" in current_status_text or
                    "System Not Ready" in current_status_text
                )
                if not sys_error_detected:
                    error_msg = "System Not Ready"
                    if not (self.cam and self.cam.isOpened() and self.face_mesh): error_msg = "CAM/MP Error"
                    elif not (self.cam and self.cam.isOpened()): error_msg = "CAM Error"
                    elif not self.face_mesh: error_msg = "MP Init Fail"
                    self.update_status(error_msg, COLOR_ERROR)
                if self.enable_cursor_highlight: self.cursor_highlighter.update_color(QColor(COLOR_ERROR))
            return
        if not (self.cam and self.cam.isOpened()):
             if self.running: self.stop_tracking()
             self._internal_tracking_active = False
             if not is_tutorial_active:
                 if "CAM ERROR!" not in self.status_label.text():
                     self.update_status("CAM ERROR!", COLOR_ERROR); self.display_error_on_feed("No Camera Feed")
                 self.start_button.setEnabled(False)
                 if self.enable_cursor_highlight: self.cursor_highlighter.update_color(QColor(COLOR_ERROR))
             return
        if not self.face_mesh:
             if self.running: self.stop_tracking()
             self._internal_tracking_active = False
             if not is_tutorial_active:
                 if "MP Init Fail!" not in self.status_label.text():
                     self.update_status("MP Init Fail!", COLOR_ERROR); self.display_error_on_feed("MediaPipe Error")
                 self.start_button.setEnabled(False)
                 if self.enable_cursor_highlight: self.cursor_highlighter.update_color(QColor(COLOR_ERROR))
             return

        try:
            ret, frame = self.cam.read()
            if not ret or frame is None:
                 if not is_tutorial_active:
                     if "Frame Read Err" not in self.status_label.text():
                         self.update_status("Frame Read Err", COLOR_ERROR); self.display_error_on_feed("Frame Read Fail")
                     if self.enable_cursor_highlight: self.cursor_highlighter.update_color(QColor(COLOR_ERROR))
                 return

            frame = cv2.flip(frame, 1); frame_h, frame_w, _ = frame.shape
            if frame_h <= 0 or frame_w <= 0: return

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB); rgb_frame.flags.writeable = False
            output = self.face_mesh.process(rgb_frame); rgb_frame.flags.writeable = True
            bgr_frame_draw = frame

        except Exception as e:
            print(f"Error in frame read/MP process: {e}")
            if not is_tutorial_active:
                if "Process Error" not in self.status_label.text(): self.update_status("Process Error", COLOR_WARN)
                if self.enable_cursor_highlight: self.cursor_highlighter.update_color(QColor(COLOR_WARN))
            self.last_valid_gaze_normalized = None
            self.display_frame(frame if 'frame' in locals() and frame is not None else None)
            return

        rect_left = max(0, self.rect_padding); rect_right = min(frame_w - 1, frame_w - self.rect_padding)
        rect_top = max(0, self.rect_padding); rect_bottom = min(frame_h - 1, frame_h - self.rect_padding)
        rect_valid = (rect_right > rect_left and rect_bottom > rect_top)
        outer_left = max(0, rect_left - self.outer_rect_gap); outer_top = max(0, rect_top - self.outer_rect_gap)
        outer_right = min(frame_w - 1, rect_right + self.outer_rect_gap); outer_bottom = min(frame_h - 1, rect_bottom + self.outer_rect_gap)
        outer_valid = (outer_right > outer_left and outer_bottom > outer_top)

        face_detected = False; target_x_px, target_y_px = -1, -1; mid_x_norm, mid_y_norm = -1.0, -1.0
        left_click, mid_click, double_click = False, False, False
        gaze_in_click_bounds = False

        in_movement_bounds = False

        if output.multi_face_landmarks:
            face_detected = True
            landmarks = output.multi_face_landmarks[0].landmark
            l_iris_idx, r_iris_idx = 473, 468
            l_top, l_bot, r_top, r_bot = 159, 145, 386, 374
            max_lmk = max(l_iris_idx, r_iris_idx, l_top, l_bot, r_top, r_bot)

            if len(landmarks) > max_lmk:
                try:
                    l_cx, l_cy = landmarks[l_iris_idx].x, landmarks[l_iris_idx].y; r_cx, r_cy = landmarks[r_iris_idx].x, landmarks[r_iris_idx].y
                    mid_x_norm, mid_y_norm = (l_cx + r_cx) / 2, (l_cy + r_cy) / 2
                    self.last_valid_gaze_normalized = (mid_x_norm, mid_y_norm)
                    target_x_px = int(mid_x_norm * frame_w); target_y_px = int(mid_y_norm * frame_h)
                    target_x_px = max(0, min(target_x_px, frame_w - 1)); target_y_px = max(0, min(target_y_px, frame_h - 1))
                    in_movement_bounds = rect_valid and (rect_left <= target_x_px <= rect_right and rect_top <= target_y_px <= rect_bottom)
                    gaze_in_click_bounds = outer_valid and target_x_px != -1 and (outer_left <= target_x_px <= outer_right and outer_top <= target_y_px <= outer_bottom)

                except (IndexError, TypeError) as e_gaze:
                     self.last_valid_gaze_normalized = None; target_x_px, target_y_px = -1,-1; mid_x_norm, mid_y_norm = -1.0, -1.0
                     in_movement_bounds = False
                     gaze_in_click_bounds = False

                if self.running and not is_tutorial_active and mid_x_norm != -1.0:
                    screen_x, screen_y = -1.0, -1.0
                    if in_movement_bounds:
                        if self.was_out_of_bounds:
                             self.smooth_cursor.position_history.clear(); self.smooth_cursor.last_smoothed_gaze_target = None; self.smooth_cursor.last_raw_position = None;
                        effective_left = rect_left + EDGE_MAP_MARGIN_PX; effective_right = rect_right - EDGE_MAP_MARGIN_PX
                        effective_top = rect_top + EDGE_MAP_MARGIN_PX; effective_bottom = rect_bottom - EDGE_MAP_MARGIN_PX
                        if effective_right > effective_left and effective_bottom > effective_top:
                            effective_range_x = float(effective_right - effective_left); effective_range_y = float(effective_bottom - effective_top)
                            norm_x_raw = (float(target_x_px) - effective_left) / effective_range_x; norm_y_raw = (float(target_y_px) - effective_top) / effective_range_y
                            norm_x = max(0.0, min(1.0, norm_x_raw)); norm_y = max(0.0, min(1.0, norm_y_raw))
                            screen_x = norm_x * float(SCREEN_W); screen_y = norm_y * float(SCREEN_H)
                        else:
                            range_x, range_y = float(rect_right - rect_left), float(rect_bottom - rect_top)
                            if range_x > 0 and range_y > 0:
                                norm_x = max(0.0, min(1.0, (float(target_x_px) - rect_left) / range_x)); norm_y = max(0.0, min(1.0, (float(target_y_px) - rect_top) / range_y))
                                screen_x = norm_x * float(SCREEN_W); screen_y = norm_y * float(SCREEN_H)
                        self.was_out_of_bounds = False
                    else:
                         self.was_out_of_bounds = True; self.smooth_cursor.reset_sticking()

                    if screen_x != -1.0 and screen_y != -1.0:
                        screen_x = max(0.0, min(screen_x, float(SCREEN_W - 1))); screen_y = max(0.0, min(screen_y, float(SCREEN_H - 1)))
                        self.smooth_cursor.update_position(np.array([screen_x, screen_y]))
                elif not self.running and not is_tutorial_active:
                     pass

                if self._internal_tracking_active:
                    try:
                        l_y_top, l_y_bot = landmarks[l_top].y, landmarks[l_bot].y; r_y_top, r_y_bot = landmarks[r_top].y, landmarks[r_bot].y
                        l_v_dist = abs(l_y_top - l_y_bot); r_v_dist = abs(r_y_top - r_y_bot)
                        is_l_closed = l_v_dist < self.blink_threshold; is_r_closed = r_v_dist < self.blink_threshold
                        currently_both_closed = is_l_closed and is_r_closed
                        current_time = time.time()

                        if currently_both_closed:
                            if self.both_eyes_closed_start_time == 0:
                                self.both_eyes_closed_start_time = current_time
                                if self.last_both_eyes_closed_end_time != 0 and (current_time - self.last_both_eyes_closed_end_time) <= self.double_blink_interval and gaze_in_click_bounds:
                                    double_click = True
                                    self.both_eyes_closed_start_time = 0
                                    self.last_both_eyes_closed_end_time = 0
                        else:
                            if self.both_eyes_closed_start_time != 0:
                                duration_both_closed = current_time - self.both_eyes_closed_start_time
                                self.last_both_eyes_closed_end_time = current_time

                                if not double_click and duration_both_closed >= MIDDLE_CLICK_HOLD_DURATION and gaze_in_click_bounds:
                                    mid_click = True
                                    self.both_eyes_closed_start_time = 0
                                    self.last_both_eyes_closed_end_time = 0
                                else:
                                    self.both_eyes_closed_start_time = 0

                        if not double_click and not mid_click:
                             if is_l_closed and not is_r_closed:
                                 if self.blink_start_time == 0: self.blink_start_time = current_time
                             else:
                                 if self.blink_start_time != 0:
                                     duration = current_time - self.blink_start_time
                                     blink_ended_in_bounds = gaze_in_click_bounds

                                     if blink_ended_in_bounds and duration >= self.long_blink_threshold:
                                         left_click = True

                                     self.blink_start_time = 0

                    except (IndexError, TypeError) as e_blink:
                         print(f"Click logic error: {e_blink}")
                         self.blink_start_time=0; self.both_eyes_closed_start_time=0; self.last_both_eyes_closed_end_time = 0

            else:
                 face_detected = True
                 self.last_valid_gaze_normalized = None
                 in_movement_bounds = False
                 gaze_in_click_bounds = False
                 self.blink_start_time=0; self.both_eyes_closed_start_time=0; self.last_both_eyes_closed_end_time = 0
                 self.was_out_of_bounds = True; self.smooth_cursor.reset_sticking()
        else:
            face_detected = False
            self.last_valid_gaze_normalized = None
            in_movement_bounds = False
            gaze_in_click_bounds = False
            self.blink_start_time=0; self.both_eyes_closed_start_time=0; self.last_both_eyes_closed_end_time = 0
            self.was_out_of_bounds = True; self.smooth_cursor.reset_sticking()

        desired_status_text = ""
        desired_status_color = ""
        if self._internal_tracking_active:
            desired_status_text = "Idle"
            desired_status_color = COLOR_IDLE

        if is_tutorial_active:
            desired_status_text = "Tutorial Active"
            desired_status_color = COLOR_TUTORIAL
        elif not self._internal_tracking_active:
            desired_status_text = self.status_label.text()
            if "CAM/MP" in desired_status_text or "CAM E" in desired_status_text or "MP Init" in desired_status_text or "Not Ready" in desired_status_text:
                desired_status_color = COLOR_ERROR
            else:
                 desired_status_color = COLOR_ERROR
        elif self.running:
            if not face_detected:
                desired_status_text = "No Face!"
                desired_status_color = COLOR_ERROR
            elif self.last_valid_gaze_normalized is None:
                 desired_status_text = "Gaze Error"
                 desired_status_color = COLOR_WARN
            elif not rect_valid or not outer_valid:
                 desired_status_text = "Config Error"
                 desired_status_color = COLOR_WARN
            elif in_movement_bounds:
                desired_status_text = "Tracking"
                desired_status_color = COLOR_RUN
            else:
                desired_status_text = "Out of Bounds"
                desired_status_color = COLOR_WARN
        else:
            desired_status_text = "Idle"
            desired_status_color = COLOR_IDLE

        current_status_text = self.status_label.text()
        if desired_status_text and (desired_status_text.lower() != current_status_text.lower() or self.status_label.styleSheet().find(desired_status_color) == -1) :
            self.update_status(desired_status_text, desired_status_color)

        final_frame_status_color_hex = desired_status_color if desired_status_color else COLOR_IDLE

        action_taken = False
        if is_tutorial_active:
             if self.tutorial_state == TUTORIAL_STATE_WAITING_LEFT_CLICK and left_click:
                 print("Tutorial: Left Click Detected")
                 self.advance_tutorial(TUTORIAL_STATE_SHOWING_LEFT_SUCCESS); action_taken = True
             elif self.tutorial_state == TUTORIAL_STATE_WAITING_DOUBLE_CLICK and double_click:
                 print("Tutorial: Double Click Detected")
                 self.advance_tutorial(TUTORIAL_STATE_SHOWING_DOUBLE_SUCCESS); action_taken = True
             elif self.tutorial_state == TUTORIAL_STATE_WAITING_MIDDLE_CLICK and mid_click:
                 print("Tutorial: Middle Click Detected")
                 self.advance_tutorial(TUTORIAL_STATE_SHOWING_MIDDLE_SUCCESS); action_taken = True

        elif self.running:
            if double_click:
                print(">>> PyAutoGUI: Double Click")
                try: pyautogui.doubleClick(_pause=False)
                except Exception as e_click: print(f"Error during pyautogui doubleClick: {e_click}")
                self.smooth_cursor.reset_sticking()
                action_taken = True
            elif mid_click:
                 print(">>> PyAutoGUI: Middle Click")
                 try: pyautogui.middleClick(_pause=False)
                 except Exception as e_click: print(f"Error during pyautogui middleClick: {e_click}")
                 self.smooth_cursor.reset_sticking()
                 action_taken = True
            elif left_click:
                 print(">>> PyAutoGUI: Left Click")
                 try: pyautogui.click(_pause=False)
                 except Exception as e_click: print(f"Error during pyautogui click: {e_click}")
                 self.smooth_cursor.reset_sticking()
                 action_taken = True

        if action_taken:
            self.blink_start_time = 0
            self.both_eyes_closed_start_time = 0
            self.last_both_eyes_closed_end_time = 0

        if self.enable_cursor_highlight and self.cursor_highlighter:
            try:
                cursor_x, cursor_y = pyautogui.position()
                self.cursor_highlighter.update_position(cursor_x, cursor_y)
                self.cursor_highlighter.update_color(QColor(final_frame_status_color_hex))
            except Exception as e_highlight:
                self.cursor_highlighter.hide()

        cv_inner_color = hex_to_bgr(final_frame_status_color_hex)
        cv_outer_color = hex_to_bgr(COLOR_INFO_BLUE)
        if rect_valid: cv2.rectangle(bgr_frame_draw, (rect_left, rect_top), (rect_right, rect_bottom), cv_inner_color, 2)
        if outer_valid: cv2.rectangle(bgr_frame_draw, (outer_left, outer_top), (outer_right, outer_bottom), cv_outer_color, 1)
        if target_x_px != -1:
             gaze_color = cv_inner_color
             cv2.circle(bgr_frame_draw, (target_x_px, target_y_px), 5, gaze_color, -1)
             cv2.circle(bgr_frame_draw, (target_x_px, target_y_px), 6, (255, 255, 255), 1)

        self.display_frame(bgr_frame_draw)
        end_time_frame = time.perf_counter()
        self.frame_processing_time = (end_time_frame - start_time_frame) * 1000

    def run_tutorial(self, current_state=TUTORIAL_STATE_SHOWING_INTRO):
        if not (self._internal_tracking_active and self.face_mesh and self.cam and self.cam.isOpened()):
            QMessageBox.warning(self, "Tutorial Error", "Cannot start tutorial: Camera or MediaPipe not ready.")
            self.mark_tutorial_skipped(); return

        print(f"Running tutorial state: {current_state}")
        self.tutorial_state = current_state

        self.set_settings_controls_enabled(False)
        self.start_button.setEnabled(False); self.stop_button.setEnabled(False)
        self.rerun_tutorial_button.setVisible(False)
        if self.running: self.stop_tracking()

        self.right_stack.setCurrentWidget(self.tutorial_widget)

        waiting_states_for_reset = [
            TUTORIAL_STATE_WAITING_LEFT_CLICK,
            TUTORIAL_STATE_WAITING_DOUBLE_CLICK,
            TUTORIAL_STATE_WAITING_MIDDLE_CLICK
        ]
        if current_state in waiting_states_for_reset:
             print(f"Tutorial: Resetting blink/click timers for state {current_state}")
             self.blink_start_time = 0
             self.both_eyes_closed_start_time = 0
             self.last_both_eyes_closed_end_time = 0

        text, instruction, next_visible, next_text, next_action, skip_visible = "", "", False, "Next", None, True

        highlight_gaze_hex = COLOR_TUTORIAL
        highlight_click_hex = COLOR_INFO_BLUE
        status_run_hex = COLOR_RUN
        status_idle_hex = COLOR_IDLE
        status_warn_hex = COLOR_WARN
        status_error_hex = COLOR_ERROR
        color_block = "■"

        if current_state == TUTORIAL_STATE_SHOWING_INTRO:
            text = (f"Welcome to <b>CursorViaCam</b>!<br><br>"
                    f"This tutorial guides you through basic eye gesture controls. Ensure your face is centered and well-lit.<br><br>"
                    f"On the camera feed:<br>"
                    f"&nbsp;&nbsp;<font color='{highlight_gaze_hex}'>⬤</font> Gaze Position<br>"
                    f"&nbsp;&nbsp;<font color='{highlight_gaze_hex}'>□</font> Movement Area (Inner Box)<br>"
                    f"&nbsp;&nbsp;<font color='{highlight_click_hex}'>□</font> Click Area (Outer Box)")
            instruction = "Click 'Next' to learn clicking."; next_visible = True; next_action = lambda: self.run_tutorial(TUTORIAL_STATE_WAITING_LEFT_CLICK)

        elif current_state == TUTORIAL_STATE_WAITING_LEFT_CLICK:
            text = (f"<b>Step 1: Left Click (Long Left Blink ~{self.long_blink_threshold:.2f}s)</b><br><br>"
                    f"Close <b>only your left eye</b> and hold it.<br>"
                    f"<font color='grey'><i>(Keep gaze <font color='{highlight_gaze_hex}'>⬤</font> inside the outer <font color='{highlight_click_hex}'>□</font> border.)</i></font>")
            instruction = "Try a long left eye blink now..."
        elif current_state == TUTORIAL_STATE_SHOWING_LEFT_SUCCESS:
             text = "<b>Success!</b> Left click detected."; instruction = "Click 'Next' for double-clicking."; next_visible = True; next_action = lambda: self.run_tutorial(TUTORIAL_STATE_WAITING_DOUBLE_CLICK)

        elif current_state == TUTORIAL_STATE_WAITING_DOUBLE_CLICK:
            text = (f"<b>Step 2: Double Click (Blink Both Eyes Twice Quickly ~{self.double_blink_interval:.2f}s apart)</b><br><br>"
                    f"Perform two quick full blinks (close <b>both eyes</b> rapidly, twice).<br>"
                    f"<font color='grey'><i>(Keep gaze <font color='{highlight_gaze_hex}'>⬤</font> inside the outer <font color='{highlight_click_hex}'>□</font> border.)</i></font>")
            instruction = "Try double-blinking now..."
        elif current_state == TUTORIAL_STATE_SHOWING_DOUBLE_SUCCESS:
             text = "<b>Great!</b> Double click detected."; instruction = "Click 'Next' for middle-clicking."; next_visible = True; next_action = lambda: self.run_tutorial(TUTORIAL_STATE_WAITING_MIDDLE_CLICK)

        elif current_state == TUTORIAL_STATE_WAITING_MIDDLE_CLICK:
             text = (f"<b>Step 3: Middle Click (Hold Both Eyes Closed ~{MIDDLE_CLICK_HOLD_DURATION:.2f}s)</b><br><br>"
                     f"Close and hold <b>both eyes</b>.<br>"
                     f"<font color='grey'><i>(Keep gaze <font color='{highlight_gaze_hex}'>⬤</font> inside the outer <font color='{highlight_click_hex}'>□</font> border.)</i></font>")
             instruction = "Try closing and holding both eyes now..."
        elif current_state == TUTORIAL_STATE_SHOWING_MIDDLE_SUCCESS:
              text = "<b>Excellent!</b> Middle click detected."; instruction = "Click 'Next' to learn about the status highlighter."; next_visible = True; next_action = lambda: self.run_tutorial(TUTORIAL_STATE_SHOWING_HIGHLIGHTER_INFO)

        elif current_state == TUTORIAL_STATE_SHOWING_HIGHLIGHTER_INFO:
            text = (f"<b>Step 4: Cursor Highlighter (Optional)</b><br><br>"
                    f"A colored ring around your cursor shows the tracking status:<br>"
                    f"<br>"
                    f"&nbsp;&nbsp;<font color='{status_run_hex}'>{color_block}</font> <b>Tracking:</b> Cursor is actively controlled.<br>"
                    f"&nbsp;&nbsp;<font color='{status_idle_hex}'>{color_block}</font> <b>Idle / Ready:</b> System ready, tracking paused.<br>"
                    f"&nbsp;&nbsp;<font color='{status_warn_hex}'>{color_block}</font> <b>Warn / Bounds:</b> Out of bounds or minor issue.<br>"
                    f"&nbsp;&nbsp;<font color='{status_error_hex}'>{color_block}</font> <b>Error / No Face:</b> Major issue or face lost.<br>"
                    f"&nbsp;&nbsp;<font color='{COLOR_TUTORIAL}'>{color_block}</font> <b>Tutorial:</b> You are in the tutorial.<br>"
                    f"<br>"
                    f"Enable/disable this in the main panel via the 'Cursor Highlighter' checkbox.")
            instruction = "Click 'Next' for a settings overview."
            next_visible = True; next_action = lambda: self.run_tutorial(TUTORIAL_STATE_SHOWING_CONTROLS_INFO)

        elif current_state == TUTORIAL_STATE_SHOWING_CONTROLS_INFO:
             text = ("<b>Step 5: Settings Overview</b><br><br>"
                     "You can adjust settings later in the main panel:<br>"
                     "<ul>"
                     "<li><b>Camera:</b> Select your input camera.</li>"
                     "<li><b>Profile:</b> Save/load different setting configurations.</li>"
                     "<li><b>Track Area Level:</b> Adjusts the central 'dead zone'.</i></li>"
                     "<li><b>Outer Gap Level:</b> Changes space between movement & click areas.</li>"
                     "<li><b>Blink Sens:</b> Adjusts how sensitive blink detection is (Low/Medium/High).</li>"
                     "<li><b>Button Sticking:</b> (Windows Only) Helps cursor 'stick' to UI buttons.</li>"
                     "<li><b>Cursor Highlighter:</b> Toggles the status ring around the cursor (explained in the previous step).</li>"
                     "</ul>")
             instruction = "You're ready to use CursorViaCam!"
             next_text = "Finish Tutorial"; next_visible = True; next_action = self.mark_tutorial_complete; skip_visible = False

        full_text = f"{text}<br><br><b>{instruction}</b>" if instruction else text
        self.tutorial_text_label.setTextFormat(Qt.TextFormat.RichText)
        self.tutorial_text_label.setText(full_text)
        self.tutorial_next_button.setText(next_text); self.tutorial_next_button.setVisible(next_visible)
        self.tutorial_skip_button.setVisible(skip_visible)

        try: self.tutorial_next_button.clicked.disconnect()
        except TypeError: pass
        if next_action: self.tutorial_next_button.clicked.connect(next_action)

    def advance_tutorial(self, next_state):
        waiting_states = [
            TUTORIAL_STATE_WAITING_LEFT_CLICK,
            TUTORIAL_STATE_WAITING_DOUBLE_CLICK,
            TUTORIAL_STATE_WAITING_MIDDLE_CLICK
        ]
        if self.tutorial_state in waiting_states:
             print(f"Tutorial advancing from {self.tutorial_state} to {next_state}")
             QTimer.singleShot(10, lambda: self.run_tutorial(next_state))
        else:
            print(f"Warning: Tried to advance tutorial from non-waiting state {self.tutorial_state}")

    def _end_tutorial(self, skipped=False):
        end_state = TUTORIAL_STATE_SKIPPED if skipped else TUTORIAL_STATE_COMPLETE
        print(f"Tutorial {'skipped' if skipped else 'completed'}.")
        self.tutorial_state = end_state; self.tutorial_completed = True
        self.all_profiles_data["tutorial_completed"] = True; save_profiles(self.all_profiles_data)

        self.right_stack.setCurrentWidget(self.control_frame)

        self.set_settings_controls_enabled(True)
        can_start = (self.cam and self.cam.isOpened() and self.face_mesh and self._internal_tracking_active)
        self.start_button.setEnabled(can_start); self.stop_button.setEnabled(self.running)
        self.rerun_tutorial_button.setVisible(True)

        final_status_color = COLOR_ERROR if not can_start else COLOR_IDLE
        final_status_text = "Init Error" if not can_start else "Idle"
        self.update_status(final_status_text, final_status_color)

        msg = "Tutorial skipped." if skipped else "Tutorial complete!"; QMessageBox.information(self, "Tutorial", msg)

    def mark_tutorial_complete(self): self._end_tutorial(skipped=False)
    def mark_tutorial_skipped(self): self._end_tutorial(skipped=True)

    def display_frame(self, frame_bgr):
        if frame_bgr is None: self.display_error_on_feed("No Frame Data"); return
        try:
            h, w, ch = frame_bgr.shape; bytes_per_line = ch * w
            if h <= 0 or w <= 0: return
            rgb_image = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            if qt_image.isNull(): self.display_error_on_feed("Frame Convert Error"); return
            pixmap = QPixmap.fromImage(qt_image)
            scaled_pixmap = pixmap.scaled(self.camera_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            bg_pixmap = QPixmap(self.camera_label.size())
            bg_pixmap.fill(Qt.GlobalColor.black)
            painter = QPainter(bg_pixmap)
            x = (bg_pixmap.width() - scaled_pixmap.width()) // 2
            y = (bg_pixmap.height() - scaled_pixmap.height()) // 2
            painter.drawPixmap(QPoint(x, y), scaled_pixmap)
            painter.end()
            self.camera_label.setPixmap(bg_pixmap); self.camera_label.setText("")
        except Exception as e:
            print(f"Error displaying frame: {e}"); self.display_error_on_feed(f"Frame Display Error:\n{e}")

    def display_error_on_feed(self, text):
         try:
             pixmap = QPixmap(self.camera_label.size()); pixmap.fill(Qt.GlobalColor.black)
             painter = QPainter(pixmap); painter.setPen(Qt.GlobalColor.red); font = painter.font(); font.setPointSize(12); font.setBold(True); painter.setFont(font)
             text_rect = pixmap.rect().adjusted(10, 10, -10, -10)
             painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text); painter.end()
             self.camera_label.setPixmap(pixmap); self.camera_label.setText("")
         except Exception as e:
             print(f"Error displaying error on feed: {e}")
             self.camera_label.setPixmap(QPixmap())
             self.camera_label.setText(text); self.camera_label.setStyleSheet("background-color: black; color: red; border: 1px solid gray;"); self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def save_current_profile_settings(self):
        if not self.active_profile_name or self.active_profile_name not in self.all_profiles_data.get("profiles", {}):
            print(f"Warning: Cannot save. Active profile '{self.active_profile_name}' invalid.")
            return
        self.update_settings_from_runtime()
        self.all_profiles_data["profiles"][self.active_profile_name] = self.settings.copy()
        self.all_profiles_data["tutorial_completed"] = self.tutorial_completed
        save_profiles(self.all_profiles_data)

    def update_settings_from_runtime(self):
        if hasattr(self, 'padding_slider'):
            padding_level = self.padding_slider.value()
            self.settings["rect_padding"] = self._level_to_padding(padding_level)
        if hasattr(self, 'gap_level_slider'):
            gap_level = self.gap_level_slider.value()
            self.settings["outer_gap_level"] = gap_level
        if hasattr(self, 'blink_selector'):
            blink_level = self.blink_selector.currentText()
            self.settings["blink_threshold_level"] = blink_level if blink_level in BLINK_THRESHOLD_MAP else "Medium"
        if hasattr(self, 'sticking_checkbox'):
            self.settings["enable_button_sticking"] = self.sticking_checkbox.isChecked() and IS_WINDOWS
        if hasattr(self, 'highlight_checkbox'):
            self.settings["enable_cursor_highlight"] = self.highlight_checkbox.isChecked()

        if hasattr(self, 'camera_selector'):
            qt_cam_idx = self.camera_selector.currentIndex()
            if qt_cam_idx >= 0:
                cam_index_data = self.camera_selector.itemData(qt_cam_idx)
                if cam_index_data is not None and isinstance(cam_index_data, int):
                    self.settings["camera_index"] = cam_index_data
                elif self.available_cameras:
                    try:
                        first_cam_data = self.camera_selector.itemData(0)
                        self.settings["camera_index"] = first_cam_data if first_cam_data is not None else 0
                    except Exception:
                        self.settings["camera_index"] = self.settings.get("camera_index", 0)
                else:
                    self.settings["camera_index"] = self.settings.get("camera_index", 0)

        if hasattr(self, 'smooth_cursor'):
            self.settings["smooth_window_internal"] = self.smooth_cursor.smoothing_window
        self.settings["long_blink_threshold"] = self.settings.get("long_blink_threshold", get_default_settings()["long_blink_threshold"])
        self.settings["double_blink_interval"] = self.settings.get("double_blink_interval", get_default_settings()["double_blink_interval"])

    def closeEvent(self, event):
        print("Closing application...")
        self.running = False; self._internal_tracking_active = False
        if self.timer.isActive(): self.timer.stop()

        if self.cursor_highlighter:
            self.cursor_highlighter.close()
            print("Closed highlighter window.")

        self.right_stack.setCurrentWidget(self.control_frame)

        is_tutorial_running_on_close = not (
            self.tutorial_state == TUTORIAL_STATE_IDLE or
            self.tutorial_state == TUTORIAL_STATE_COMPLETE or
            self.tutorial_state == TUTORIAL_STATE_SKIPPED
        )

        if not is_tutorial_running_on_close:
            if self.active_profile_name in self.all_profiles_data.get("profiles", {}):
                print(f"Saving final settings for profile: {self.active_profile_name}")
                self.save_current_profile_settings()
            else:
                 print(f"Warning: Active profile '{self.active_profile_name}' not found. Saving only tutorial status.")
                 self.all_profiles_data["tutorial_completed"] = self.tutorial_completed
                 save_profiles(self.all_profiles_data)
        else:
             print("Tutorial active on close. Saving status as incomplete.")
             self.tutorial_completed = False
             self.all_profiles_data["tutorial_completed"] = False
             if self.active_profile_name in self.all_profiles_data.get("profiles", {}):
                 self.update_settings_from_runtime()
                 self.all_profiles_data["profiles"][self.active_profile_name] = self.settings.copy()
             save_profiles(self.all_profiles_data)

        if self.cam is not None and self.cam.isOpened(): print("Releasing camera..."); self.cam.release(); self.cam = None
        if self.face_mesh is not None: print("Closing MediaPipe..."); self.face_mesh.close(); self.face_mesh = None

        print("Exiting."); event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = CursorViaCamApp()
    window.show()
    sys.exit(app.exec())