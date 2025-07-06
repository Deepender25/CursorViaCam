from constants import (
    MIN_GAP_LEVEL, MAX_GAP_LEVEL, GAP_LEVEL_BASE_PX, GAP_LEVEL_STEP_PX,
    MIN_TRACK_AREA_LEVEL, MAX_TRACK_AREA_LEVEL, PAD_AT_LEVEL_1, PAD_AT_MAX_LEVEL, PAD_LEVEL_STEP_PX
)

def level_to_gap_px_static(level):
    clamped_level = max(MIN_GAP_LEVEL, min(MAX_GAP_LEVEL, int(round(level))))
    gap_px = GAP_LEVEL_BASE_PX + (clamped_level - MIN_GAP_LEVEL) * GAP_LEVEL_STEP_PX
    return gap_px

def gap_px_to_level_static(gap_px):
    gap_px = int(gap_px)
    clamped_gap_px = max(GAP_LEVEL_BASE_PX, min(GAP_LEVEL_BASE_PX + (MAX_GAP_LEVEL - MIN_GAP_LEVEL) * GAP_LEVEL_STEP_PX, gap_px))
    ideal_level = (clamped_gap_px - GAP_LEVEL_BASE_PX) / GAP_LEVEL_STEP_PX + MIN_GAP_LEVEL
    level = max(MIN_GAP_LEVEL, min(MAX_GAP_LEVEL, int(round(ideal_level))))
    return level

def level_to_padding_static(level):
    level_clamped = max(MIN_TRACK_AREA_LEVEL, min(MAX_TRACK_AREA_LEVEL, int(round(level))))
    padding = PAD_AT_LEVEL_1 - (level_clamped - MIN_TRACK_AREA_LEVEL) * PAD_LEVEL_STEP_PX
    return int(round(padding))

def padding_to_level_static(padding):
    padding = int(padding)
    clamped_padding = max(PAD_AT_MAX_LEVEL, min(PAD_AT_LEVEL_1, padding))
    # Snap padding to the nearest valid step based on levels
    snapped_padding = round((clamped_padding - PAD_AT_MAX_LEVEL) / PAD_LEVEL_STEP_PX) * PAD_LEVEL_STEP_PX + PAD_AT_MAX_LEVEL
    level_float = MIN_TRACK_AREA_LEVEL + (PAD_AT_LEVEL_1 - snapped_padding) / PAD_LEVEL_STEP_PX
    level_int = int(round(level_float))
    # Clamp level to valid range
    return max(MIN_TRACK_AREA_LEVEL, min(MAX_TRACK_AREA_LEVEL, level_int))

def hex_to_bgr(hex_color):
    """Converts a hex color string (e.g., '#FF0000') to a BGR tuple."""
    h = hex_color.lstrip('#')
    try:
        if len(h) == 3: h = h[0]*2 + h[1]*2 + h[2]*2 # Expand shorthand hex
        if len(h) != 6: raise ValueError("Invalid hex length")
        r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
        return (b, g, r) # BGR for OpenCV
    except Exception: return (128, 128, 128) # Default grey on error
