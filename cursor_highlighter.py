from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtCore import Qt
import pyautogui

from constants import COLOR_IDLE

class CursorHighlighterWindow(QWidget):
    """A transparent overlay window to draw a ring around the cursor."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |       # No border or title bar
            Qt.WindowType.WindowStaysOnTopHint |      # Always on top
            Qt.WindowType.Tool |                      # Doesn't appear in taskbar/alt-tab
            Qt.WindowType.WindowTransparentForInput # Allows clicks to pass through (Qt 5.1+)
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
