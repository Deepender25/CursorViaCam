import json
import os
from constants import (
    CONFIG_FILE, IS_WINDOWS, DEFAULT_PADDING_VALUE, DEFAULT_GAP_LEVEL,
    DOUBLE_BLINK_INTERVAL, MIN_GAP_LEVEL, MAX_GAP_LEVEL
)
from utils import (
    level_to_padding_static, padding_to_level_static,
    level_to_gap_px_static, gap_px_to_level_static
)

def get_default_settings():
    """Returns a dictionary containing the default application settings."""
    defaults = {
        "rect_padding": DEFAULT_PADDING_VALUE,
        "blink_threshold_level": "Medium",
        "outer_gap_level": DEFAULT_GAP_LEVEL,
        "camera_index": 0,
        "enable_button_sticking": IS_WINDOWS,
        "double_blink_interval": DOUBLE_BLINK_INTERVAL,
        "long_blink_threshold": 0.27,
        "smooth_window_internal": 6,
        "enable_cursor_highlight": False,
    }
    if not IS_WINDOWS: defaults["enable_button_sticking"] = False
    defaults["rect_padding"] = level_to_padding_static(padding_to_level_static(defaults["rect_padding"]))
    return defaults

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

    loaded_data = None
    try:
        with open(CONFIG_FILE, "r") as file: loaded_data = json.load(file)

        if not (isinstance(loaded_data, dict) and "profiles" in loaded_data and
                "active_profile" in loaded_data and isinstance(loaded_data["profiles"], dict)):
            print("Config file structure invalid. Resetting."); return default_structure.copy()

        if "tutorial_completed" not in loaded_data: loaded_data["tutorial_completed"] = False
        if "Default" not in loaded_data["profiles"]:
            loaded_data["profiles"]["Default"] = default_profile_settings.copy(); print("Added missing 'Default' profile.")

        valid_profiles = {}
        default_keys = set(default_profile_settings.keys())

        for name, profile_settings in loaded_data["profiles"].items():
            if not isinstance(profile_settings, dict):
                print(f"Warning: Profile '{name}' data invalid (not a dict). Skipping."); continue

            valid_settings = default_profile_settings.copy()
            migrated_settings = {}
            keys_to_remove = set()

            for key, value in profile_settings.items():
                if key in ["cursor_sensitivity_level", "cursor_speed_level", "cursor_sensitivity", "min_speed", "max_speed", "acceleration", "min_speed_factor", "max_speed_factor", "double_blink_threshold"]:
                    keys_to_remove.add(key)
                elif key not in default_keys:
                    keys_to_remove.add(key)
                else:
                     migrated_settings[key] = value

            if keys_to_remove: print(f"Migrating/removing old keys for profile '{name}': {keys_to_remove}")

            valid_settings.update(migrated_settings)

            try: valid_settings["outer_gap_level"] = max(MIN_GAP_LEVEL, min(MAX_GAP_LEVEL, int(valid_settings.get("outer_gap_level", DEFAULT_GAP_LEVEL))))
            except (ValueError, TypeError): valid_settings["outer_gap_level"] = DEFAULT_GAP_LEVEL

            try:
                level = padding_to_level_static(int(valid_settings.get("rect_padding", DEFAULT_PADDING_VALUE)))
                valid_settings["rect_padding"] = level_to_padding_static(level)
            except (ValueError, TypeError): valid_settings["rect_padding"] = DEFAULT_PADDING_VALUE

            try: valid_settings["camera_index"] = int(valid_settings.get("camera_index", 0))
            except (ValueError, TypeError): valid_settings["camera_index"] = 0

            try: valid_settings["long_blink_threshold"] = max(0.1, float(valid_settings.get("long_blink_threshold", default_profile_settings["long_blink_threshold"])))
            except (ValueError, TypeError): valid_settings["long_blink_threshold"] = default_profile_settings["long_blink_threshold"]

            try: valid_settings["double_blink_interval"] = max(0.1, float(valid_settings.get("double_blink_interval", default_profile_settings["double_blink_interval"])))
            except (ValueError, TypeError): valid_settings["double_blink_interval"] = default_profile_settings["double_blink_interval"]

            try: valid_settings["smooth_window_internal"] = max(1, int(valid_settings.get("smooth_window_internal", default_profile_settings["smooth_window_internal"])))
            except (ValueError, TypeError): valid_settings["smooth_window_internal"] = default_profile_settings["smooth_window_internal"]

            if valid_settings.get("blink_threshold_level") not in ["Low", "Medium", "High"]: valid_settings["blink_threshold_level"] = "Medium"

            if not IS_WINDOWS: valid_settings["enable_button_sticking"] = False
            else:
                 try: valid_settings["enable_button_sticking"] = bool(valid_settings.get("enable_button_sticking", IS_WINDOWS))
                 except (ValueError, TypeError): valid_settings["enable_button_sticking"] = IS_WINDOWS

            try: valid_settings["enable_cursor_highlight"] = bool(valid_settings.get("enable_cursor_highlight", default_profile_settings["enable_cursor_highlight"]))
            except (ValueError, TypeError): valid_settings["enable_cursor_highlight"] = default_profile_settings["enable_cursor_highlight"]

            valid_profiles[name] = valid_settings

        loaded_data["profiles"] = valid_profiles

        if loaded_data["active_profile"] not in loaded_data["profiles"]:
            print(f"Active profile '{loaded_data['active_profile']}' not found. Setting to 'Default'.")
            loaded_data["active_profile"] = "Default"

        save_profiles(loaded_data)
        return loaded_data

    except (json.JSONDecodeError, IOError, TypeError, ValueError, KeyError) as e:
        print(f"Error loading or validating profiles: {e}. Using default.")
        save_data = default_structure.copy()
        if isinstance(loaded_data, dict) and "tutorial_completed" in loaded_data:
             save_data["tutorial_completed"] = loaded_data["tutorial_completed"]
        save_profiles(save_data)
        return default_structure.copy()

def save_profiles(profiles_data):
    """Saves the complete profiles data structure to the JSON file."""
    try:
        default_keys = get_default_settings().keys()
        clean_profiles_dict = {}
        for profile_name, settings_dict in profiles_data.get("profiles", {}).items():
             if isinstance(settings_dict, dict):
                 clean_settings = {k: v for k, v in settings_dict.items() if k in default_keys}
                 for def_key in default_keys:
                     if def_key not in clean_settings:
                         clean_settings[def_key] = get_default_settings()[def_key]
                 clean_profiles_dict[profile_name] = clean_settings
             else: print(f"Warning: Profile '{profile_name}' has invalid data type during save. Skipping.")

        data_to_save = {
            "active_profile": profiles_data.get("active_profile", "Default"),
            "profiles": clean_profiles_dict,
            "tutorial_completed": profiles_data.get("tutorial_completed", False)
        }
        if data_to_save["active_profile"] not in data_to_save["profiles"]:
             data_to_save["active_profile"] = "Default"
             if "Default" not in data_to_save["profiles"]:
                  data_to_save["profiles"]["Default"] = get_default_settings()

        with open(CONFIG_FILE, "w") as file:
            json.dump(data_to_save, file, indent=4)
    except (IOError, TypeError) as e:
        print(f"Error saving profiles: {e}")
