import pyautogui
import numpy as np
from collections import deque
import time
import platform

from constants import IS_WINDOWS, DEFAULT_BASE_GAIN, DEFAULT_ACCELERATION, DEFAULT_MIN_FACTOR, DEFAULT_MAX_FACTOR

if IS_WINDOWS:
    try:
        import win32gui
        import win32api
    except ImportError:
        print("Warning: 'pywin32' not installed. Button sticking feature will be disabled.")
        IS_WINDOWS = False

class SmoothCursor:
    """Handles cursor smoothing, adaptive speed, button sticking, and drift correction."""
    def __init__(self):
        self.smoothing_window = 6 # Default if not loaded
        self.speed_gain = DEFAULT_BASE_GAIN
        self.acceleration = DEFAULT_ACCELERATION
        self.min_speed_factor = DEFAULT_MIN_FACTOR
        self.max_speed_factor = DEFAULT_MAX_FACTOR
        self.enable_sticking = IS_WINDOWS
        self.stick_threshold = 25
        self.stick_release_multiplier = 1.8
        self.stick_search_radius = 100
        self.stick_check_interval = 0.2
        self.last_stick_check_time = 0
        self.sticking_to_button = False
        self.stick_position = None
        self.position_history = deque(maxlen=self.smoothing_window)
        self.last_raw_position = None
        self.last_smoothed_gaze_target = None
        self.current_speed_multiplier = self.min_speed_factor
        self.screen_width = 0
        self.screen_height = 0
        self._get_screen_dimensions()

    def _get_screen_dimensions(self):
        """Gets screen dimensions using appropriate method."""
        if IS_WINDOWS:
            try:
                self.screen_width = win32api.GetSystemMetrics(0)
                self.screen_height = win32api.GetSystemMetrics(1)
                if self.screen_width <= 0 or self.screen_height <= 0:
                    raise ValueError("win32api returned non-positive dimensions")
            except Exception as e_size_win:
                print(f"Warning: win32api.GetSystemMetrics failed: {e_size_win}. Falling back to pyautogui.")
                self._get_screen_dimensions_pyautogui()
        else:
            self._get_screen_dimensions_pyautogui()

    def _get_screen_dimensions_pyautogui(self):
        """Fallback method using pyautogui for screen dimensions."""
        try:
            self.screen_width, self.screen_height = pyautogui.size()
            if self.screen_width <= 0 or self.screen_height <= 0:
                raise ValueError("pyautogui returned non-positive dimensions")
        except Exception as e_size_py:
            print(f"Warning: Could not get screen dimensions for sticking filter: {e_size_py}")
            self.screen_width = 1920
            self.screen_height = 1080
            print(f"SmoothCursor: Using fallback screen dimensions: {self.screen_width}x{self.screen_height}")

    def update_position(self, raw_screen_pos):
        """Updates cursor position based on raw input, applying smoothing, adaptive speed, sticking, and drift correction."""
        raw_screen_pos = np.array(raw_screen_pos)

        current_time = time.time()
        if self.enable_sticking and IS_WINDOWS and (current_time - self.last_stick_check_time > self.stick_check_interval):
            self.last_stick_check_time = current_time
            try:
                current_cursor_pos_tuple = pyautogui.position()
            except Exception as e_pos:
                current_cursor_pos_tuple = (self.last_smoothed_gaze_target[0], self.last_smoothed_gaze_target[1]) if self.last_smoothed_gaze_target is not None else (self.screen_width // 2, self.screen_height // 2)

            current_cursor_pos = np.array(current_cursor_pos_tuple)

            if self.sticking_to_button:
                if self.stick_position is None:
                    self.sticking_to_button = False
                else:
                    intended_distance_from_stick = np.linalg.norm(raw_screen_pos - self.stick_position)
                    if intended_distance_from_stick > self.stick_threshold * self.stick_release_multiplier * 1.1:
                        self.sticking_to_button = False; self.stick_position = None
                        self.position_history.clear(); self.last_smoothed_gaze_target = None; self.last_raw_position = None
                    else:
                        if np.linalg.norm(current_cursor_pos - self.stick_position) > 1:
                            stick_x = max(0, min(int(self.stick_position[0]), self.screen_width - 1))
                            stick_y = max(0, min(int(self.stick_position[1]), self.screen_height - 1))
                            try:
                                pyautogui.moveTo(stick_x, stick_y, _pause=False)
                            except Exception as e_move:
                                print(f"Error during stick moveTo: {e_move}")

                        self.position_history.append(raw_screen_pos)
                        self.last_smoothed_gaze_target = self.stick_position
                        self.last_raw_position = raw_screen_pos
                        return

            if not self.sticking_to_button:
                nearest_button_pos = self._find_nearest_clickable_win32(current_cursor_pos, self.screen_width, self.screen_height)
                if nearest_button_pos is not None:
                    distance_to_button = np.linalg.norm(current_cursor_pos - nearest_button_pos)
                    intended_move_vector = raw_screen_pos - current_cursor_pos
                    cursor_to_button_vector = nearest_button_pos - current_cursor_pos
                    norm_intended = np.linalg.norm(intended_move_vector)
                    norm_button = np.linalg.norm(cursor_to_button_vector)
                    dot_product = 0.0
                    if norm_intended > 1e-6 and norm_button > 1e-6:
                        dot_product = np.dot(intended_move_vector / norm_intended, cursor_to_button_vector / norm_button)

                    should_stick = (distance_to_button < self.stick_threshold and
                                    (dot_product > -0.1 or norm_intended < 5 or distance_to_button < self.stick_threshold * 0.6 ))

                    if should_stick:
                        self.sticking_to_button = True; self.stick_position = nearest_button_pos
                        stick_x = max(0, min(int(self.stick_position[0]), self.screen_width - 1))
                        stick_y = max(0, min(int(self.stick_position[1]), self.screen_height - 1))
                        try:
                            pyautogui.moveTo(stick_x, stick_y, _pause=False)
                        except Exception as e_move:
                             print(f"Error during initial stick moveTo: {e_move}")
                        self.position_history.clear(); self.position_history.append(self.stick_position)
                        self.last_smoothed_gaze_target = self.stick_position
                        self.last_raw_position = raw_screen_pos
                        return

        self.position_history.append(raw_screen_pos)

        if len(self.position_history) < 1:
            self.last_raw_position = raw_screen_pos
            return

        smoothed_gaze_target = np.mean(self.position_history, axis=0)

        try:
            current_x, current_y = pyautogui.position()
            current_cursor_pos = np.array([current_x, current_y])
        except Exception as e_pos:
            if self.last_smoothed_gaze_target is not None:
                current_cursor_pos = self.last_smoothed_gaze_target
            else:
                 current_cursor_pos = np.array([self.screen_width // 2, self.screen_height // 2])

        if self.last_raw_position is not None:
            raw_movement_vector = raw_screen_pos - self.last_raw_position
            raw_movement_distance = np.linalg.norm(raw_movement_vector)
            self.current_speed_multiplier = np.clip(
                raw_movement_distance * self.acceleration + self.min_speed_factor,
                self.min_speed_factor,
                self.max_speed_factor
            )
        else:
             self.current_speed_multiplier = self.min_speed_factor

        error_vector = smoothed_gaze_target - current_cursor_pos
        error_distance = np.linalg.norm(error_vector)

        distance_scaling_factor = min(1.0 + error_distance / 40.0, 2.0)

        applied_gain = self.speed_gain * self.current_speed_multiplier * distance_scaling_factor
        applied_gain = min(applied_gain, 1.0)

        cursor_movement_step = error_vector * applied_gain

        new_x_f = current_cursor_pos[0] + cursor_movement_step[0]
        new_y_f = current_cursor_pos[1] + cursor_movement_step[1]

        new_x = int(max(0, min(new_x_f, self.screen_width - 1)))
        new_y = int(max(0, min(new_y_f, self.screen_height - 1)))

        if not self.sticking_to_button and (abs(new_x - int(current_cursor_pos[0])) > 0 or abs(new_y - int(current_cursor_pos[1])) > 0):
             try:
                 pyautogui.moveTo(new_x, new_y, duration=0, _pause=False)
             except Exception as e_move:
                 print(f"Error during normal moveTo: {e_move}")

        self.last_smoothed_gaze_target = smoothed_gaze_target
        self.last_raw_position = raw_screen_pos

    def _find_nearest_clickable_win32(self, position, screen_w, screen_h):
        """Finds the center of the nearest clickable UI element within search radius on Windows."""
        if not IS_WINDOWS: return None
        buttons = []; target_pos = np.array(position); search_radius_sq = self.stick_search_radius ** 2
        max_sensible_width = screen_w * 0.80; max_sensible_height = screen_h * 0.80
        min_sensible_dimension = 5
        clickable_classes = [
            'Button', 'TButton', 'WindowsForms10.BUTTON.*', 'WindowsForms10.CHECKBOX.*',
            'WindowsForms10.RADIOBUTTON.*', 'CheckBox', 'RadioButton', 'ComboBox', 'ListBox',
            'msctls_trackbar32', 'msctls_updown32', 'ScrollBar', 'SysLink', 'SysListView32',
            'SysTreeView32', 'ToolbarWindow32', 'ReBarWindow32', 'TabControl', 'SysTabControl32',
            'MenuItem'
        ]
        ignore_classes = [
            'Shell_TrayWnd', 'Progman', 'WorkerW', 'Internet Explorer_Server', 'Static', 'Edit',
            'IME', 'MSCTFIME UI', '#32768', 'tooltips_class32', 'SysHeader32',
            'SysPager', 'msctls_statusbar32',
            '#32769',
            'ComboLBox',
        ]

        def enum_windows_proc(hwnd, lParam):
            nonlocal buttons
            try:
                if not win32gui.IsWindowVisible(hwnd) or not win32gui.IsWindowEnabled(hwnd): return True
                class_name = win32gui.GetClassName(hwnd); rect = win32gui.GetWindowRect(hwnd)
                if class_name in ignore_classes: return True
                if class_name.startswith("Windows.UI.") or class_name.startswith("ApplicationFrameWindow"): return True

                x, y, right, bottom = rect; w, h = right - x, bottom - y
                if w < min_sensible_dimension or h < min_sensible_dimension or right <= 0 or bottom <= 0 or x >= screen_w or y >= screen_h or w > screen_w or h > screen_h: return True
                if w > max_sensible_width or h > max_sensible_height: return True

                center_x, center_y = x + w // 2, y + h // 2
                dist_sq = (target_pos[0] - center_x)**2 + (target_pos[1] - center_y)**2

                if dist_sq > search_radius_sq: return True

                match = False
                import fnmatch
                for pattern in clickable_classes:
                    if '*' in pattern:
                        if fnmatch.fnmatch(class_name, pattern): match = True; break
                    elif class_name == pattern: match = True; break

                if not match and class_name == '#32768':
                    def enum_menu_items(menu_hwnd, _):
                        nonlocal buttons, match
                        try:
                            menu_class = win32gui.GetClassName(menu_hwnd)
                            if menu_class == 'MenuItem':
                                menu_rect = win32gui.GetWindowRect(menu_hwnd)
                                mx, my, mright, mbottom = menu_rect
                                mw, mh = mright-mx, mbottom-my
                                if mw < min_sensible_dimension or mh < min_sensible_dimension: return True
                                mcenter_x, mcenter_y = mx + mw // 2, my + mh // 2
                                mdist_sq = (target_pos[0] - mcenter_x)**2 + (target_pos[1] - mcenter_y)**2
                                if mdist_sq <= search_radius_sq and 0 <= mcenter_x < screen_w and 0 <= mcenter_y < screen_h:
                                    buttons.append({'pos': np.array([mcenter_x, mcenter_y]), 'dist': np.sqrt(mdist_sq), 'hwnd': menu_hwnd, 'class': menu_class, 'rect': menu_rect})
                                    match = True
                        except win32gui.error: pass
                        except Exception as e_menu: pass
                        return True
                    win32gui.EnumChildWindows(hwnd, enum_menu_items, None)

                if match and not any(b['hwnd'] == hwnd for b in buttons):
                    if 0 <= center_x < screen_w and 0 <= center_y < screen_h:
                        button_center = np.array([center_x, center_y])
                        buttons.append({'pos': button_center, 'dist': np.sqrt(dist_sq), 'hwnd': hwnd, 'class': class_name, 'rect': rect})

            except win32gui.error: pass
            except Exception as e_enum:
                pass
            return True

        try:
            fg_hwnd = win32gui.GetForegroundWindow()
            if fg_hwnd:
                 win32gui.EnumChildWindows(fg_hwnd, enum_windows_proc, None)
            win32gui.EnumChildWindows(win32gui.GetDesktopWindow(), enum_windows_proc, None)
            win32gui.EnumWindows(enum_windows_proc, None)
        except Exception as e: print(f"Warning: Error during EnumWindows/EnumChildWindows call: {e}")

        if not buttons: return None
        nearest_button = min(buttons, key=lambda b: b['dist'])
        return nearest_button['pos']

    def reset_sticking(self):
        """Resets the button sticking state."""
        if self.sticking_to_button:
             pass
        self.sticking_to_button = False; self.stick_position = None
        self.last_raw_position = None

    def set_smoothing_params(self, window):
        """Updates smoothing window size."""
        window = int(max(1, window))
        if self.smoothing_window != window:
            self.position_history = deque(maxlen=window)
            self.last_smoothed_gaze_target = None
            self.last_raw_position = None
        self.smoothing_window = window
