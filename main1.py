import cv2
import mediapipe as mp
import pyautogui
pyautogui.FAILSAFE = False # Disable the failsafe feature
import sys
import json
import os
import time
import numpy as np
from collections import deque
import platform
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QComboBox, QSlider, QCheckBox, QFrame, QGridLayout, QSizePolicy, QErrorMessage,
    QInputDialog, QMessageBox, QSpacerItem, QStackedWidget, QScrollArea
)
from PyQt6.QtGui import QImage, QPixmap, QIcon, QPainter, QPen, QColor, QScreen, QFont
from PyQt6.QtCore import Qt, QTimer, QSize, QPoint, QRect

# --- Platform Specific Imports (for Button Sticking) ---
IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    try:
        import win32gui
        import win32api # Needed for GetSystemMetrics
        print("win32gui/win32api libraries imported successfully for button sticking.")
    except ImportError:
        print("Warning: 'pywin32' not installed. Button sticking feature will be disabled.")
        IS_WINDOWS = False
else:
    print("Button sticking feature is only available on Windows.")
# --- End Platform Specific Imports ---

# Configuration file for saving user settings and profiles
CONFIG_FILE = "cursorviacam_profiles.json"

# --- Track Area (Padding) Level Constants & Mappings ---
MIN_TRACK_AREA_LEVEL = 1
MAX_TRACK_AREA_LEVEL = 31 # Corresponds to 50px padding
PAD_AT_LEVEL_1 = 200      # Padding in pixels for Level 1
PAD_AT_MAX_LEVEL = 50       # Padding in pixels for the highest Level
PAD_LEVEL_STEP_PX = 5      # The change in padding per level change
DEFAULT_PADDING_VALUE = 170 # Still store padding in px, calculate level for UI

# --- Default Cursor Behavior Constants (Replaces Sensitivity) ---
DEFAULT_BASE_GAIN = 0.80
DEFAULT_ACCELERATION = 0.07
DEFAULT_MIN_FACTOR = 0.5
DEFAULT_MAX_FACTOR = 2.4
# ---

# --- Outer Gap Level Constants & Mappings ---
MIN_GAP_LEVEL = 1
MAX_GAP_LEVEL = 9
DEFAULT_GAP_LEVEL = 1
GAP_LEVEL_BASE_PX = 10
GAP_LEVEL_STEP_PX = 5

# --- Click Duration Constants ---
MIDDLE_CLICK_HOLD_DURATION = 0.35 # Time in seconds for middle click (Hold BOTH eyes)
# Removed SINGLE_BLINK_DURATION_FOR_LEFT_CLICK constant - using long_blink_threshold setting
DOUBLE_BLINK_INTERVAL = 0.45 # Max time IN SECONDS between the end of first blink and start of second for double click

# --- Edge Mapping Margin ---
EDGE_MAP_MARGIN_PX = 10 # Adjust this value as needed (e.g., 5, 10, 15, 20)

# --- Tutorial Constants (Highlight Info ADDED, Renumbered) ---
TUTORIAL_STATE_IDLE = 0
TUTORIAL_STATE_SHOWING_INTRO = 1
TUTORIAL_STATE_WAITING_LEFT_CLICK = 2
TUTORIAL_STATE_SHOWING_LEFT_SUCCESS = 3
TUTORIAL_STATE_WAITING_DOUBLE_CLICK = 4
TUTORIAL_STATE_SHOWING_DOUBLE_SUCCESS = 5
TUTORIAL_STATE_WAITING_MIDDLE_CLICK = 6
TUTORIAL_STATE_SHOWING_MIDDLE_SUCCESS = 7
TUTORIAL_STATE_SHOWING_HIGHLIGHTER_INFO = 8 # NEW: Explain Highlighter
TUTORIAL_STATE_SHOWING_CONTROLS_INFO = 9    # Renumbered from 8
TUTORIAL_STATE_COMPLETE = 10                # Renumbered from 9
TUTORIAL_STATE_SKIPPED = 11                 # Renumbered from 10


# Status Colors
COLOR_IDLE = "#777777"; COLOR_RUN = "#008000"; COLOR_WARN = "#FFA500"; COLOR_ERROR = "#FF0000"
COLOR_START = "#FFD700"; COLOR_INFO_BLUE = "#4682B4"; COLOR_TUTORIAL = "#DA70D6" # Purple for Tutorial


