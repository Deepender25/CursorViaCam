import platform

# --- Platform Specific Imports (for Button Sticking) ---
IS_WINDOWS = platform.system() == "Windows"

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
COLOR_IDLE = "#777777"
COLOR_RUN = "#008000"
COLOR_WARN = "#FFA500"
COLOR_ERROR = "#FF0000"
COLOR_START = "#FFD700"
COLOR_INFO_BLUE = "#4682B4"
COLOR_TUTORIAL = "#DA70D6" # Purple for Tutorial

BLINK_THRESHOLD_MAP = {"Low": 0.0045, "Medium": 0.0055, "High": 0.0065}