# --- Cursor Highlighter Overlay Window ---
class CursorHighlighterWindow(QWidget):
    """A transparent overlay window to draw a ring around the cursor."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |       # No border or title bar
            Qt.WindowType.WindowStaysOnTopHint |      # Always on top
            Qt.WindowType.Tool |                      # Doesn't appear in taskbar/alt-tab
            Qt.WindowType.WindowTransparentForInput # Allows clicks to pass through (Qt 5.1+) - Using attribute below
        )
        # Ensure background is transparent and mouse events pass through
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) # Crucial!

        self.current_color = QColor(COLOR_IDLE) # Default color
        self.ring_diameter = 32 # Outer diameter of the ring
        self.pen_width = 3
        # Set fixed size slightly larger than the ring to accommodate the pen width
        self.setFixedSize(self.ring_diameter + self.pen_width, self.ring_diameter + self.pen_width)
        self.hide() # Start hidden

    def paintEvent(self, event):
        """Draws the colored ring."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.current_color, self.pen_width)
        painter.setPen(pen)
        # Calculate the drawing rectangle, inset by half the pen width for centering
        rect = self.rect().adjusted(self.pen_width // 2, self.pen_width // 2,
                                     -self.pen_width // 2, -self.pen_width // 2)
        painter.drawEllipse(rect) # Draw the ring

    def update_color(self, color: QColor):
        """Sets the ring color and triggers a repaint if changed."""
        if self.current_color != color:
            self.current_color = color
            self.update() # Request a repaint

    def update_position(self, x, y):
        """Moves the overlay window so its center is at the given (x, y) screen coordinates."""
        # Calculate top-left corner for the window to be centered at (x, y)
        new_x = x - self.width() // 2
        new_y = y - self.height() // 2
        # Only move if the position actually changes to reduce overhead
        if self.pos().x() != new_x or self.pos().y() != new_y:
            self.move(new_x, new_y)

    def set_visibility(self, visible):
        """Shows or hides the highlighter window."""
        if visible and not self.isVisible():
            # print("Highlighter: Showing") # Debug
            # Try to move to current cursor pos before showing to avoid initial jump
            try:
                cx, cy = pyautogui.position()
                self.update_position(cx, cy)
            except Exception: pass # Ignore if fails
            self.show()
        elif not visible and self.isVisible():
            # print("Highlighter: Hiding") # Debug
            self.hide()
# --- End Cursor Highlighter Overlay Window ---


# --- SmoothCursor Class (With Button Sticking Fix & DRIFT FIX) ---
class SmoothCursor:
    """Handles cursor smoothing, adaptive speed, button sticking, and drift correction."""
    def __init__(self):
        self.smoothing_window = 6 # Default if not loaded
        # Use fixed default values now
        self.speed_gain = DEFAULT_BASE_GAIN
        self.acceleration = DEFAULT_ACCELERATION
        self.min_speed_factor = DEFAULT_MIN_FACTOR
        self.max_speed_factor = DEFAULT_MAX_FACTOR
        # --- Sticking ---
        self.enable_sticking = IS_WINDOWS
        self.stick_threshold = 25
        self.stick_release_multiplier = 1.8
        self.stick_search_radius = 100
        self.stick_check_interval = 0.2
        self.last_stick_check_time = 0
        self.sticking_to_button = False
        self.stick_position = None
        # --- State ---
        self.position_history = deque(maxlen=self.smoothing_window)
        self.last_raw_position = None          # Track last raw input for speed calc
        self.last_smoothed_gaze_target = None  # Tracks previous smoothed target for adaptive speed calculation
        self.current_speed_multiplier = self.min_speed_factor # Use the fixed min factor initially
        # --- Screen Info ---
        self.screen_width = 0
        self.screen_height = 0
        self._get_screen_dimensions() # Use helper method for clarity


    def _get_screen_dimensions(self):
        """Gets screen dimensions using appropriate method."""
        if IS_WINDOWS:
            try:
                self.screen_width = win32api.GetSystemMetrics(0) # SM_CXSCREEN
                self.screen_height = win32api.GetSystemMetrics(1) # SM_CYSCREEN
                # print(f"SmoothCursor: Detected screen dimensions (win32api): {self.screen_width}x{self.screen_height}")
                if self.screen_width <= 0 or self.screen_height <= 0: # Sanity check
                    raise ValueError("win32api returned non-positive dimensions")
            except Exception as e_size_win:
                print(f"Warning: win32api.GetSystemMetrics failed: {e_size_win}. Falling back to pyautogui.")
                self._get_screen_dimensions_pyautogui() # Fallback
        else: # Non-windows
            self._get_screen_dimensions_pyautogui()

    def _get_screen_dimensions_pyautogui(self):
        """Fallback method using pyautogui for screen dimensions."""
        try:
            self.screen_width, self.screen_height = pyautogui.size()
            # print(f"SmoothCursor: Detected screen dimensions (pyautogui): {self.screen_width}x{self.screen_height}")
            if self.screen_width <= 0 or self.screen_height <= 0: # Sanity check
                raise ValueError("pyautogui returned non-positive dimensions")
        except Exception as e_size_py:
            print(f"Warning: Could not get screen dimensions for sticking filter: {e_size_py}")
            self.screen_width = 1920 # Default fallback
            self.screen_height = 1080 # Default fallback
            print(f"SmoothCursor: Using fallback screen dimensions: {self.screen_width}x{self.screen_height}")


    def update_position(self, raw_screen_pos):
        """Updates cursor position based on raw input, applying smoothing, adaptive speed, sticking, and drift correction."""
        raw_screen_pos = np.array(raw_screen_pos)

        # --- Button Sticking Logic ---
        current_time = time.time()
        if self.enable_sticking and IS_WINDOWS and (current_time - self.last_stick_check_time > self.stick_check_interval):
            self.last_stick_check_time = current_time
            try:
                current_cursor_pos_tuple = pyautogui.position()
            except Exception as e_pos:
                # Fallback if getting position fails (less accurate sticking)
                current_cursor_pos_tuple = (self.last_smoothed_gaze_target[0], self.last_smoothed_gaze_target[1]) if self.last_smoothed_gaze_target is not None else (self.screen_width // 2, self.screen_height // 2)
                # print(f"Sticking check: pyautogui.position failed ({e_pos}), using fallback.")

            current_cursor_pos = np.array(current_cursor_pos_tuple)

            if self.sticking_to_button:
                if self.stick_position is None:
                    self.sticking_to_button = False
                else:
                    intended_distance_from_stick = np.linalg.norm(raw_screen_pos - self.stick_position)
                    # Increased release multiplier slightly
                    if intended_distance_from_stick > self.stick_threshold * self.stick_release_multiplier * 1.1:
                        # print("Sticking released: Intention far from stick point.")
                        self.sticking_to_button = False; self.stick_position = None
                        # Clear history on release to avoid jump from possibly stale data
                        self.position_history.clear(); self.last_smoothed_gaze_target = None; self.last_raw_position = None
                    else:
                        # If stuck, ensure cursor stays exactly on stick point
                        # Use current_cursor_pos from pyautogui if available
                        if np.linalg.norm(current_cursor_pos - self.stick_position) > 1: # Allow tiny movements
                            stick_x = max(0, min(int(self.stick_position[0]), self.screen_width - 1))
                            stick_y = max(0, min(int(self.stick_position[1]), self.screen_height - 1))
                            try:
                                pyautogui.moveTo(stick_x, stick_y, _pause=False)
                            except Exception as e_move:
                                print(f"Error during stick moveTo: {e_move}") # Handle rare moveTo issues

                        # Keep updating history with *intended* raw position to allow smooth release transition
                        self.position_history.append(raw_screen_pos)
                        # Store the *actual* stuck position as the last smoothed target for stability
                        self.last_smoothed_gaze_target = self.stick_position
                        self.last_raw_position = raw_screen_pos # Keep tracking raw intention
                        return # IMPORTANT: Return early when stuck

            if not self.sticking_to_button:
                nearest_button_pos = self._find_nearest_clickable_win32(current_cursor_pos, self.screen_width, self.screen_height)
                if nearest_button_pos is not None:
                    distance_to_button = np.linalg.norm(current_cursor_pos - nearest_button_pos)
                    # Consider intention relative to *current* cursor, not smoothed target
                    intended_move_vector = raw_screen_pos - current_cursor_pos
                    cursor_to_button_vector = nearest_button_pos - current_cursor_pos
                    norm_intended = np.linalg.norm(intended_move_vector)
                    norm_button = np.linalg.norm(cursor_to_button_vector)
                    dot_product = 0.0
                    if norm_intended > 1e-6 and norm_button > 1e-6:
                        dot_product = np.dot(intended_move_vector / norm_intended, cursor_to_button_vector / norm_button)

                    # Stick if close AND (moving towards button OR moving very little OR very close)
                    should_stick = (distance_to_button < self.stick_threshold and
                                    (dot_product > -0.1 or norm_intended < 5 or distance_to_button < self.stick_threshold * 0.6 )) # Adjusted threshold

                    if should_stick:
                        # print(f"Sticking initiated: Dist={distance_to_button:.1f}, Dot={dot_product:.2f}, IntendNorm={norm_intended:.1f}")
                        self.sticking_to_button = True; self.stick_position = nearest_button_pos
                        stick_x = max(0, min(int(self.stick_position[0]), self.screen_width - 1))
                        stick_y = max(0, min(int(self.stick_position[1]), self.screen_height - 1))
                        try:
                            pyautogui.moveTo(stick_x, stick_y, _pause=False)
                        except Exception as e_move:
                             print(f"Error during initial stick moveTo: {e_move}")
                        # Reset history and set target to stick position for stability
                        self.position_history.clear(); self.position_history.append(self.stick_position)
                        self.last_smoothed_gaze_target = self.stick_position
                        self.last_raw_position = raw_screen_pos # Still track raw intention
                        return # IMPORTANT: Return early after initiating stick
        # --- End Button Sticking Logic ---

        # --- Smoothing & Movement Calculation (Only if NOT stuck) ---
        self.position_history.append(raw_screen_pos)

        if len(self.position_history) < 1: # Need at least one point
            self.last_raw_position = raw_screen_pos
            return

        # Calculate smoothed target position
        smoothed_gaze_target = np.mean(self.position_history, axis=0)

        # Get current actual cursor position
        try:
            current_x, current_y = pyautogui.position()
            current_cursor_pos = np.array([current_x, current_y])
        except Exception as e_pos:
            # Fallback if getting position fails (e.g., Wayland issues)
            # Use last known smoothed target as approximation
            if self.last_smoothed_gaze_target is not None:
                current_cursor_pos = self.last_smoothed_gaze_target
            else: # Absolute fallback
                 current_cursor_pos = np.array([self.screen_width // 2, self.screen_height // 2])
            # print(f"Warning: pyautogui.position() failed ({e_pos}), using fallback {current_cursor_pos}")


        # --- Adaptive Speed Calculation ---
        if self.last_raw_position is not None:
            raw_movement_vector = raw_screen_pos - self.last_raw_position
            raw_movement_distance = np.linalg.norm(raw_movement_vector)
            # Calculate speed multiplier based on raw movement distance
            self.current_speed_multiplier = np.clip(
                raw_movement_distance * self.acceleration + self.min_speed_factor,
                self.min_speed_factor,
                self.max_speed_factor
            )
        else:
             self.current_speed_multiplier = self.min_speed_factor # Default if no previous position

        # --- DRIFT CORRECTION & MOVEMENT ---
        # Vector from current cursor position to the smoothed gaze target
        error_vector = smoothed_gaze_target - current_cursor_pos
        error_distance = np.linalg.norm(error_vector)

        # Scale movement based on how far the cursor has drifted from the target
        # Increases responsiveness when cursor is far away
        distance_scaling_factor = min(1.0 + error_distance / 40.0, 2.0) # Capped scaling

        # Combine base gain, adaptive speed multiplier, and distance scaling
        applied_gain = self.speed_gain * self.current_speed_multiplier * distance_scaling_factor
        applied_gain = min(applied_gain, 1.0) # Ensure gain doesn't exceed 1.0 (prevents overshooting)

        # Calculate the movement step for this frame
        cursor_movement_step = error_vector * applied_gain

        # Calculate new floating point position
        new_x_f = current_cursor_pos[0] + cursor_movement_step[0]
        new_y_f = current_cursor_pos[1] + cursor_movement_step[1]

        # Convert to integer, clamping to screen boundaries
        new_x = int(max(0, min(new_x_f, self.screen_width - 1)))
        new_y = int(max(0, min(new_y_f, self.screen_height - 1)))

        # Move the cursor only if the calculated position is different (prevents unnecessary calls)
        # Ensure not sticking AND movement is significant enough (e.g., > 0 pixels)
        if not self.sticking_to_button and (abs(new_x - int(current_cursor_pos[0])) > 0 or abs(new_y - int(current_cursor_pos[1])) > 0):
             try:
                 pyautogui.moveTo(new_x, new_y, duration=0, _pause=False)
             except Exception as e_move:
                 print(f"Error during normal moveTo: {e_move}") # Handle rare moveTo issues


        # Update last known positions for the next frame
        self.last_smoothed_gaze_target = smoothed_gaze_target
        self.last_raw_position = raw_screen_pos

    def _find_nearest_clickable_win32(self, position, screen_w, screen_h):
        """Finds the center of the nearest clickable UI element within search radius on Windows."""
        # This method remains unchanged - relies on pywin32
        if not IS_WINDOWS: return None
        buttons = []; target_pos = np.array(position); search_radius_sq = self.stick_search_radius ** 2
        max_sensible_width = screen_w * 0.80; max_sensible_height = screen_h * 0.80
        min_sensible_dimension = 5
        clickable_classes = [
            'Button', 'TButton', 'WindowsForms10.BUTTON.*', 'WindowsForms10.CHECKBOX.*',
            'WindowsForms10.RADIOBUTTON.*', 'CheckBox', 'RadioButton', 'ComboBox', 'ListBox',
            'msctls_trackbar32', 'msctls_updown32', 'ScrollBar', 'SysLink', 'SysListView32',
            'SysTreeView32', 'ToolbarWindow32', 'ReBarWindow32', 'TabControl', 'SysTabControl32',
            'MenuItem' # Added menu items
            # Add more as needed
        ]
        # Classes to definitely ignore (Window decorations, backgrounds, etc.)
        ignore_classes = [
            'Shell_TrayWnd', 'Progman', 'WorkerW', 'Internet Explorer_Server', 'Static', 'Edit',
            'IME', 'MSCTFIME UI', '#32768', 'tooltips_class32', 'SysHeader32',
            'SysPager', 'msctls_statusbar32', # Added status bars etc.
            '#32769', # Popup menus container (items are separate)
            'ComboLBox', # Dropdown list part of ComboBox
        ]

        def enum_windows_proc(hwnd, lParam):
            nonlocal buttons
            try:
                # Basic visibility and enablement checks
                if not win32gui.IsWindowVisible(hwnd) or not win32gui.IsWindowEnabled(hwnd): return True
                class_name = win32gui.GetClassName(hwnd); rect = win32gui.GetWindowRect(hwnd)
                # Ignore specific classes known not to be clickable targets
                if class_name in ignore_classes: return True
                # Ignore by pattern
                if class_name.startswith("Windows.UI.") or class_name.startswith("ApplicationFrameWindow"): return True # Ignore modern UI chrome

                # Basic sanity checks on window rect
                x, y, right, bottom = rect; w, h = right - x, bottom - y
                if w < min_sensible_dimension or h < min_sensible_dimension or right <= 0 or bottom <= 0 or x >= screen_w or y >= screen_h or w > screen_w or h > screen_h: return True
                # Ignore excessively large elements (likely backgrounds or main windows)
                if w > max_sensible_width or h > max_sensible_height: return True

                # Calculate center and distance squared (faster than sqrt)
                center_x, center_y = x + w // 2, y + h // 2
                dist_sq = (target_pos[0] - center_x)**2 + (target_pos[1] - center_y)**2

                # Ignore if outside search radius
                if dist_sq > search_radius_sq: return True

                # Check if class matches any of the clickable patterns
                match = False
                import fnmatch # For wildcard matching
                for pattern in clickable_classes:
                    if '*' in pattern: # Handle wildcards like 'WindowsForms10.BUTTON.*'
                        if fnmatch.fnmatch(class_name, pattern): match = True; break
                    elif class_name == pattern: match = True; break

                # Special handling for menu items (use GetMenuItemRect for more accuracy if needed, but center is often ok)
                if not match and class_name == '#32768': # Check children of popup menus
                    def enum_menu_items(menu_hwnd, _):
                        nonlocal buttons, match
                        try:
                            menu_class = win32gui.GetClassName(menu_hwnd)
                            if menu_class == 'MenuItem': # Assuming direct child is MenuItem, might need deeper search
                                menu_rect = win32gui.GetWindowRect(menu_hwnd)
                                mx, my, mright, mbottom = menu_rect
                                mw, mh = mright-mx, mbottom-my
                                if mw < min_sensible_dimension or mh < min_sensible_dimension: return True
                                mcenter_x, mcenter_y = mx + mw // 2, my + mh // 2
                                mdist_sq = (target_pos[0] - mcenter_x)**2 + (target_pos[1] - mcenter_y)**2
                                if mdist_sq <= search_radius_sq and 0 <= mcenter_x < screen_w and 0 <= mcenter_y < screen_h:
                                    buttons.append({'pos': np.array([mcenter_x, mcenter_y]), 'dist': np.sqrt(mdist_sq), 'hwnd': menu_hwnd, 'class': menu_class, 'rect': menu_rect})
                                    match = True # Consider it matched if a menu item is found nearby
                        except win32gui.error: pass
                        except Exception as e_menu: pass # print(f"Minor error enum menu: {e_menu}")
                        return True
                    win32gui.EnumChildWindows(hwnd, enum_menu_items, None)

                # Add matched button if not already added via menu logic
                if match and not any(b['hwnd'] == hwnd for b in buttons):
                    # Final check: ensure calculated center is within screen bounds
                    if 0 <= center_x < screen_w and 0 <= center_y < screen_h:
                        button_center = np.array([center_x, center_y])
                        buttons.append({'pos': button_center, 'dist': np.sqrt(dist_sq), 'hwnd': hwnd, 'class': class_name, 'rect': rect})

            except win32gui.error: pass # Ignore errors from specific windows (e.g., disappearing)
            except Exception as e_enum:
                # print(f"Minor error during window enumeration: {e_enum}") # Debugging only
                pass
            return True # Continue enumeration

        try:
            # Enumerate children of the desktop first, then top-level windows
            # Include children of the foreground window for potentially higher priority targets
            fg_hwnd = win32gui.GetForegroundWindow()
            if fg_hwnd:
                 win32gui.EnumChildWindows(fg_hwnd, enum_windows_proc, None)
            win32gui.EnumChildWindows(win32gui.GetDesktopWindow(), enum_windows_proc, None)
            win32gui.EnumWindows(enum_windows_proc, None)
        except Exception as e: print(f"Warning: Error during EnumWindows/EnumChildWindows call: {e}")

        if not buttons: return None
        # Find the button with the minimum distance
        nearest_button = min(buttons, key=lambda b: b['dist'])
        return nearest_button['pos']


    def reset_sticking(self):
        """Resets the button sticking state."""
        if self.sticking_to_button:
             # print("Sticking reset.")
             pass
        self.sticking_to_button = False; self.stick_position = None
        # Do not reset smoothed gaze target here, causes jumpiness if sticking released mid-movement
        self.last_raw_position = None # Okay to reset raw position

    def set_smoothing_params(self, window):
        """Updates smoothing window size."""
        window = int(max(1, window))
        if self.smoothing_window != window:
            # print(f"SmoothCursor: Updating smoothing window to {window}") # Info
            self.position_history = deque(maxlen=window)
            # Reset refs when window changes to avoid jerky transition
            self.last_smoothed_gaze_target = None
            self.last_raw_position = None
        self.smoothing_window = window
        # Speed parameters are now fixed defaults set in __init__

# --- End SmoothCursor Class ---


# --- Settings Management Helper Functions (Static) ---
def _level_to_gap_px_static(level):
    clamped_level = max(MIN_GAP_LEVEL, min(MAX_GAP_LEVEL, int(round(level))))
    gap_px = GAP_LEVEL_BASE_PX + (clamped_level - MIN_GAP_LEVEL) * GAP_LEVEL_STEP_PX
    return gap_px

def _gap_px_to_level_static(gap_px):
    gap_px = int(gap_px)
    clamped_gap_px = max(GAP_LEVEL_BASE_PX, min(GAP_LEVEL_BASE_PX + (MAX_GAP_LEVEL - MIN_GAP_LEVEL) * GAP_LEVEL_STEP_PX, gap_px))
    ideal_level = (clamped_gap_px - GAP_LEVEL_BASE_PX) / GAP_LEVEL_STEP_PX + MIN_GAP_LEVEL
    level = max(MIN_GAP_LEVEL, min(MAX_GAP_LEVEL, int(round(ideal_level))))
    return level

def _level_to_padding_static(level):
    level_clamped = max(MIN_TRACK_AREA_LEVEL, min(MAX_TRACK_AREA_LEVEL, int(round(level))))
    padding = PAD_AT_LEVEL_1 - (level_clamped - MIN_TRACK_AREA_LEVEL) * PAD_LEVEL_STEP_PX
    return int(round(padding))

def _padding_to_level_static(padding):
    padding = int(padding)
    clamped_padding = max(PAD_AT_MAX_LEVEL, min(PAD_AT_LEVEL_1, padding))
    # Snap padding to the nearest valid step based on levels
    snapped_padding = round((clamped_padding - PAD_AT_MAX_LEVEL) / PAD_LEVEL_STEP_PX) * PAD_LEVEL_STEP_PX + PAD_AT_MAX_LEVEL
    level_float = MIN_TRACK_AREA_LEVEL + (PAD_AT_LEVEL_1 - snapped_padding) / PAD_LEVEL_STEP_PX
    level_int = int(round(level_float))
    # Clamp level to valid range
    return max(MIN_TRACK_AREA_LEVEL, min(MAX_TRACK_AREA_LEVEL, level_int))

# --- Default Settings Function (UPDATED Highlight ADDED) ---
def get_default_settings():
    """Returns a dictionary containing the default application settings."""
    defaults = {
        "rect_padding": DEFAULT_PADDING_VALUE,
        "blink_threshold_level": "Medium",
        # Removed cursor_sensitivity_level
        "outer_gap_level": DEFAULT_GAP_LEVEL,
        "camera_index": 0,
        "enable_button_sticking": IS_WINDOWS,
        # *** ADDED double_blink_interval (not currently user settable, but stored) ***
        "double_blink_interval": DOUBLE_BLINK_INTERVAL,
        "long_blink_threshold": 0.27,  # Use constant
        "smooth_window_internal": 6,
        "enable_cursor_highlight": False, # New setting default
    }
    if not IS_WINDOWS: defaults["enable_button_sticking"] = False
    # Ensure default padding corresponds exactly to a level
    defaults["rect_padding"] = _level_to_padding_static(_padding_to_level_static(defaults["rect_padding"]))
    return defaults

# --- Load/Save Profiles (Updated for Double Click Interval) ---
def load_profiles():
    default_profile_settings = get_default_settings()
    default_structure = {
        "active_profile": "Default",
        "profiles": {
            "Default": default_profile_settings.copy()
        },
        "tutorial_completed": False
    }
    if not os.path.exists(CONFIG_FILE):
        print(f"Config file '{CONFIG_FILE}' not found. Creating with default profile.")
        try:
            with open(CONFIG_FILE, "w") as file: json.dump(default_structure, file, indent=4)
        except IOError as e: print(f"Error creating default config file: {e}")
        return default_structure

    loaded_data = None # Initialize before try block
    try:
        with open(CONFIG_FILE, "r") as file: loaded_data = json.load(file)

        # --- Basic Structure Validation ---
        if not (isinstance(loaded_data, dict) and "profiles" in loaded_data and
                "active_profile" in loaded_data and isinstance(loaded_data["profiles"], dict)):
            print("Config file structure invalid. Resetting."); return default_structure.copy()

        # --- Add Missing Top-Level Keys ---
        if "tutorial_completed" not in loaded_data: loaded_data["tutorial_completed"] = False
        if "Default" not in loaded_data["profiles"]:
            loaded_data["profiles"]["Default"] = default_profile_settings.copy(); print("Added missing 'Default' profile.")

        valid_profiles = {}
        default_keys = set(default_profile_settings.keys()) # Get current valid keys (including highlight & double blink interval)

        # --- Iterate and Validate Each Profile ---
        for name, profile_settings in loaded_data["profiles"].items():
            if not isinstance(profile_settings, dict):
                print(f"Warning: Profile '{name}' data invalid (not a dict). Skipping."); continue

            # Start with current defaults, then selectively update with loaded valid settings
            valid_settings = default_profile_settings.copy()
            migrated_settings = {}
            keys_to_remove = set()

            for key, value in profile_settings.items():
                # --- Migration: Remove old/unused keys ---
                if key in ["cursor_sensitivity_level", "cursor_speed_level", "cursor_sensitivity", "min_speed", "max_speed", "acceleration", "min_speed_factor", "max_speed_factor", "double_blink_threshold"]: # Old double blink duration removed
                    keys_to_remove.add(key)
                elif key not in default_keys: # Remove any other unknown/old keys
                    keys_to_remove.add(key)
                else:
                     migrated_settings[key] = value # Keep valid keys that exist in current defaults

            if keys_to_remove: print(f"Migrating/removing old keys for profile '{name}': {keys_to_remove}")

            # Update the defaults with valid loaded settings from this profile
            valid_settings.update(migrated_settings)

            # --- Re-Validate and Clamp/Snap All Settings in the profile ---
            try: valid_settings["outer_gap_level"] = max(MIN_GAP_LEVEL, min(MAX_GAP_LEVEL, int(valid_settings.get("outer_gap_level", DEFAULT_GAP_LEVEL))))
            except (ValueError, TypeError): valid_settings["outer_gap_level"] = DEFAULT_GAP_LEVEL

            try:
                level = _padding_to_level_static(int(valid_settings.get("rect_padding", DEFAULT_PADDING_VALUE)))
                valid_settings["rect_padding"] = _level_to_padding_static(level)
            except (ValueError, TypeError): valid_settings["rect_padding"] = DEFAULT_PADDING_VALUE

            try: valid_settings["camera_index"] = int(valid_settings.get("camera_index", 0))
            except (ValueError, TypeError): valid_settings["camera_index"] = 0

            try: valid_settings["long_blink_threshold"] = max(0.1, float(valid_settings.get("long_blink_threshold", default_profile_settings["long_blink_threshold"])))
            except (ValueError, TypeError): valid_settings["long_blink_threshold"] = default_profile_settings["long_blink_threshold"]

            # Validate double_blink_interval (ensure it's a positive float)
            try: valid_settings["double_blink_interval"] = max(0.1, float(valid_settings.get("double_blink_interval", default_profile_settings["double_blink_interval"])))
            except (ValueError, TypeError): valid_settings["double_blink_interval"] = default_profile_settings["double_blink_interval"]

            try: valid_settings["smooth_window_internal"] = max(1, int(valid_settings.get("smooth_window_internal", default_profile_settings["smooth_window_internal"])))
            except (ValueError, TypeError): valid_settings["smooth_window_internal"] = default_profile_settings["smooth_window_internal"]

            if valid_settings.get("blink_threshold_level") not in ["Low", "Medium", "High"]: valid_settings["blink_threshold_level"] = "Medium"

            # Handle boolean sticking setting, ensuring False if not Windows
            if not IS_WINDOWS: valid_settings["enable_button_sticking"] = False
            else:
                 try: valid_settings["enable_button_sticking"] = bool(valid_settings.get("enable_button_sticking", IS_WINDOWS))
                 except (ValueError, TypeError): valid_settings["enable_button_sticking"] = IS_WINDOWS

            # Handle boolean highlight setting
            try: valid_settings["enable_cursor_highlight"] = bool(valid_settings.get("enable_cursor_highlight", default_profile_settings["enable_cursor_highlight"]))
            except (ValueError, TypeError): valid_settings["enable_cursor_highlight"] = default_profile_settings["enable_cursor_highlight"]


            valid_profiles[name] = valid_settings # Store the cleaned profile

        loaded_data["profiles"] = valid_profiles # Replace potentially invalid profiles with validated ones

        # --- Validate Active Profile ---
        if loaded_data["active_profile"] not in loaded_data["profiles"]:
            print(f"Active profile '{loaded_data['active_profile']}' not found. Setting to 'Default'.")
            loaded_data["active_profile"] = "Default"

        # Save the potentially migrated/validated data back immediately
        save_profiles(loaded_data)
        return loaded_data

    except (json.JSONDecodeError, IOError, TypeError, ValueError, KeyError) as e:
        print(f"Error loading or validating profiles: {e}. Using default.")
        # Attempt to save default structure if loading failed, preserving tutorial status if possible
        save_data = default_structure.copy()
        if isinstance(loaded_data, dict) and "tutorial_completed" in loaded_data:
             save_data["tutorial_completed"] = loaded_data["tutorial_completed"]
        save_profiles(save_data)
        return default_structure.copy()

def save_profiles(profiles_data):
    """Saves the complete profiles data structure to the JSON file."""
    try:
        # Ensure only known keys are saved within each profile dictionary
        default_keys = get_default_settings().keys() # Get CURRENT default keys (with highlight & double click interval)
        clean_profiles_dict = {}
        for profile_name, settings_dict in profiles_data.get("profiles", {}).items():
             if isinstance(settings_dict, dict):
                 # Create a new dict containing only the keys that are in the current default settings
                 clean_settings = {k: v for k, v in settings_dict.items() if k in default_keys}
                 # Ensure all default keys are present, adding defaults if missing
                 for def_key in default_keys:
                     if def_key not in clean_settings:
                         clean_settings[def_key] = get_default_settings()[def_key]
                 clean_profiles_dict[profile_name] = clean_settings
             else: print(f"Warning: Profile '{profile_name}' has invalid data type during save. Skipping.")

        # Create the final structure to save
        data_to_save = {
            "active_profile": profiles_data.get("active_profile", "Default"),
            "profiles": clean_profiles_dict,
            "tutorial_completed": profiles_data.get("tutorial_completed", False)
        }
        # Ensure active profile exists, fallback to Default if necessary
        if data_to_save["active_profile"] not in data_to_save["profiles"]:
             data_to_save["active_profile"] = "Default"
             if "Default" not in data_to_save["profiles"]: # Absolute fallback
                  data_to_save["profiles"]["Default"] = get_default_settings()


        with open(CONFIG_FILE, "w") as file:
            json.dump(data_to_save, file, indent=4)
    except (IOError, TypeError) as e:
        print(f"Error saving profiles: {e}")

# --- Global Constants & Initializations ---
ALL_PROFILES_DATA = load_profiles()
ACTIVE_PROFILE_NAME = ALL_PROFILES_DATA.get("active_profile", "Default")
# Ensure active profile name is valid after loading
if ACTIVE_PROFILE_NAME not in ALL_PROFILES_DATA.get("profiles", {}):
    print(f"Correcting active profile: '{ACTIVE_PROFILE_NAME}' not found, using 'Default'.")
    ACTIVE_PROFILE_NAME = "Default"; ALL_PROFILES_DATA["active_profile"] = "Default"
    save_profiles(ALL_PROFILES_DATA) # Save correction

SETTINGS = ALL_PROFILES_DATA.get("profiles", {}).get(ACTIVE_PROFILE_NAME, get_default_settings())
TUTORIAL_COMPLETED = ALL_PROFILES_DATA.get("tutorial_completed", False)

BLINK_THRESHOLD_MAP = {"Low": 0.0045, "Medium": 0.0055, "High": 0.0065}
try: SCREEN_W, SCREEN_H = pyautogui.size()
except Exception as e_scr_size: print(f"Warning: pyautogui.size() failed: {e_scr_size}. Using fallback."); SCREEN_W, SCREEN_H = 1920, 1080

MP_FACE_MESH = mp.solutions.face_mesh


# --- Main Application Window ---
class CursorViaCamApp(QWidget):
    def __init__(self):
        super().__init__()
        # Use globals loaded safely above
        self.all_profiles_data = ALL_PROFILES_DATA
        self.active_profile_name = ACTIVE_PROFILE_NAME
        # Ensure settings are a distinct copy for the active profile
        self.settings = self.all_profiles_data["profiles"].get(self.active_profile_name, get_default_settings()).copy()
        self.tutorial_completed = TUTORIAL_COMPLETED
        self.smooth_cursor = SmoothCursor()
        self.cursor_highlighter = CursorHighlighterWindow() # Create highlighter instance

        # Runtime variables - will be correctly initialized by apply_settings_to_runtime
        self.rect_padding = 0
        self.current_gap_level = 0
        self.outer_rect_gap = 0
        self.blink_threshold = 0
        self.long_blink_threshold = 0
        self.double_blink_interval = 0 # NEW
        self.enable_cursor_highlight = False # Runtime state for highlighter

        # State variables
        self.running = False; self._internal_tracking_active = False; self.cam = None; self.face_mesh = None
        self.was_out_of_bounds = True; self.blink_start_time = 0
        self.both_eyes_closed_start_time = 0
        self.last_both_eyes_closed_end_time = 0 # NEW: Track end of last "both closed" event for double click
        self.available_cameras = []
        self.last_valid_gaze_normalized = None

        # Timing & Performance
        self.timer = QTimer(self); self.timer.timeout.connect(self.update_frame)
        self.frame_processing_time = 0; self.last_frame_time = time.perf_counter()
        self.fps_history = deque(maxlen=10) # For smoothing FPS display

        self.error_dialog = QErrorMessage(self); self.error_dialog.setWindowTitle("CursorViaCam Error")
        self.tutorial_state = TUTORIAL_STATE_IDLE

        # Apply initial loaded/default settings to runtime variables
        self.apply_settings_to_runtime()
        # Build the UI
        self.initUI()
        # Apply settings to UI elements (needs to happen AFTER initUI)
        self.apply_settings_to_ui()
        # Set initial highlighter visibility based on settings AFTER UI is ready
        self.cursor_highlighter.set_visibility(self.enable_cursor_highlight)

        # Center window on screen
        self.center_window()
        # Initialize MediaPipe and Camera
        self.initialize_dependencies()
        # Update performance display initially
        self.update_performance_display()
        self.update_status("Initializing", COLOR_START)

        # Set final UI state based on initialization success and tutorial status
        if self.cam and self.cam.isOpened() and self.face_mesh:
            self.timer.start(15) # Start processing frames immediately
            self._internal_tracking_active = True
            if not self.tutorial_completed:
                # Start tutorial automatically if not completed
                QTimer.singleShot(500, self.run_tutorial) # Delay slightly
            else:
                # Tutorial done, enable normal operation
                QTimer.singleShot(500, lambda: self.update_status("Idle", COLOR_IDLE))
                self.set_settings_controls_enabled(True)
                self.rerun_tutorial_button.setVisible(True)
                self.start_button.setEnabled(True)
                self.right_stack.setCurrentWidget(self.control_frame) # Show control panel
        else:
             # Initialization failed
             self._internal_tracking_active = False
             error_msg = "CAM/MP Error" if not (self.cam and self.cam.isOpened() and self.face_mesh) else ("CAM Error" if not (self.cam and self.cam.isOpened()) else "MP Init Fail")
             QTimer.singleShot(500, lambda: self.update_status(error_msg, COLOR_ERROR))
             self.set_settings_controls_enabled(False) # Disable settings
             self.start_button.setEnabled(False) # Disable start
             self.rerun_tutorial_button.setVisible(False) # Hide tutorial button


    # --- Mapping Helper Functions ---
    def _level_to_padding(self, level): return _level_to_padding_static(level)
    def _padding_to_level(self, padding): return _padding_to_level_static(padding)
    def _level_to_gap_px(self, level): return _level_to_gap_px_static(level)

    def center_window(self):
        """Centers the application window on the primary screen."""
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
        """Initializes Face Mesh and the selected Camera."""
        self.initialize_face_mesh()
        # Use the camera index from the loaded settings
        current_cam_index = self.settings.get("camera_index", 0)
        self.init_camera(current_cam_index)

    # UPDATED apply_settings_to_runtime (Double Click Interval ADDED)
    def apply_settings_to_runtime(self):
        """Applies settings from self.settings dict to internal variables and SmoothCursor."""
        default_settings = get_default_settings() # Get defaults for fallback

        # Apply settings with fallbacks
        self.rect_padding = self.settings.get("rect_padding", default_settings["rect_padding"])
        self.current_gap_level = self.settings.get("outer_gap_level", default_settings["outer_gap_level"])
        self.outer_rect_gap = self._level_to_gap_px(self.current_gap_level)
        self.blink_threshold = BLINK_THRESHOLD_MAP.get( self.settings.get("blink_threshold_level", default_settings["blink_threshold_level"]), BLINK_THRESHOLD_MAP[default_settings["blink_threshold_level"]])
        self.long_blink_threshold = self.settings.get("long_blink_threshold", default_settings["long_blink_threshold"])
        self.double_blink_interval = self.settings.get("double_blink_interval", default_settings["double_blink_interval"]) # NEW
        self.enable_cursor_highlight = self.settings.get("enable_cursor_highlight", default_settings["enable_cursor_highlight"])

        # Update SmoothCursor parameters
        self.smooth_cursor.set_smoothing_params(
            window=self.settings.get("smooth_window_internal", default_settings["smooth_window_internal"])
        )
        enable_sticking_setting = self.settings.get("enable_button_sticking", default_settings["enable_button_sticking"])
        self.smooth_cursor.enable_sticking = enable_sticking_setting and IS_WINDOWS
        if not self.smooth_cursor.enable_sticking: self.smooth_cursor.reset_sticking()

        # Update highlighter visibility based on the new runtime setting
        # Ensure this runs after the highlighter object exists
        if hasattr(self, 'cursor_highlighter') and self.cursor_highlighter:
             self.cursor_highlighter.set_visibility(self.enable_cursor_highlight)

        # print(f"Applied runtime settings: Pad={self.rect_padding}, GapLvl={self.current_gap_level}, BlinkLvl={self.settings.get('blink_threshold_level')}, LongThresh={self.long_blink_threshold:.3f}, DblInt={self.double_blink_interval:.2f}, Smooth={self.smooth_cursor.smoothing_window}, Stick={self.smooth_cursor.enable_sticking}, Highlight={self.enable_cursor_highlight}")


    def initUI(self):
        """Initializes the User Interface elements."""
        self.setWindowTitle("CursorViaCam Control (PyQt6)")
        initial_width, initial_height = 900, 450 # Adjusted height slightly for new checkbox
        self.setGeometry(100, 100, initial_width, initial_height); self.setMinimumSize(initial_width, initial_height); self.setMaximumSize(initial_width, initial_height)

        # Set Window Icon
        try:
            # Determine base path correctly for packaged and script execution
            if getattr(sys, 'frozen', False):
                # If the application is run as a bundle/executable
                base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
            else:
                # If run as a script
                base_path = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(base_path, "CursorViaCam(Whightbg).ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
            else:
                print(f"Warning: Icon '{icon_path}' not found.")
        except Exception as e_icon:
            print(f"Error loading icon: {e_icon}")


        main_layout = QHBoxLayout(self); left_layout = QVBoxLayout(); right_layout = QVBoxLayout()

        # --- Left Side (Camera Feed & Performance) ---
        self.camera_label = QLabel("Initializing Camera...")
        camera_feed_width, camera_feed_height = 540, 405 # Keep feed size
        self.camera_label.setFixedSize(camera_feed_width, camera_feed_height); self.camera_label.setStyleSheet("background-color: black; color: red; border: 1px solid gray;"); self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.camera_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        perf_layout = QHBoxLayout(); self.fps_label = QLabel("FPS: --"); self.proc_time_label = QLabel("Proc: -- ms")
        perf_layout.addWidget(self.fps_label); perf_layout.addStretch(1); perf_layout.addWidget(self.proc_time_label)
        left_layout.addLayout(perf_layout); left_layout.addStretch(1) # Push perf info down

        # --- Right Side (Controls / Tutorial Stack) ---
        self.right_stack = QStackedWidget()

        # --- Page 0: Controls Panel ---
        self.control_frame = QFrame(); self.control_frame.setFrameShape(QFrame.Shape.StyledPanel)
        control_layout = QVBoxLayout(self.control_frame); control_layout.setSpacing(8) # Reduced spacing slightly

        # Start/Stop Buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Tracking"); self.start_button.setToolTip("Start processing camera feed and controlling the cursor.")
        self.stop_button = QPushButton("Stop Tracking"); self.stop_button.setToolTip("Stop processing camera feed and release cursor control.")
        button_style = "QPushButton { font-size: 11pt; padding: 8px; min-height: 35px; }"; self.start_button.setStyleSheet(button_style); self.stop_button.setStyleSheet(button_style)
        button_layout.addWidget(self.start_button); button_layout.addWidget(self.stop_button); control_layout.addLayout(button_layout)

        # Profile Management Section
        profile_frame = QFrame(); profile_frame.setFrameShape(QFrame.Shape.StyledPanel)
        profile_layout_outer = QVBoxLayout(profile_frame); profile_layout_inner = QHBoxLayout()
        profile_layout_outer.addWidget(QLabel("Profile:")); self.profile_combo = QComboBox(); self.profile_combo.setToolTip("Select the active settings profile.")
        self.save_profile_button = QPushButton("Save As..."); self.save_profile_button.setToolTip("Save current settings as a new profile")
        self.delete_profile_button = QPushButton("Delete"); self.delete_profile_button.setToolTip("Delete the selected profile (cannot delete 'Default')")
        profile_layout_inner.addWidget(self.profile_combo, 2); profile_layout_inner.addWidget(self.save_profile_button, 1); profile_layout_inner.addWidget(self.delete_profile_button, 1)
        profile_layout_outer.addLayout(profile_layout_inner); control_layout.addWidget(profile_frame)

        # Settings Grid Layout
        grid_layout = QGridLayout(); grid_layout.setVerticalSpacing(6); grid_layout.setHorizontalSpacing(10) # Reduced vertical spacing
        grid_row = 0
        # Camera Selector
        grid_layout.addWidget(QLabel("Camera:"), grid_row, 0); self.camera_selector = QComboBox(); self.camera_selector.setToolTip("Select the camera device to use for tracking.")
        self.populate_camera_selector(); grid_layout.addWidget(self.camera_selector, grid_row, 1, 1, 2); grid_row += 1
        # Track Area Slider
        grid_layout.addWidget(QLabel("Track Area Level:"), grid_row, 0); self.padding_slider = QSlider(Qt.Orientation.Horizontal)
        self.padding_slider.setToolTip("Adjust Track Area Level: Controls dead zone size.\nHigher level = Smaller dead zone."); self.padding_slider.setRange(MIN_TRACK_AREA_LEVEL, MAX_TRACK_AREA_LEVEL)
        self.padding_value_label = QLabel("Level -"); self.padding_value_label.setMinimumWidth(70); self.padding_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid_layout.addWidget(self.padding_slider, grid_row, 1); grid_layout.addWidget(self.padding_value_label, grid_row, 2); grid_row += 1
        # Outer Gap Slider
        grid_layout.addWidget(QLabel("Outer Gap Level:"), grid_row, 0); self.gap_level_slider = QSlider(Qt.Orientation.Horizontal)
        self.gap_level_slider.setToolTip("Adjust Outer Gap Level: Space between move/click areas."); self.gap_level_slider.setRange(MIN_GAP_LEVEL, MAX_GAP_LEVEL)
        self.gap_level_value_label = QLabel("Level -"); self.gap_level_value_label.setMinimumWidth(50); self.gap_level_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid_layout.addWidget(self.gap_level_slider, grid_row, 1); grid_layout.addWidget(self.gap_level_value_label, grid_row, 2); grid_row += 1
        # Blink Sensitivity Selector
        grid_layout.addWidget(QLabel("Blink Sens:"), grid_row, 0); self.blink_selector = QComboBox(); self.blink_selector.setToolTip("Set sensitivity for blink detection.")
        self.blink_selector.addItems(list(BLINK_THRESHOLD_MAP.keys())); grid_layout.addWidget(self.blink_selector, grid_row, 1, 1, 2); grid_row += 1

        # Configure grid column stretch factors
        grid_layout.setColumnStretch(0, 0); grid_layout.setColumnStretch(1, 1); grid_layout.setColumnStretch(2, 0)
        control_layout.addLayout(grid_layout)

        # Checkboxes (Sticking & Highlight) - Placed outside grid for simpler layout
        checkbox_layout = QVBoxLayout(); checkbox_layout.setSpacing(4) # Tight spacing for checkboxes
        self.sticking_checkbox = QCheckBox("Button Sticking (Win Only)"); self.sticking_checkbox.setToolTip("Enable cursor 'sticking' (Windows only)."); self.sticking_checkbox.setEnabled(IS_WINDOWS)
        checkbox_layout.addWidget(self.sticking_checkbox)

        # --- Add Cursor Highlight Checkbox Here ---
        self.highlight_checkbox = QCheckBox("Cursor Highlighter")
        self.highlight_checkbox.setToolTip("Show a colored ring around the cursor indicating tracking status.")
        checkbox_layout.addWidget(self.highlight_checkbox)
        control_layout.addLayout(checkbox_layout) # Add the checkbox layout

        control_layout.addStretch(1) # Push tutorial button down

        # Re-run Tutorial Button
        self.rerun_tutorial_button = QPushButton("Run Tutorial"); self.rerun_tutorial_button.setToolTip("Run the setup tutorial again.")
        control_layout.addWidget(self.rerun_tutorial_button);
        self.right_stack.addWidget(self.control_frame) # Add control frame as first page

        # --- Page 1: Tutorial Panel ---
        self.tutorial_widget = QWidget()
        tutorial_layout = QVBoxLayout(self.tutorial_widget)
        tutorial_layout.setContentsMargins(15, 15, 15, 15)
        tutorial_layout.setSpacing(15) # Increased spacing slightly for scrollbar room

        self.tutorial_title_label = QLabel("CursorViaCam Tutorial")
        font = self.tutorial_title_label.font()
        font.setPointSize(14); font.setBold(True)
        self.tutorial_title_label.setFont(font)
        self.tutorial_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tutorial_layout.addWidget(self.tutorial_title_label)

        # --- Create Scroll Area for Tutorial Text ---
        self.tutorial_scroll_area = QScrollArea() # Create a scroll area
        self.tutorial_scroll_area.setWidgetResizable(True) # Allow the inner widget (label) to resize
        self.tutorial_scroll_area.setFrameShape(QFrame.Shape.NoFrame) # Optional: remove border around scroll area
        # Only show scrollbars when needed
        self.tutorial_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tutorial_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Create the label that will go inside the scroll area
        self.tutorial_text_label = QLabel("Tutorial instructions...")
        font = self.tutorial_text_label.font()
        font.setPointSize(11)
        self.tutorial_text_label.setFont(font)
        self.tutorial_text_label.setWordWrap(True)
        # Align text to the top within the label, important for scrolling behavior
        self.tutorial_text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.tutorial_text_label.setTextFormat(Qt.TextFormat.RichText) # Ensure rich text works

        # Set the label as the widget contained within the scroll area
        self.tutorial_scroll_area.setWidget(self.tutorial_text_label)

        # Add the scroll area (containing the label) to the main tutorial layout
        tutorial_layout.addWidget(self.tutorial_scroll_area, 1) # Allow scroll area to expand

        # --- Tutorial Buttons ---
        tutorial_button_layout = QHBoxLayout()
        self.tutorial_skip_button = QPushButton("Skip Tutorial")
        self.tutorial_next_button = QPushButton("Next")
        tutorial_button_layout.addWidget(self.tutorial_skip_button)
        tutorial_button_layout.addStretch(1)
        tutorial_button_layout.addWidget(self.tutorial_next_button)
        tutorial_layout.addLayout(tutorial_button_layout)

        self.right_stack.addWidget(self.tutorial_widget) # Add tutorial frame as second page

        # --- Final Layout Assembly ---
        right_layout.addWidget(self.right_stack) # Add stack to right layout
        # Status Label at the bottom right
        self.status_label = QLabel("Initializing"); self.status_label.setMinimumHeight(35); self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.status_label.setStyleSheet("border: 1px solid gray; border-radius: 4px; padding: 5px;")
        right_layout.addWidget(self.status_label)

        main_layout.setContentsMargins(12, 12, 12, 12); main_layout.setSpacing(15)
        main_layout.addLayout(left_layout, 5); main_layout.addLayout(right_layout, 4) # Adjust stretch factors if needed
        self.setLayout(main_layout)

        # Connect signals AFTER all UI elements are created
        self.connect_signals()
        # Populate selectors based on initial settings (already loaded into self.settings)
        self.populate_profile_selector() # Must happen after profile_combo exists
        # NOTE: apply_settings_to_ui() is called in __init__ AFTER initUI


    # --- Camera Population & Selection ---
    def populate_camera_selector(self):
        """Detects available cameras and populates the camera selection dropdown."""
        self.available_cameras = self.get_available_cameras()
        self.camera_selector.clear()
        saved_cam_index = self.settings.get("camera_index", 0)
        qt_index_to_select = -1 # Default to no selection

        if self.available_cameras:
            for i, cam_info in enumerate(self.available_cameras):
                # Store the system index (cam_info['index']) as user data
                self.camera_selector.addItem(cam_info['name'], userData=cam_info['index'])
                # Check if this camera's system index matches the saved setting
                if cam_info['index'] == saved_cam_index:
                    qt_index_to_select = i # Found the Qt index corresponding to the saved system index

            # If the saved camera index wasn't found among available cameras
            if qt_index_to_select == -1 and len(self.available_cameras) > 0:
                print(f"Warning: Saved camera index {saved_cam_index} not found. Selecting first available camera.")
                qt_index_to_select = 0 # Select the first camera in the list
                # Update the setting in memory to match the first available camera
                first_cam_data = self.camera_selector.itemData(0)
                if first_cam_data is not None:
                    self.settings["camera_index"] = first_cam_data
                    # Optionally save this correction back to the profile immediately
                    # self.save_current_profile_settings() # Might be too aggressive here

            # Set the current index in the dropdown if a valid selection was determined
            if qt_index_to_select != -1:
                self.camera_selector.setCurrentIndex(qt_index_to_select)

            self.camera_selector.setEnabled(True) # Enable selector if cameras found
        else:
            # No cameras found
            self.camera_selector.addItem("No Cameras Found")
            self.camera_selector.setEnabled(False) # Disable selector

    def get_available_cameras(self, max_to_check=5):
        """Checks multiple camera indices using OpenCV to find available devices."""
        available = []; print("Detecting cameras...")
        for i in range(max_to_check):
            cap_test = None; backend_name = "Default"; name = f"Camera {i}"
            preferred_api = cv2.CAP_DSHOW if IS_WINDOWS else cv2.CAP_ANY # Prefer DSHOW on Windows

            try:
                # Try preferred backend first
                cap_test = cv2.VideoCapture(i, preferred_api)
                if cap_test and cap_test.isOpened():
                    backend_name = "DSHOW" if preferred_api == cv2.CAP_DSHOW else "OS Default"
                else: # If preferred failed, try system default (CAP_ANY)
                    if cap_test: cap_test.release(); cap_test = None # Release failed attempt
                    # print(f"  Camera {i}: Preferred backend ({preferred_api}) failed. Trying CAP_ANY.")
                    cap_test = cv2.VideoCapture(i, cv2.CAP_ANY)
                    if cap_test and cap_test.isOpened():
                        backend_name = "CAP_ANY"
                    else:
                        # print(f"  Camera {i}: Both backends failed.")
                        if cap_test: cap_test.release(); cap_test = None
                        continue # Skip this index if both fail

                # If successfully opened with either backend
                if cap_test and cap_test.isOpened():
                    name = f"Camera {i} ({backend_name})"
                    ret, frame = cap_test.read() # Try reading a frame
                    if ret and frame is not None:
                        h, w, _ = frame.shape
                        if w > 0 and h > 0: # Check for valid dimensions
                            available.append({'index': i, 'name': name, 'backend': backend_name}); print(f"  Found: {name} ({w}x{h})")
                        else: print(f"  Skipping {name}: Invalid resolution {w}x{h}")
                    else: print(f"  Skipping {name}: Failed to read frame")
            except Exception as e: print(f"Error checking camera {i}: {e}")
            finally:
                # Ensure camera is released
                if cap_test and cap_test.isOpened(): cap_test.release()

        if not available: print("Warning: No cameras detected!"); self.show_error_message("No working cameras detected.")
        return available

    def show_error_message(self, message):
        """Displays an error message in a popup dialog."""
        # Ensure error dialog exists
        if not hasattr(self, 'error_dialog') or self.error_dialog is None:
           self.error_dialog = QErrorMessage(self)
           self.error_dialog.setWindowTitle("CursorViaCam Error")
        self.error_dialog.showMessage(message)

    # --- connect_signals (Highlight ADDED) ---
    def connect_signals(self):
        """Connects UI element signals to their corresponding slots."""
        # Buttons
        self.start_button.clicked.connect(self.start_tracking)
        self.stop_button.clicked.connect(self.stop_tracking)
        # Profile Management
        self.profile_combo.activated.connect(self.select_profile) # User selects from dropdown
        self.save_profile_button.clicked.connect(self.save_profile_as)
        self.delete_profile_button.clicked.connect(self.delete_profile)
        # Settings Controls
        self.camera_selector.currentIndexChanged.connect(self.update_camera_selection) # User OR programmatic change
        self.padding_slider.valueChanged.connect(self.update_padding_level_display) # Update label continuously
        self.padding_slider.sliderReleased.connect(self.save_padding_level_setting) # Save on release
        self.gap_level_slider.valueChanged.connect(self.update_gap_level_display) # Update label continuously
        self.gap_level_slider.sliderReleased.connect(self.save_gap_level_setting) # Save on release
        self.blink_selector.activated.connect(self.update_blink_threshold_selection) # User selects from dropdown
        self.sticking_checkbox.stateChanged.connect(self.toggle_sticking) # Checkbox toggled
        self.highlight_checkbox.stateChanged.connect(self.toggle_highlight) # Highlight checkbox toggled
        # Tutorial Controls
        self.rerun_tutorial_button.clicked.connect(lambda: self.run_tutorial())
        self.tutorial_skip_button.clicked.connect(self.mark_tutorial_skipped)
        # Note: tutorial_next_button signal is connected dynamically within run_tutorial

    # --- apply_settings_to_ui (Highlight ADDED) ---
    def apply_settings_to_ui(self):
        """Sets the state of UI widgets based on the current self.settings dict."""
        self.block_setting_signals(True) # Prevent signals during update

        # Profile Selector
        profile_index = self.profile_combo.findText(self.active_profile_name)
        if profile_index != -1: self.profile_combo.setCurrentIndex(profile_index)
        self.delete_profile_button.setEnabled(self.active_profile_name != "Default")

        # Camera Selector
        saved_cam_index = self.settings.get("camera_index", 0)
        qt_cam_idx_to_select = self.camera_selector.findData(saved_cam_index) # Find item by stored system index
        if qt_cam_idx_to_select != -1:
            self.camera_selector.setCurrentIndex(qt_cam_idx_to_select)
        elif self.camera_selector.count() > 0: # If saved index not found, select first item
             print(f"Warning: Saved camera index {saved_cam_index} not found in UI selector. Setting UI to first.")
             self.camera_selector.setCurrentIndex(0)

        # Padding Slider & Label
        current_padding = self.settings.get("rect_padding", DEFAULT_PADDING_VALUE)
        level_padding = self._padding_to_level(current_padding)
        self.padding_slider.setValue(level_padding)
        self.padding_value_label.setText(f"Level {level_padding}")

        # Gap Slider & Label
        level_gap = self.settings.get('outer_gap_level', DEFAULT_GAP_LEVEL)
        self.gap_level_slider.setValue(level_gap)
        self.gap_level_value_label.setText(f"Level {level_gap}")

        # Blink Selector
        blink_level_str = self.settings.get("blink_threshold_level", "Medium")
        blink_idx = self.blink_selector.findText(blink_level_str)
        if blink_idx != -1: self.blink_selector.setCurrentIndex(blink_idx)
        else: self.blink_selector.setCurrentIndex(self.blink_selector.findText("Medium"))

        # Sticking Checkbox
        enable_sticking = self.settings.get("enable_button_sticking", IS_WINDOWS) and IS_WINDOWS
        self.sticking_checkbox.setChecked(enable_sticking)
        self.sticking_checkbox.setEnabled(IS_WINDOWS) # Ensure always disabled if not Windows

        # Highlight Checkbox
        enable_highlight = self.settings.get("enable_cursor_highlight", False)
        self.highlight_checkbox.setChecked(enable_highlight)
        # Highlight checkbox is always enabled if the control panel is enabled

        self.block_setting_signals(False) # Re-enable signals

    # --- block_setting_signals (Highlight ADDED) ---
    def block_setting_signals(self, block):
        """Blocks or unblocks signals for settings-related widgets to prevent loops."""
        widgets_to_block = [
            self.padding_slider, self.gap_level_slider,
            self.blink_selector, self.sticking_checkbox, self.highlight_checkbox, # Added highlight checkbox
            self.camera_selector, self.profile_combo,
        ]
        for widget in widgets_to_block:
            if widget:
                try: widget.blockSignals(block)
                except Exception as e: print(f"Error blocking signals for {widget}: {e}")

    # --- Profile Management Slots ---
    def populate_profile_selector(self):
        """Refreshes the profile dropdown list based on self.all_profiles_data."""
        self.block_setting_signals(True); self.profile_combo.clear() # Block signals during repopulation

        # Ensure 'Default' profile exists if none do
        if not self.all_profiles_data.get("profiles"):
            print("No profiles found, creating default.")
            self.all_profiles_data["profiles"] = {"Default": get_default_settings()}
            self.all_profiles_data["active_profile"] = "Default"; self.active_profile_name = "Default"
            save_profiles(self.all_profiles_data)

        # Add profile names sorted alphabetically
        profile_names = sorted(self.all_profiles_data["profiles"].keys()); self.profile_combo.addItems(profile_names)

        # Set the current selection in the combo box
        active_index = self.profile_combo.findText(self.active_profile_name)
        if active_index != -1:
            self.profile_combo.setCurrentIndex(active_index)
        elif profile_names: # If active profile wasn't found, select the first in the list
            print(f"Warning: Active profile '{self.active_profile_name}' not in list. Selecting '{profile_names[0]}'.")
            self.active_profile_name = profile_names[0]
            self.all_profiles_data["active_profile"] = self.active_profile_name
            # Load the settings for this newly selected active profile
            self.settings = self.all_profiles_data["profiles"].get(self.active_profile_name, get_default_settings()).copy()
            self.profile_combo.setCurrentIndex(0)
            save_profiles(self.all_profiles_data) # Save the corrected active profile name
        else: print("Error: No profiles available after attempting default creation.")

        # Enable/disable delete button based on current selection
        self.delete_profile_button.setEnabled(self.active_profile_name != "Default")
        self.block_setting_signals(False) # Unblock signals

    def select_profile(self, index):
        """Handles user selection of a profile from the dropdown."""
        # Prevent changes during tutorial
        if not self._is_ok_to_change_settings():
             self.block_setting_signals(True) # Block to prevent infinite loop
             current_profile_idx = self.profile_combo.findText(self.active_profile_name)
             if current_profile_idx != -1: self.profile_combo.setCurrentIndex(current_profile_idx)
             self.block_setting_signals(False)
             return

        selected_profile_name = self.profile_combo.itemText(index)
        # Do nothing if selection is invalid or hasn't changed
        if not selected_profile_name or selected_profile_name == self.active_profile_name: return

        print(f"Switching to profile: {selected_profile_name}")

        # Save current UI state to the *previous* active profile before switching
        # Ensure self.settings accurately reflects the UI of the outgoing profile first
        self.update_settings_from_runtime() # Gets current UI state into self.settings
        if self.active_profile_name in self.all_profiles_data["profiles"]:
            self.all_profiles_data["profiles"][self.active_profile_name] = self.settings.copy()
        else:
            print(f"Warning: Outgoing active profile '{self.active_profile_name}' not found in data. Cannot save its state.")

        # Switch active profile name and load its settings
        self.active_profile_name = selected_profile_name
        self.all_profiles_data["active_profile"] = self.active_profile_name
        # Load settings from the new profile, using defaults as fallback
        self.settings = self.all_profiles_data["profiles"].get(self.active_profile_name, get_default_settings()).copy()

        # Apply newly loaded settings to runtime variables and UI elements
        self.apply_settings_to_runtime() # Updates internal vars AND highlighter visibility
        self.apply_settings_to_ui()    # Updates UI controls to match the loaded profile

        # Check if the loaded profile requires a camera change and handle it
        self._check_and_handle_camera_change_for_profile()

        # Save the updated active profile name and potentially updated old profile data
        save_profiles(self.all_profiles_data)

        self.update_status(f"Profile '{self.active_profile_name}' loaded", COLOR_IDLE)
        self.delete_profile_button.setEnabled(self.active_profile_name != "Default") # Update delete button state

    def save_profile_as(self):
        """Saves the current settings (from UI) as a new or existing profile."""
        if not self._is_ok_to_change_settings(): return
        profile_name, ok = QInputDialog.getText(self, "Save Profile As", "Enter profile name:")
        if ok and profile_name:
            profile_name = profile_name.strip()
            if not profile_name: QMessageBox.warning(self, "Invalid Name", "Profile name cannot be empty."); return

            # Check for overwrite, but allow saving over 'Default'
            if profile_name in self.all_profiles_data["profiles"] and profile_name != "Default":
                 reply = QMessageBox.question(self, "Profile Exists", f"Overwrite existing profile '{profile_name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                 if reply == QMessageBox.StandardButton.No: return
            # No special confirmation needed for saving as 'Default'

            # Get current UI state into self.settings before saving
            self.update_settings_from_runtime()
            # Save the current settings under the new name
            self.all_profiles_data["profiles"][profile_name] = self.settings.copy()
            # Make the newly saved profile the active one
            self.active_profile_name = profile_name
            self.all_profiles_data["active_profile"] = profile_name
            save_profiles(self.all_profiles_data) # Save changes to file
            # Update the UI selector to show the new profile and select it
            self.populate_profile_selector() # Refreshes list and sets active index based on self.active_profile_name
            # No need to call apply_settings_to_ui here, populate_profile_selector handles the active selection display
            self.update_status(f"Profile '{profile_name}' saved", COLOR_IDLE)
        elif ok and not profile_name: # User clicked OK but entered empty name
            QMessageBox.warning(self, "Invalid Name", "Profile name cannot be empty.")

    def delete_profile(self):
        """Deletes the currently selected profile (if not 'Default')."""
        if not self._is_ok_to_change_settings(): return
        profile_to_delete = self.profile_combo.currentText() # Get name from UI

        if profile_to_delete == "Default":
            QMessageBox.warning(self, "Cannot Delete", "'Default' profile cannot be deleted."); return
        # Verify profile exists in data before attempting deletion
        if not profile_to_delete or profile_to_delete not in self.all_profiles_data["profiles"]:
             QMessageBox.warning(self, "Error", f"Cannot delete invalid profile '{profile_to_delete}'."); self.populate_profile_selector(); return

        reply = QMessageBox.question(self, "Confirm Delete", f"Delete profile '{profile_to_delete}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # Delete from data structure
            del self.all_profiles_data["profiles"][profile_to_delete]; print(f"Deleted profile: {profile_to_delete}")
            # Switch back to 'Default' profile
            self.active_profile_name = "Default"; self.all_profiles_data["active_profile"] = "Default"
            self.settings = self.all_profiles_data["profiles"].get("Default", get_default_settings()).copy()
            save_profiles(self.all_profiles_data) # Save the deletion and active profile change
            # Refresh UI
            self.populate_profile_selector() # Updates combo box, sets index to Default
            self.apply_settings_to_runtime() # Apply Default settings to runtime vars AND highlighter
            self.apply_settings_to_ui()    # Apply Default settings to UI widgets
            self._check_and_handle_camera_change_for_profile() # Check if Default profile needs camera change
            self.update_status(f"Profile '{profile_to_delete}' deleted", COLOR_IDLE)

    # --- Helper for Settings Changes ---
    def _is_ok_to_change_settings(self):
        """Checks if it's currently permissible to change settings (e.g., not during tutorial)."""
        is_tutorial_active = not (self.tutorial_state == TUTORIAL_STATE_IDLE or
                               self.tutorial_state == TUTORIAL_STATE_COMPLETE or
                               self.tutorial_state == TUTORIAL_STATE_SKIPPED)
        if is_tutorial_active:
             # Avoid showing the message box repeatedly if just checking internally
             # QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before changing settings or profiles.")
             return False
        # Could add check here: if self.running: return False (if settings changes shouldn't happen while tracking)
        return True

    # --- Check Camera Change for Profile ---
    def _check_and_handle_camera_change_for_profile(self):
        """Checks if the newly loaded profile's camera setting requires a camera switch."""
        new_cam_index_setting = self.settings.get("camera_index")

        current_qt_cam_idx = self.camera_selector.currentIndex()
        current_cam_runtime_index = None
        if current_qt_cam_idx >= 0:
            current_cam_runtime_index = self.camera_selector.itemData(current_qt_cam_idx) # Get system index from UI data

        # Compare the setting from the loaded profile with the camera currently selected in the UI
        if new_cam_index_setting is not None and new_cam_index_setting != current_cam_runtime_index:
            print(f"Profile load indicates camera change needed (Current UI: {current_cam_runtime_index}, New Profile Setting: {new_cam_index_setting}).")
            new_qt_idx = self.camera_selector.findData(new_cam_index_setting) # Find Qt index for the required system index
            if new_qt_idx != -1:
                 # If UI isn't already set correctly, trigger the change handler
                 if self.camera_selector.currentIndex() != new_qt_idx:
                     print("Forcing camera change based on profile setting.")
                     # handle_camera_change will update self.settings and save if successful
                     self.handle_camera_change(new_qt_idx, called_internally=True)
                 else:
                     # UI is already correct, but ensure camera is actually initialized if needed
                     print("Camera index already correctly set in UI by profile load.")
                     if not (self.cam and self.cam.isOpened()):
                          print("Camera not open, attempting re-initialization based on profile.")
                          self.handle_camera_change(new_qt_idx, called_internally=True)
            else:
                 # Camera index from profile doesn't exist in current hardware list
                 print(f"Warning: Camera index {new_cam_index_setting} from profile not found in available cameras.")
                 # Revert the setting *in memory* to the currently selected valid camera in the UI
                 if current_cam_runtime_index is not None:
                     self.settings["camera_index"] = current_cam_runtime_index
                     print(f"Reverted profile camera index setting in memory to current UI index: {current_cam_runtime_index}")
                     self.save_current_profile_settings() # Save the correction back to the profile file
                 elif self.camera_selector.count() > 0: # Fallback: use first available camera
                     first_cam_data = self.camera_selector.itemData(0)
                     if first_cam_data is not None:
                         self.settings["camera_index"] = first_cam_data
                         # Also update the UI to select the first camera
                         self.camera_selector.blockSignals(True)
                         self.camera_selector.setCurrentIndex(0)
                         self.camera_selector.blockSignals(False)
                         print(f"Reverted profile camera index setting in memory to first available index: {first_cam_data}")
                         self.save_current_profile_settings()


    # --- Settings Control Slots ---
    def update_camera_selection(self, qt_index):
        """Slot triggered by user changing camera OR programmatic change via setCurrentIndex."""
        # Check if signals are blocked to prevent loops if set programmatically
        if not self.camera_selector.signalsBlocked():
            # Show warning only if user initiated the change during tutorial
            if not self._is_ok_to_change_settings():
                QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before changing settings.")
                # Revert UI selection if change is not allowed
                saved_cam_index = self.settings.get("camera_index", 0)
                previous_qt_idx = self.camera_selector.findData(saved_cam_index)
                if previous_qt_idx != -1:
                    self.camera_selector.blockSignals(True)
                    self.camera_selector.setCurrentIndex(previous_qt_idx)
                    self.camera_selector.blockSignals(False)
                return

            # Pass index and mark as user-initiated (not internal)
            self.handle_camera_change(qt_index, called_internally=False)


    def handle_camera_change(self, qt_index, called_internally=False):
        """Internal logic to handle camera initialization and state updates."""
        # Prevent changes during tutorial unless called internally (e.g., by profile load)
        # The user-facing warning is now in update_camera_selection
        if not called_internally and not self._is_ok_to_change_settings():
            # Just return silently if internal check fails
            return

        # Validate selected Qt index and retrieve associated system camera index
        if qt_index < 0 or qt_index >= self.camera_selector.count():
             print(f"Camera change ignored: Invalid Qt index {qt_index}")
             return
        actual_cam_index = self.camera_selector.itemData(qt_index) # System index stored in data
        if actual_cam_index is None:
             print(f"Camera change ignored: No data for Qt index {qt_index}")
             return
        # Find corresponding camera info (name, backend)
        selected_cam_info = next((c for c in self.available_cameras if c['index'] == actual_cam_index), None)
        if not selected_cam_info:
             print(f"Camera change ignored: Camera info not found for index {actual_cam_index}")
             return

        # Get the camera index currently stored in settings (before this potential change)
        current_setting_cam_index = self.settings.get("camera_index", -1)

        # Avoid unnecessary re-initialization if the same camera is selected and already working
        if actual_cam_index == current_setting_cam_index and self.cam and self.cam.isOpened() and self._internal_tracking_active:
            # print(f"Camera index {actual_cam_index} already active and open.")
            return
        elif actual_cam_index == current_setting_cam_index:
             print(f"Camera index {actual_cam_index} selected, but camera not open. Attempting initialization.")
             # Proceed to initialization block below

        # --- Actual Camera Switch Logic ---
        was_running = self.running
        if self.running: self.stop_tracking() # Stop tracking before changing

        print(f"Switching camera to index {actual_cam_index} ({selected_cam_info['name']})...")
        selected_backend_name = selected_cam_info.get('backend', 'Default')

        if self.init_camera(actual_cam_index, preferred_backend=selected_backend_name):
            # --- Success ---
            print(f"Camera {actual_cam_index} initialized successfully.")
            self.settings["camera_index"] = actual_cam_index # Update setting in memory
            # Save the setting ONLY if the change was initiated by the user via UI OR if internally corrected
            if not called_internally: # User action always saves
                 self.save_current_profile_settings()
            elif called_internally and current_setting_cam_index != actual_cam_index: # Profile load corrected
                 print("Saving corrected camera index from profile load.")
                 self.save_current_profile_settings() # Save the correction

            self.update_status("Camera Changed", COLOR_IDLE)
            self._internal_tracking_active = True # Mark system as ready
            if not self.timer.isActive(): self.timer.start(15) # Ensure timer is running
            # Restart tracking if it was running before and tutorial is not active
            if was_running and self._is_ok_to_change_settings():
                QTimer.singleShot(100, self.start_tracking)
            # Ensure start button is enabled if appropriate
            elif self._is_ok_to_change_settings():
                 self.start_button.setEnabled(True)
        else:
            # --- Failure ---
            print(f"Failed to initialize camera {actual_cam_index}.")
            self.update_status("CAM SWITCH FAIL!", COLOR_ERROR)
            self.display_error_on_feed(f"Failed to Open\n{selected_cam_info['name']}")
            self.show_error_message(f"Failed to open camera: {selected_cam_info['name']}")
            self._internal_tracking_active = False # Mark system as not ready
            self.start_button.setEnabled(False)
            if self.timer.isActive(): self.timer.stop()

            # Attempt to revert UI selection back to the previous setting
            previous_qt_idx = self.camera_selector.findData(current_setting_cam_index)
            if previous_qt_idx != -1 and current_setting_cam_index != actual_cam_index:
                print(f"Attempting to revert UI to previous camera {current_setting_cam_index}.")
                self.camera_selector.blockSignals(True)
                self.camera_selector.setCurrentIndex(previous_qt_idx)
                self.camera_selector.blockSignals(False)
                # Do not try to re-initialize the previous camera automatically here
            else:
                 # If we cannot revert UI, update the setting to the failed index if user initiated
                 if not called_internally:
                      self.settings["camera_index"] = actual_cam_index
                      self.save_current_profile_settings()

    def update_padding_level_display(self, level):
        """Updates padding value label when slider changes."""
        if not self.padding_slider.signalsBlocked():
            if not self._is_ok_to_change_settings(): # Check if change is allowed
                 self.padding_slider.blockSignals(True)
                 level_padding = self._padding_to_level(self.settings.get("rect_padding", DEFAULT_PADDING_VALUE))
                 self.padding_slider.setValue(level_padding)
                 self.padding_slider.blockSignals(False)
                 return # Don't update label or runtime if reverted

            self.rect_padding = self._level_to_padding(level)
            self.padding_value_label.setText(f"Level {level}")
            # Apply immediately for visual feedback in frame? (Optional)
            # self.apply_settings_to_runtime()

    def save_padding_level_setting(self):
        """Saves padding setting when slider is released."""
        if not self.padding_slider.signalsBlocked():
            if not self._is_ok_to_change_settings(): # Double-check on release
                 QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before changing settings.")
                 # Revert UI to saved setting
                 self.padding_slider.blockSignals(True)
                 level_padding = self._padding_to_level(self.settings.get("rect_padding", DEFAULT_PADDING_VALUE))
                 self.padding_slider.setValue(level_padding)
                 self.padding_value_label.setText(f"Level {level_padding}") # Also revert label
                 self.padding_slider.blockSignals(False)
                 return
            level = self.padding_slider.value()
            self.settings["rect_padding"] = self._level_to_padding(level)
            self.apply_settings_to_runtime() # Apply change to runtime variables
            self.save_current_profile_settings() # Save change to file

    def update_gap_level_display(self, level):
        """Updates gap value label when slider changes."""
        if not self.gap_level_slider.signalsBlocked():
            if not self._is_ok_to_change_settings(): # Check if change is allowed
                 self.gap_level_slider.blockSignals(True)
                 level_gap = self.settings.get('outer_gap_level', DEFAULT_GAP_LEVEL)
                 self.gap_level_slider.setValue(level_gap)
                 self.gap_level_slider.blockSignals(False)
                 return # Don't update label or runtime if reverted

            self.current_gap_level = level
            self.outer_rect_gap = self._level_to_gap_px(level)
            self.gap_level_value_label.setText(f"Level {level}")
            # Apply immediately for visual feedback? (Optional)
            # self.apply_settings_to_runtime()

    def save_gap_level_setting(self):
        """Saves gap setting when slider is released."""
        if not self.gap_level_slider.signalsBlocked():
            if not self._is_ok_to_change_settings(): # Double-check on release
                 QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before changing settings.")
                 # Revert UI to saved setting
                 self.gap_level_slider.blockSignals(True)
                 level_gap = self.settings.get('outer_gap_level', DEFAULT_GAP_LEVEL)
                 self.gap_level_slider.setValue(level_gap)
                 self.gap_level_value_label.setText(f"Level {level_gap}") # Also revert label
                 self.gap_level_slider.blockSignals(False)
                 return
            level = self.gap_level_slider.value()
            self.settings["outer_gap_level"] = level
            self.apply_settings_to_runtime() # Apply change
            self.save_current_profile_settings() # Save change

    def update_blink_threshold_selection(self, index):
        """Handles blink sensitivity dropdown change (user interaction)."""
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
                self.apply_settings_to_runtime() # Apply change
                self.save_current_profile_settings() # Save change

    def toggle_sticking(self, state_int):
        """Handles button sticking checkbox change."""
        if not self.sticking_checkbox.signalsBlocked():
            # state_int: 0=Unchecked, 1=PartiallyChecked(ignore), 2=Checked
            if state_int == 1: return
            enabled = (state_int == Qt.CheckState.Checked.value)

            if not self._is_ok_to_change_settings():
                 QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before changing settings.")
                 current_sticking = self.settings.get("enable_button_sticking", IS_WINDOWS) and IS_WINDOWS
                 self.sticking_checkbox.blockSignals(True)
                 self.sticking_checkbox.setChecked(current_sticking)
                 self.sticking_checkbox.blockSignals(False)
                 return

            if not IS_WINDOWS and enabled: # Prevent enabling if not on Windows
                self.sticking_checkbox.blockSignals(True)
                self.sticking_checkbox.setChecked(False) # Force uncheck
                self.sticking_checkbox.blockSignals(False)
                enabled = False
                self.show_error_message("Button Sticking is only available on Windows.")

            self.settings["enable_button_sticking"] = enabled
            self.apply_settings_to_runtime() # Apply change
            self.save_current_profile_settings() # Save change

    def toggle_highlight(self, state_int):
        """Handles cursor highlight checkbox change."""
        if not self.highlight_checkbox.signalsBlocked():
            if state_int == 1: return # Ignore partial state (shouldn't happen with 2-state checkbox)
            enabled = (state_int == Qt.CheckState.Checked.value)

            # Check if tutorial is active
            if not self._is_ok_to_change_settings():
                 QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before changing settings.")
                 # Revert UI change if tutorial is active
                 self.highlight_checkbox.blockSignals(True)
                 # Use the setting value, as runtime value might not be updated yet
                 current_highlight_setting = self.settings.get("enable_cursor_highlight", False)
                 self.highlight_checkbox.setChecked(current_highlight_setting)
                 self.highlight_checkbox.blockSignals(False)
                 return

            # Update runtime state and highlighter visibility
            self.enable_cursor_highlight = enabled
            self.cursor_highlighter.set_visibility(enabled)

            # If enabling, try to update position immediately
            if enabled:
                 try:
                     x, y = pyautogui.position()
                     self.cursor_highlighter.update_position(x, y)
                     # Set initial color based on current status
                     # Determine current status color more reliably
                     status_color_hex = COLOR_IDLE # Default
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
                         else: status_color_hex = COLOR_RUN # Default running color
                     elif not self._internal_tracking_active:
                         status_color_hex = COLOR_ERROR # System not ready
                     else:
                         status_color_hex = COLOR_IDLE # Idle and ready

                     self.cursor_highlighter.update_color(QColor(status_color_hex))

                 except Exception as e:
                     print(f"Error getting initial cursor pos for highlight: {e}")


            # Update setting in memory and save profile
            self.settings["enable_cursor_highlight"] = enabled
            self.save_current_profile_settings()


    # --- Core Logic Methods ---
    def initialize_face_mesh(self):
        """Initializes the MediaPipe Face Mesh model."""
        if self.face_mesh:
            try: self.face_mesh.close(); self.face_mesh = None
            except Exception as e: print(f"Error closing previous FaceMesh: {e}")
        print("Initializing MediaPipe Face Mesh..."); self.face_mesh = None
        try:
            # Adjusted confidence slightly
            self.face_mesh = MP_FACE_MESH.FaceMesh(max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.6, min_tracking_confidence=0.6)
            print("Face Mesh Initialized.")
        except Exception as e:
            print(f"FATAL: Error initializing FaceMesh: {e}"); self.face_mesh = None
            self.show_error_message(f"Failed to initialize MediaPipe Face Mesh:\n{e}\nTracking disabled.")

    def init_camera(self, index, preferred_backend="Default"):
        """Attempts to initialize the camera at the given index."""
        if self.cam and self.cam.isOpened():
            print("Releasing previous camera..."); self.cam.release(); self.cam = None

        print(f"Attempting camera index {index} (Preferred Backend: {preferred_backend})...")
        self.cam = None; success = False
        # Define potential backend APIs to try
        backends_to_try = []
        if IS_WINDOWS: backends_to_try.append((cv2.CAP_DSHOW, "DSHOW"))
        backends_to_try.append((cv2.CAP_ANY, "CAP_ANY")) # Always try default

        for api, backend_str in backends_to_try:
            # Only retry CAP_ANY if it wasn't the preferred backend that failed
            if preferred_backend != "Default" and api == cv2.CAP_ANY and any(b[1] == preferred_backend for b in backends_to_try):
                 if self.cam is None: # Check if preferred backend failed
                     print(f"  Skipping CAP_ANY retry as preferred backend {preferred_backend} already tried.")
                     # Continue # Actually, let's allow trying CAP_ANY anyway as a fallback
                 else: pass # Preferred succeeded or wasn't tried yet.


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
                    success = True; break # Success!
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


    # --- Status & Performance Update ---
    def update_status(self, text, color_hex):
        """Updates the status label with text and background color."""
        # Determine text color (black/white) based on background luminance
        try:
            r, g, b = int(color_hex[1:3], 16), int(color_hex[3:5], 16), int(color_hex[5:7], 16)
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            text_color = "black" if luminance > 0.5 else "white"
        except Exception: text_color = "white" # Default to white on error

        style = f"QLabel {{ background-color: {color_hex}; color: {text_color}; border: 1px solid #333333; border-radius: 4px; padding: 5px; font-weight: bold; font-size: 11pt; }}"

        # Check if tutorial is active *after* setting style but *before* setting text/style on label
        is_tutorial_running = not (self.tutorial_state == TUTORIAL_STATE_IDLE or
                              self.tutorial_state == TUTORIAL_STATE_COMPLETE or
                              self.tutorial_state == TUTORIAL_STATE_SKIPPED)

        # Override status display during tutorial
        if is_tutorial_running:
            tut_style = f"QLabel {{ background-color: {COLOR_TUTORIAL}; color: black; border: 1px solid #333333; border-radius: 4px; padding: 5px; font-weight: bold; font-size: 11pt; }}"
            self.status_label.setText("Tutorial Active")
            self.status_label.setStyleSheet(tut_style)
            # Update highlighter color during tutorial as well
            if self.enable_cursor_highlight and self.cursor_highlighter:
                 self.cursor_highlighter.update_color(QColor(COLOR_TUTORIAL))
            return # Important: Return here to avoid overwriting tutorial status

        # --- Normal Status Update ---
        self.status_label.setText(text)
        self.status_label.setStyleSheet(style)

        # Update highlighter color based on this normal status
        if self.enable_cursor_highlight and self.cursor_highlighter:
            self.cursor_highlighter.update_color(QColor(color_hex))


    def update_performance_display(self):
        """Updates FPS and processing time labels."""
        now = time.perf_counter(); elapsed = now - self.last_frame_time; self.last_frame_time = now
        if elapsed > 1e-6: # Avoid division by zero
            current_fps = 1.0 / elapsed; self.fps_history.append(current_fps)
            avg_fps = sum(self.fps_history) / len(self.fps_history); self.fps_label.setText(f"FPS: {avg_fps:.1f}")
        # Display processing time from the end of the last update_frame call
        self.proc_time_label.setText(f"Proc: {self.frame_processing_time:.1f} ms")

    # --- Start/Stop Tracking ---
    def start_tracking(self):
        """Starts the main tracking and cursor control loop."""
        if not self._is_ok_to_change_settings(): # Show message if tutorial active
            QMessageBox.warning(self, "Tutorial Active", "Please complete or skip the tutorial before starting tracking.")
            return
        if self.running: return # Already running
        # Check if system is ready (camera and mediapipe initialized)
        if not (self.cam and self.cam.isOpened() and self.face_mesh and self._internal_tracking_active):
            self.update_status("System Not Ready", COLOR_ERROR); self.show_error_message("Cannot start: Camera or MediaPipe not ready."); return

        print("Tracking started.")
        self.running = True
        # Update UI state
        self.start_button.setEnabled(False); self.stop_button.setEnabled(True)
        self.set_settings_controls_enabled(False); self.rerun_tutorial_button.setVisible(False)
        self.update_status("Starting...", COLOR_START)
        # Reset state variables for a clean tracking session
        self.smooth_cursor.last_smoothed_gaze_target = None; self.smooth_cursor.last_raw_position = None
        self.smooth_cursor.position_history.clear(); self.smooth_cursor.reset_sticking()
        self.blink_start_time = 0; self.both_eyes_closed_start_time = 0
        self.last_both_eyes_closed_end_time = 0 # Reset double click timer state
        self.was_out_of_bounds = True; self.last_valid_gaze_normalized = None
        # Update status to "Tracking" after a short delay
        QTimer.singleShot(200, lambda: self.update_status("Tracking", COLOR_RUN) if self.running else None)

    def stop_tracking(self):
        """Stops the tracking and cursor control."""
        if not self.running: return # Already stopped
        print("Tracking stopped."); self.running = False
        # Determine if system is ready to start again
        can_start_again = (self.cam and self.cam.isOpened() and self.face_mesh and self._internal_tracking_active)
        # Update UI state
        self.start_button.setEnabled(can_start_again); self.stop_button.setEnabled(False)
        # Check if tutorial is finished to decide whether to re-enable settings
        is_tutorial_finished_or_idle = self._is_ok_to_change_settings()
        if is_tutorial_finished_or_idle:
            self.set_settings_controls_enabled(True); self.rerun_tutorial_button.setVisible(True)
            self.update_status("Idle", COLOR_IDLE if can_start_again else COLOR_ERROR) # Show error if system not ready
        else: # Keep controls disabled if tutorial is still active
            self.set_settings_controls_enabled(False); self.rerun_tutorial_button.setVisible(False)
            self.update_status("Tutorial Active", COLOR_TUTORIAL) # Status already handled by update_status logic

        # Reset state variables
        self.smooth_cursor.reset_sticking(); self.was_out_of_bounds = True; self.both_eyes_closed_start_time = 0
        self.blink_start_time = 0; self.last_both_eyes_closed_end_time = 0 # Reset double click timer state
        # Update highlighter color to idle/error state when stopping
        if self.enable_cursor_highlight and self.cursor_highlighter:
             idle_color = COLOR_ERROR if not can_start_again else COLOR_IDLE
             # Check if tutorial is still active, override color
             if not is_tutorial_finished_or_idle:
                 idle_color = COLOR_TUTORIAL
             self.cursor_highlighter.update_color(QColor(idle_color))


    # --- set_settings_controls_enabled (Highlight ADDED) ---
    def set_settings_controls_enabled(self, enabled):
        """Enables/disables settings controls, handling platform specifics."""
        widgets_to_toggle = [
            self.profile_combo, self.save_profile_button, self.delete_profile_button,
            self.camera_selector, self.padding_slider, self.gap_level_slider,
            self.blink_selector, self.sticking_checkbox, self.highlight_checkbox, # Added highlight checkbox
            self.padding_value_label, self.gap_level_value_label
        ]
        # Handle camera selector based on camera availability
        camera_available = self.camera_selector.count() > 0 and "No Cameras Found" not in self.camera_selector.itemText(0)
        self.camera_selector.setEnabled(enabled and camera_available)

        # Toggle other widgets
        for widget in widgets_to_toggle:
            if widget == self.camera_selector: continue # Handled above
            if widget:
                # Sticking checkbox only enabled on Windows AND if main toggle is enabled
                can_enable_widget = enabled and (IS_WINDOWS if widget == self.sticking_checkbox else True)
                try: widget.setEnabled(can_enable_widget)
                except Exception as e: print(f"Error setting enabled state for {widget}: {e}")

        # Special handling for delete button based on profile name
        if enabled:
             is_default_profile = (self.profile_combo.currentText() == "Default")
             if self.delete_profile_button: self.delete_profile_button.setEnabled(not is_default_profile)


    # --- update_frame (STATUS FIX INTEGRATED) ---
    def update_frame(self):
        """Main processing loop: Capture frame, detect face/eyes, calculate gaze, move cursor, detect clicks."""
        start_time_frame = time.perf_counter()
        self.update_performance_display() # Update FPS/Proc time display

        # --- Determine if Tutorial is Active ---
        is_tutorial_active = not (self.tutorial_state == TUTORIAL_STATE_IDLE or
                               self.tutorial_state == TUTORIAL_STATE_COMPLETE or
                               self.tutorial_state == TUTORIAL_STATE_SKIPPED)

        # --- Basic System Checks ---
        if not self._internal_tracking_active:
            if self.running: self.stop_tracking()
            # Update status only if NOT in tutorial and status not already reflecting the error
            if not is_tutorial_active:
                current_status_text = self.status_label.text()
                sys_error_detected = "CAM/MP Error" in current_status_text or \
                                    "CAM Error" in current_status_text or \
                                    "MP Init Fail" in current_status_text or \
                                    "System Not Ready" in current_status_text
                if not sys_error_detected:
                    error_msg = "System Not Ready" # Generic error if specific cause unknown
                    if not (self.cam and self.cam.isOpened() and self.face_mesh): error_msg = "CAM/MP Error"
                    elif not (self.cam and self.cam.isOpened()): error_msg = "CAM Error"
                    elif not self.face_mesh: error_msg = "MP Init Fail"
                    self.update_status(error_msg, COLOR_ERROR)
                # Also update highlighter if enabled
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

        # --- Frame Capture and Initial Processing ---
        try:
            ret, frame = self.cam.read()
            if not ret or frame is None:
                 if not is_tutorial_active:
                     if "Frame Read Err" not in self.status_label.text():
                         self.update_status("Frame Read Err", COLOR_ERROR); self.display_error_on_feed("Frame Read Fail")
                     if self.enable_cursor_highlight: self.cursor_highlighter.update_color(QColor(COLOR_ERROR))
                 return
            # Removed clearing error here - handled by the unified status logic below

            frame = cv2.flip(frame, 1); frame_h, frame_w, _ = frame.shape
            if frame_h <= 0 or frame_w <= 0: return # Invalid frame

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

        # --- Define Tracking and Clicking Areas ---
        rect_left = max(0, self.rect_padding); rect_right = min(frame_w - 1, frame_w - self.rect_padding)
        rect_top = max(0, self.rect_padding); rect_bottom = min(frame_h - 1, frame_h - self.rect_padding)
        rect_valid = (rect_right > rect_left and rect_bottom > rect_top)
        outer_left = max(0, rect_left - self.outer_rect_gap); outer_top = max(0, rect_top - self.outer_rect_gap)
        outer_right = min(frame_w - 1, rect_right + self.outer_rect_gap); outer_bottom = min(frame_h - 1, rect_bottom + self.outer_rect_gap)
        outer_valid = (outer_right > outer_left and outer_bottom > outer_top)

        # --- Face and Landmark Processing ---
        face_detected = False; target_x_px, target_y_px = -1, -1; mid_x_norm, mid_y_norm = -1.0, -1.0
        left_click, mid_click, double_click = False, False, False # Initialize click flags for this frame
        # Initialize gaze_in_click_bounds here
        gaze_in_click_bounds = False

        # --- Determine current state flags ---
        in_movement_bounds = False

        if output.multi_face_landmarks:
            face_detected = True
            landmarks = output.multi_face_landmarks[0].landmark
            l_iris_idx, r_iris_idx = 473, 468
            l_top, l_bot, r_top, r_bot = 159, 145, 386, 374
            max_lmk = max(l_iris_idx, r_iris_idx, l_top, l_bot, r_top, r_bot)

            if len(landmarks) > max_lmk:
                # --- Gaze Calculation ---
                try:
                    l_cx, l_cy = landmarks[l_iris_idx].x, landmarks[l_iris_idx].y; r_cx, r_cy = landmarks[r_iris_idx].x, landmarks[r_iris_idx].y
                    mid_x_norm, mid_y_norm = (l_cx + r_cx) / 2, (l_cy + r_cy) / 2
                    self.last_valid_gaze_normalized = (mid_x_norm, mid_y_norm)
                    target_x_px = int(mid_x_norm * frame_w); target_y_px = int(mid_y_norm * frame_h)
                    target_x_px = max(0, min(target_x_px, frame_w - 1)); target_y_px = max(0, min(target_y_px, frame_h - 1))
                    # Determine bounds check flags based on gaze calculation success
                    in_movement_bounds = rect_valid and (rect_left <= target_x_px <= rect_right and rect_top <= target_y_px <= rect_bottom)
                    gaze_in_click_bounds = outer_valid and target_x_px != -1 and (outer_left <= target_x_px <= outer_right and outer_top <= target_y_px <= outer_bottom)

                except (IndexError, TypeError) as e_gaze:
                     self.last_valid_gaze_normalized = None; target_x_px, target_y_px = -1,-1; mid_x_norm, mid_y_norm = -1.0, -1.0
                     in_movement_bounds = False # Cannot be in bounds if gaze calc failed
                     gaze_in_click_bounds = False
                     # Status will be handled by the unified logic below


                # --- Cursor Movement Logic (Only if running AND NOT in tutorial) ---
                if self.running and not is_tutorial_active and mid_x_norm != -1.0:
                    screen_x, screen_y = -1.0, -1.0
                    if in_movement_bounds:
                        if self.was_out_of_bounds:
                             self.smooth_cursor.position_history.clear(); self.smooth_cursor.last_smoothed_gaze_target = None; self.smooth_cursor.last_raw_position = None; # print("Re-entered bounds, smoother reset.")
                        # Status is handled below
                        effective_left = rect_left + EDGE_MAP_MARGIN_PX; effective_right = rect_right - EDGE_MAP_MARGIN_PX
                        effective_top = rect_top + EDGE_MAP_MARGIN_PX; effective_bottom = rect_bottom - EDGE_MAP_MARGIN_PX
                        if effective_right > effective_left and effective_bottom > effective_top:
                            effective_range_x = float(effective_right - effective_left); effective_range_y = float(effective_bottom - effective_top)
                            norm_x_raw = (float(target_x_px) - effective_left) / effective_range_x; norm_y_raw = (float(target_y_px) - effective_top) / effective_range_y
                            norm_x = max(0.0, min(1.0, norm_x_raw)); norm_y = max(0.0, min(1.0, norm_y_raw))
                            screen_x = norm_x * float(SCREEN_W); screen_y = norm_y * float(SCREEN_H)
                        else: # Fallback if margin too large
                            range_x, range_y = float(rect_right - rect_left), float(rect_bottom - rect_top)
                            if range_x > 0 and range_y > 0:
                                norm_x = max(0.0, min(1.0, (float(target_x_px) - rect_left) / range_x)); norm_y = max(0.0, min(1.0, (float(target_y_px) - rect_top) / range_y))
                                screen_x = norm_x * float(SCREEN_W); screen_y = norm_y * float(SCREEN_H)
                        self.was_out_of_bounds = False
                    else: # Out of movement bounds (but face detected)
                         # Status handled below
                         self.was_out_of_bounds = True; self.smooth_cursor.reset_sticking()

                    if screen_x != -1.0 and screen_y != -1.0:
                        screen_x = max(0.0, min(screen_x, float(SCREEN_W - 1))); screen_y = max(0.0, min(screen_y, float(SCREEN_H - 1)))
                        self.smooth_cursor.update_position(np.array([screen_x, screen_y]))
                elif not self.running and not is_tutorial_active:
                     # Status handled below
                     pass


                # --- Blink/Click Detection Logic (Always run if landmarks are good, needed for tutorial too) ---
                if self._internal_tracking_active: # Check if system is generally active
                    try:
                        l_y_top, l_y_bot = landmarks[l_top].y, landmarks[l_bot].y; r_y_top, r_y_bot = landmarks[r_top].y, landmarks[r_bot].y
                        l_v_dist = abs(l_y_top - l_y_bot); r_v_dist = abs(r_y_top - r_y_bot)
                        is_l_closed = l_v_dist < self.blink_threshold; is_r_closed = r_v_dist < self.blink_threshold
                        currently_both_closed = is_l_closed and is_r_closed
                        current_time = time.time()
                        # gaze_in_click_bounds already calculated above

                        # --- Double Click (Rapid Both Eyes Closed Twice) ---
                        if currently_both_closed:
                            if self.both_eyes_closed_start_time == 0: # Just closed both eyes
                                self.both_eyes_closed_start_time = current_time
                                # Check if this closure is within the interval of the *last* closure ending
                                if self.last_both_eyes_closed_end_time != 0 and (current_time - self.last_both_eyes_closed_end_time) <= self.double_blink_interval and gaze_in_click_bounds:
                                    double_click = True
                                    # Reset timers immediately after detecting double click
                                    self.both_eyes_closed_start_time = 0
                                    self.last_both_eyes_closed_end_time = 0
                        else: # Both eyes are not currently closed
                            if self.both_eyes_closed_start_time != 0: # Both eyes were closed, now just opened
                                duration_both_closed = current_time - self.both_eyes_closed_start_time
                                # Record the time this "both closed" event ended
                                self.last_both_eyes_closed_end_time = current_time

                                # --- Middle Click (Hold Both Eyes) --- Check duration *after* opening
                                # Only trigger if double click wasn't already detected this frame
                                if not double_click and duration_both_closed >= MIDDLE_CLICK_HOLD_DURATION and gaze_in_click_bounds:
                                    mid_click = True
                                    # Reset timers as the hold action is complete
                                    self.both_eyes_closed_start_time = 0
                                    self.last_both_eyes_closed_end_time = 0 # Reset end time too, middle click ends sequence
                                else:
                                    # Reset only the start time, keep the end time for potential double click
                                    self.both_eyes_closed_start_time = 0


                        # --- Left Click (Long Left Eye Only Blink) ---
                        # Only process if double or middle click didn't happen
                        if not double_click and not mid_click:
                             if is_l_closed and not is_r_closed: # Left eye just closed or is held closed
                                 if self.blink_start_time == 0: self.blink_start_time = current_time
                             else: # Left eye is open OR both eyes are closed (handled above)
                                 # If a left blink was in progress (blink_start_time is set), process its end
                                 if self.blink_start_time != 0:
                                     duration = current_time - self.blink_start_time
                                     blink_ended_in_bounds = gaze_in_click_bounds # Check bounds *at the moment eye opens*

                                     # Check only for LONG blink (Single Click)
                                     if blink_ended_in_bounds and duration >= self.long_blink_threshold:
                                         left_click = True
                                     # else: # Short blink ended in bounds, or any blink ended out of bounds - do nothing
                                         # print(f"Ignoring short/OOB left blink ({duration:.2f}s)") # Debug

                                     # Reset the single blink timer *after* processing the end event
                                     self.blink_start_time = 0

                    except (IndexError, TypeError) as e_blink:
                         print(f"Click logic error: {e_blink}")
                         # Status handled below
                         # Reset all blink timers on error
                         self.blink_start_time=0; self.both_eyes_closed_start_time=0; self.last_both_eyes_closed_end_time = 0

            else: # Not enough landmarks
                 face_detected = True # Face structure detected, but not enough landmarks
                 self.last_valid_gaze_normalized = None
                 in_movement_bounds = False # Cannot be in bounds if gaze calc failed
                 gaze_in_click_bounds = False
                 self.blink_start_time=0; self.both_eyes_closed_start_time=0; self.last_both_eyes_closed_end_time = 0
                 self.was_out_of_bounds = True; self.smooth_cursor.reset_sticking()
                 # Status handled below
        else: # No face detected
            face_detected = False # Explicitly set flag
            self.last_valid_gaze_normalized = None
            in_movement_bounds = False # Cannot be in bounds if face not detected
            gaze_in_click_bounds = False
            self.blink_start_time=0; self.both_eyes_closed_start_time=0; self.last_both_eyes_closed_end_time = 0
            self.was_out_of_bounds = True; self.smooth_cursor.reset_sticking()
            # Status handled below

        # --- Determine Desired Status (Unified Logic) ---
        desired_status_text = ""
        desired_status_color = ""
        # Default to Idle if system is active but no other condition met yet
        if self._internal_tracking_active:
            desired_status_text = "Idle"
            desired_status_color = COLOR_IDLE

        if is_tutorial_active:
            desired_status_text = "Tutorial Active"
            desired_status_color = COLOR_TUTORIAL
        elif not self._internal_tracking_active:
            # Error status should have been set by earlier checks, maintain it
            desired_status_text = self.status_label.text() # Keep existing error text
            # Determine color based on text (crude but best guess)
            if "CAM/MP" in desired_status_text or "CAM E" in desired_status_text or "MP Init" in desired_status_text or "Not Ready" in desired_status_text:
                desired_status_color = COLOR_ERROR
            else: # Fallback if error text not recognized
                 desired_status_color = COLOR_ERROR
        elif self.running:
            if not face_detected:
                desired_status_text = "No Face!"
                desired_status_color = COLOR_ERROR
            elif self.last_valid_gaze_normalized is None: # Gaze calculation failed (e.g., not enough landmarks)
                 desired_status_text = "Gaze Error"
                 desired_status_color = COLOR_WARN
            elif not rect_valid or not outer_valid: # Invalid configuration somehow
                 desired_status_text = "Config Error"
                 desired_status_color = COLOR_WARN
            elif in_movement_bounds:
                desired_status_text = "Tracking"
                desired_status_color = COLOR_RUN
            else: # Running, face detected, gaze valid, but out of bounds
                desired_status_text = "Out of Bounds"
                desired_status_color = COLOR_WARN
        else: # Not running, but system is active (_internal_tracking_active is True)
            desired_status_text = "Idle"
            desired_status_color = COLOR_IDLE

        # --- Update Status Label if Changed ---
        current_status_text = self.status_label.text()
        # Make comparison case-insensitive just in case and check if colors differ too
        if desired_status_text and (desired_status_text.lower() != current_status_text.lower() or self.status_label.styleSheet().find(desired_status_color) == -1) :
            self.update_status(desired_status_text, desired_status_color)

        # --- Set Color for Drawing/Highlighting ---
        # Use the determined desired color, defaulting to Idle if somehow empty
        final_frame_status_color_hex = desired_status_color if desired_status_color else COLOR_IDLE

        # --- Trigger Actions (Tutorial or Actual Clicks) ---
        action_taken = False # Flag to reset timers only once if any action occurred
        if is_tutorial_active:
             # IMPORTANT: Check the tutorial state *before* checking the click type
             if self.tutorial_state == TUTORIAL_STATE_WAITING_LEFT_CLICK and left_click:
                 print("Tutorial: Left Click Detected")
                 self.advance_tutorial(TUTORIAL_STATE_SHOWING_LEFT_SUCCESS); action_taken = True
             elif self.tutorial_state == TUTORIAL_STATE_WAITING_DOUBLE_CLICK and double_click:
                 print("Tutorial: Double Click Detected")
                 self.advance_tutorial(TUTORIAL_STATE_SHOWING_DOUBLE_SUCCESS); action_taken = True
             elif self.tutorial_state == TUTORIAL_STATE_WAITING_MIDDLE_CLICK and mid_click:
                 print("Tutorial: Middle Click Detected")
                 self.advance_tutorial(TUTORIAL_STATE_SHOWING_MIDDLE_SUCCESS); action_taken = True
             # No else needed, just ignore other clicks during tutorial waiting states
             # Color already set by unified logic above

        elif self.running: # Only perform actions if tracking is enabled AND not in tutorial
            # Check in order: double -> middle -> left
            if double_click:
                print(">>> PyAutoGUI: Double Click")
                try: pyautogui.doubleClick(_pause=False)
                except Exception as e_click: print(f"Error during pyautogui doubleClick: {e_click}")
                self.smooth_cursor.reset_sticking() # Reset sticking after any click
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
                 self.smooth_cursor.reset_sticking() # Reset sticking after any click
                 action_taken = True

        # If an action was taken (either tutorial advance or actual click), ensure relevant timers are reset
        if action_taken:
            self.blink_start_time = 0
            self.both_eyes_closed_start_time = 0
            self.last_both_eyes_closed_end_time = 0


        # --- Update Cursor Highlighter ---
        if self.enable_cursor_highlight and self.cursor_highlighter:
            try:
                cursor_x, cursor_y = pyautogui.position() # Get *actual* cursor pos for highlight
                self.cursor_highlighter.update_position(cursor_x, cursor_y)
                # Use the *final* determined status color for the frame
                self.cursor_highlighter.update_color(QColor(final_frame_status_color_hex))
            except Exception as e_highlight:
                # print(f"Error updating highlighter: {e_highlight}") # Debug only
                self.cursor_highlighter.hide() # Hide on error getting position etc.

        # --- Drawing on Frame (Visual Feedback) ---
        # Determine inner rect color based on the final status color derived this frame
        cv_inner_color = hex_to_bgr(final_frame_status_color_hex)
        cv_outer_color = hex_to_bgr(COLOR_INFO_BLUE) # Click area always blue outline
        if rect_valid: cv2.rectangle(bgr_frame_draw, (rect_left, rect_top), (rect_right, rect_bottom), cv_inner_color, 2)
        if outer_valid: cv2.rectangle(bgr_frame_draw, (outer_left, outer_top), (outer_right, outer_bottom), cv_outer_color, 1)
        if target_x_px != -1:
             # Gaze color matches inner rect color (status/tutorial)
             gaze_color = cv_inner_color
             cv2.circle(bgr_frame_draw, (target_x_px, target_y_px), 5, gaze_color, -1)
             cv2.circle(bgr_frame_draw, (target_x_px, target_y_px), 6, (255, 255, 255), 1) # White outline

        # --- Display Frame and Timing ---
        self.display_frame(bgr_frame_draw)
        end_time_frame = time.perf_counter()
        self.frame_processing_time = (end_time_frame - start_time_frame) * 1000


    # --- Tutorial Methods (Highlight Info ADDED, Renumbered, Robustness Improved) ---
    def run_tutorial(self, current_state=TUTORIAL_STATE_SHOWING_INTRO):
        """Starts or continues the interactive tutorial."""
        if not (self._internal_tracking_active and self.face_mesh and self.cam and self.cam.isOpened()):
            QMessageBox.warning(self, "Tutorial Error", "Cannot start tutorial: Camera or MediaPipe not ready.")
            self.mark_tutorial_skipped(); return

        print(f"Running tutorial state: {current_state}")
        self.tutorial_state = current_state
        # Force status update to Tutorial color/text (will be handled correctly by update_status logic now)
        # self.update_status("Tutorial Active", COLOR_TUTORIAL)

        # Disable controls and stop tracking if running
        self.set_settings_controls_enabled(False)
        self.start_button.setEnabled(False); self.stop_button.setEnabled(False)
        self.rerun_tutorial_button.setVisible(False)
        if self.running: self.stop_tracking()

        # Switch to tutorial panel
        self.right_stack.setCurrentWidget(self.tutorial_widget)

        # *** CRITICAL: Reset click state variables BEFORE entering a WAITING state ***
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

        # Configure UI elements for the current state
        text, instruction, next_visible, next_text, next_action, skip_visible = "", "", False, "Next", None, True

        # Use QColor constants for richer text formatting
        highlight_gaze_hex = COLOR_TUTORIAL # Using Tutorial color for gaze/move area in explanation
        highlight_click_hex = COLOR_INFO_BLUE # Using InfoBlue for click area explanation
        status_run_hex = COLOR_RUN
        status_idle_hex = COLOR_IDLE
        status_warn_hex = COLOR_WARN
        status_error_hex = COLOR_ERROR
        # Use a small square character (Unicode U+25A0 or similar) for the color legend
        color_block = "■"

        if current_state == TUTORIAL_STATE_SHOWING_INTRO:
            text = (f"Welcome to <b>CursorViaCam</b>!<br><br>"
                    f"This tutorial guides you through basic eye gesture controls. Ensure your face is centered and well-lit.<br><br>"
                    f"On the camera feed:<br>"
                    f"&nbsp;&nbsp;<font color='{highlight_gaze_hex}'>⬤</font> Gaze Position<br>"
                    f"&nbsp;&nbsp;<font color='{highlight_gaze_hex}'>□</font> Movement Area (Inner Box)<br>" # Use Square outline
                    f"&nbsp;&nbsp;<font color='{highlight_click_hex}'>□</font> Click Area (Outer Box)")    # Use Square outline
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
              # Transition to the NEW Highlighter Info step
              text = "<b>Excellent!</b> Middle click detected."; instruction = "Click 'Next' to learn about the status highlighter."; next_visible = True; next_action = lambda: self.run_tutorial(TUTORIAL_STATE_SHOWING_HIGHLIGHTER_INFO)

        # --- REVISED HIGHLIGHTER STEP ---
        elif current_state == TUTORIAL_STATE_SHOWING_HIGHLIGHTER_INFO:
            text = (f"<b>Step 4: Cursor Highlighter (Optional)</b><br><br>"
                    f"A colored ring around your cursor shows the tracking status:<br>"
                    f"<br>" # Extra space for clarity
                    f"&nbsp;&nbsp;<font color='{status_run_hex}'>{color_block}</font> <b>Tracking:</b> Cursor is actively controlled.<br>"
                    f"&nbsp;&nbsp;<font color='{status_idle_hex}'>{color_block}</font> <b>Idle / Ready:</b> System ready, tracking paused.<br>"
                    f"&nbsp;&nbsp;<font color='{status_warn_hex}'>{color_block}</font> <b>Warn / Bounds:</b> Out of bounds or minor issue.<br>"
                    f"&nbsp;&nbsp;<font color='{status_error_hex}'>{color_block}</font> <b>Error / No Face:</b> Major issue or face lost.<br>"
                    f"&nbsp;&nbsp;<font color='{COLOR_TUTORIAL}'>{color_block}</font> <b>Tutorial:</b> You are in the tutorial.<br>"
                    f"<br>" # Extra space
                    f"Enable/disable this in the main panel via the 'Cursor Highlighter' checkbox.")
            instruction = "Click 'Next' for a settings overview."
            next_visible = True; next_action = lambda: self.run_tutorial(TUTORIAL_STATE_SHOWING_CONTROLS_INFO)


        # --- REFINED SETTINGS INFO STEP ---
        elif current_state == TUTORIAL_STATE_SHOWING_CONTROLS_INFO: # Renumbered Step
             text = ("<b>Step 5: Settings Overview</b><br><br>"
                     "You can adjust settings later in the main panel:<br>"
                     "<ul>" # Use unordered list for better structure
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

        # Update UI text and button states
        full_text = f"{text}<br><br><b>{instruction}</b>" if instruction else text
        # Ensure the label uses rich text formatting
        self.tutorial_text_label.setTextFormat(Qt.TextFormat.RichText)
        self.tutorial_text_label.setText(full_text)
        self.tutorial_next_button.setText(next_text); self.tutorial_next_button.setVisible(next_visible)
        self.tutorial_skip_button.setVisible(skip_visible)

        # Disconnect previous signal before connecting new one
        try: self.tutorial_next_button.clicked.disconnect()
        except TypeError: pass # Ignore if no connection exists
        if next_action: self.tutorial_next_button.clicked.connect(next_action)

    def advance_tutorial(self, next_state):
        """Advances the tutorial state, intended to be called *after* a gesture is detected."""
        # Ensure we are actually in a state waiting for a gesture
        waiting_states = [
            TUTORIAL_STATE_WAITING_LEFT_CLICK,
            TUTORIAL_STATE_WAITING_DOUBLE_CLICK,
            TUTORIAL_STATE_WAITING_MIDDLE_CLICK
        ]
        if self.tutorial_state in waiting_states:
             print(f"Tutorial advancing from {self.tutorial_state} to {next_state}")
             # Use QTimer to schedule the state change, preventing potential issues
             # if called directly from within the event loop processing (update_frame).
             QTimer.singleShot(10, lambda: self.run_tutorial(next_state))
        else:
            print(f"Warning: Tried to advance tutorial from non-waiting state {self.tutorial_state}")


    def _end_tutorial(self, skipped=False):
        """Common logic for ending the tutorial."""
        end_state = TUTORIAL_STATE_SKIPPED if skipped else TUTORIAL_STATE_COMPLETE
        print(f"Tutorial {'skipped' if skipped else 'completed'}.")
        self.tutorial_state = end_state; self.tutorial_completed = True
        self.all_profiles_data["tutorial_completed"] = True; save_profiles(self.all_profiles_data)

        # Switch back to control panel
        self.right_stack.setCurrentWidget(self.control_frame)

        # Re-enable controls based on system readiness
        self.set_settings_controls_enabled(True)
        can_start = (self.cam and self.cam.isOpened() and self.face_mesh and self._internal_tracking_active)
        self.start_button.setEnabled(can_start); self.stop_button.setEnabled(self.running) # Stop button only enabled if it was somehow left running
        self.rerun_tutorial_button.setVisible(True)

        # Update status label and highlighter color to reflect idle/ready state
        final_status_color = COLOR_ERROR if not can_start else COLOR_IDLE
        final_status_text = "Init Error" if not can_start else "Idle"
        self.update_status(final_status_text, final_status_color) # This will set the correct color

        msg = "Tutorial skipped." if skipped else "Tutorial complete!"; QMessageBox.information(self, "Tutorial", msg)

    def mark_tutorial_complete(self): self._end_tutorial(skipped=False)
    def mark_tutorial_skipped(self): self._end_tutorial(skipped=True)

    # --- Frame Display & UI Update Helpers ---
    def display_frame(self, frame_bgr):
        """Displays the processed BGR frame in the camera label."""
        if frame_bgr is None: self.display_error_on_feed("No Frame Data"); return
        try:
            h, w, ch = frame_bgr.shape; bytes_per_line = ch * w
            if h <= 0 or w <= 0: return
            rgb_image = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            if qt_image.isNull(): self.display_error_on_feed("Frame Convert Error"); return
            pixmap = QPixmap.fromImage(qt_image)
            scaled_pixmap = pixmap.scaled(self.camera_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            # Create a black background pixmap matching the label size
            bg_pixmap = QPixmap(self.camera_label.size())
            bg_pixmap.fill(Qt.GlobalColor.black)
            # Paint the scaled video frame onto the black background, centered
            painter = QPainter(bg_pixmap)
            x = (bg_pixmap.width() - scaled_pixmap.width()) // 2
            y = (bg_pixmap.height() - scaled_pixmap.height()) // 2
            painter.drawPixmap(QPoint(x, y), scaled_pixmap)
            painter.end()
            # Set the final composited pixmap on the label
            self.camera_label.setPixmap(bg_pixmap); self.camera_label.setText("") # Clear any previous error text
        except Exception as e:
            print(f"Error displaying frame: {e}"); self.display_error_on_feed(f"Frame Display Error:\n{e}")


    def display_error_on_feed(self, text):
         """Displays an error message directly on the camera feed label."""
         try:
             pixmap = QPixmap(self.camera_label.size()); pixmap.fill(Qt.GlobalColor.black)
             painter = QPainter(pixmap); painter.setPen(Qt.GlobalColor.red); font = painter.font(); font.setPointSize(12); font.setBold(True); painter.setFont(font)
             text_rect = pixmap.rect().adjusted(10, 10, -10, -10)
             painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text); painter.end()
             self.camera_label.setPixmap(pixmap); self.camera_label.setText("")
         except Exception as e:
             print(f"Error displaying error on feed: {e}")
             # Fallback: Set text directly on label
             self.camera_label.setPixmap(QPixmap()) # Clear existing pixmap
             self.camera_label.setText(text); self.camera_label.setStyleSheet("background-color: black; color: red; border: 1px solid gray;"); self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)


    # --- save_current_profile_settings ---
    def save_current_profile_settings(self):
        """Updates the active profile's settings in memory FROM THE UI and saves all profiles to file."""
        # Allow saving even if tutorial is active, just don't allow *changing* settings during tutorial
        # if not self._is_ok_to_change_settings(): return

        if not self.active_profile_name or self.active_profile_name not in self.all_profiles_data.get("profiles", {}):
            print(f"Warning: Cannot save. Active profile '{self.active_profile_name}' invalid.")
            return
        # Ensure self.settings reflects the *current state of the UI controls* before saving
        self.update_settings_from_runtime() # Syncs self.settings with UI state
        # Update the profile data in the main dictionary
        self.all_profiles_data["profiles"][self.active_profile_name] = self.settings.copy()
        self.all_profiles_data["tutorial_completed"] = self.tutorial_completed # Save tutorial status too
        save_profiles(self.all_profiles_data) # Write the entire structure to file
        # print(f"Saved settings for profile: {self.active_profile_name}")

    # --- update_settings_from_runtime (Highlight & Double Click Interval ADDED) ---
    def update_settings_from_runtime(self):
        """Updates self.settings dict from the current state of UI widgets."""
        # Ensure UI elements exist before accessing them
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
            self.settings["enable_cursor_highlight"] = self.highlight_checkbox.isChecked() # Get highlight state

        if hasattr(self, 'camera_selector'):
            qt_cam_idx = self.camera_selector.currentIndex()
            if qt_cam_idx >= 0:
                cam_index_data = self.camera_selector.itemData(qt_cam_idx)
                if cam_index_data is not None and isinstance(cam_index_data, int):
                    self.settings["camera_index"] = cam_index_data
                elif self.available_cameras: # Fallback if data missing but cameras exist
                    try: # Protect against index error if no cameras listed in UI somehow
                        first_cam_data = self.camera_selector.itemData(0)
                        self.settings["camera_index"] = first_cam_data if first_cam_data is not None else 0
                    except Exception:
                        self.settings["camera_index"] = self.settings.get("camera_index", 0) # Keep old or default
                else: # No cameras available, keep old setting or default
                    self.settings["camera_index"] = self.settings.get("camera_index", 0)

        # Ensure internal params are also in self.settings if they could change
        if hasattr(self, 'smooth_cursor'):
            self.settings["smooth_window_internal"] = self.smooth_cursor.smoothing_window
        # Ensure click thresholds are stored (they aren't directly settable via simple UI widgets currently)
        self.settings["long_blink_threshold"] = self.settings.get("long_blink_threshold", get_default_settings()["long_blink_threshold"])
        self.settings["double_blink_interval"] = self.settings.get("double_blink_interval", get_default_settings()["double_blink_interval"]) # Keep stored interval


    # --- closeEvent ---
    def closeEvent(self, event):
        """Handles application closing: stops tracking, saves settings, releases resources."""
        print("Closing application...")
        self.running = False; self._internal_tracking_active = False
        if self.timer.isActive(): self.timer.stop()

        # Ensure highlighter window is closed
        if self.cursor_highlighter:
            self.cursor_highlighter.close()
            print("Closed highlighter window.")

        # Set UI to a safe state before potential save
        self.right_stack.setCurrentWidget(self.control_frame)

        # Save settings before exiting
        is_tutorial_running_on_close = not (self.tutorial_state == TUTORIAL_STATE_IDLE or
                                            self.tutorial_state == TUTORIAL_STATE_COMPLETE or
                                            self.tutorial_state == TUTORIAL_STATE_SKIPPED)

        if not is_tutorial_running_on_close: # If tutorial wasn't active
            if self.active_profile_name in self.all_profiles_data.get("profiles", {}):
                print(f"Saving final settings for profile: {self.active_profile_name}")
                self.save_current_profile_settings() # Saves current UI state + tutorial completed status
            else: # Active profile invalid, just save tutorial status
                 print(f"Warning: Active profile '{self.active_profile_name}' not found. Saving only tutorial status.")
                 self.all_profiles_data["tutorial_completed"] = self.tutorial_completed # Already True/False
                 save_profiles(self.all_profiles_data)
        else: # Tutorial was active during close
             print("Tutorial active on close. Saving status as incomplete.")
             self.tutorial_completed = False # Mark as incomplete
             self.all_profiles_data["tutorial_completed"] = False
             # Still try to save current settings state for the active profile
             if self.active_profile_name in self.all_profiles_data.get("profiles", {}):
                 self.update_settings_from_runtime() # Get UI state
                 self.all_profiles_data["profiles"][self.active_profile_name] = self.settings.copy()
             save_profiles(self.all_profiles_data) # Save profile data + incomplete tutorial status

        # Release hardware
        if self.cam is not None and self.cam.isOpened(): print("Releasing camera..."); self.cam.release(); self.cam = None
        if self.face_mesh is not None: print("Closing MediaPipe..."); self.face_mesh.close(); self.face_mesh = None

        print("Exiting."); event.accept()

# --- Helper Function ---
def hex_to_bgr(hex_color):
    """Converts a hex color string (e.g., '#FF0000') to a BGR tuple."""
    h = hex_color.lstrip('#')
    try:
        if len(h) == 3: h = h[0]*2 + h[1]*2 + h[2]*2 # Expand shorthand hex
        if len(h) != 6: raise ValueError("Invalid hex length")
        r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
        return (b, g, r) # BGR for OpenCV
    except Exception: return (128, 128, 128) # Default grey on error

# --- Main Execution ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Set App Style (Optional - for better consistency across platforms)
    # app.setStyle('Fusion')
    window = CursorViaCamApp()
    window.show()
    sys.exit(app.exec())
# <<< End of Python Code >>>