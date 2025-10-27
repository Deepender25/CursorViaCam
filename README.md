<h1 align="center"> Cursor Via Cam </h1>
<p align="center"> Control Your Digital World Hands-Free with Vision-Based Cursor Tracking. </p>

<p align="center">
  <img alt="Build" src="https://img.shields.io/badge/Build-Passing-brightgreen?style=for-the-badge">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.x+-blue?style=for-the-badge&logo=python">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge">
  <img alt="Contributions" src="https://img.shields.io/badge/Contributions-Welcome-orange?style=for-the-badge">
</p>
<!-- 
  **Note:** These are static placeholder badges. Replace them with your project's actual badges.
  You can generate your own at https://shields.io
-->

***

## 📚 Table of Contents

*   [⭐ Overview](#-overview)
*   [✨ Key Features](#-key-features)
*   [🛠️ Tech Stack & Architecture](#-tech-stack--architecture)
*   [📁 Project Structure](#-project-structure)
*   [📸 Demo & Screenshots](#-demo--screenshots)
*   [🚀 Getting Started](#-getting-started)
*   [🔧 Usage](#-usage)
*   [🤝 Contributing](#-contributing)
*   [📝 License](#-license)

***

## ⭐ Overview

**Cursor Via Cam** is a powerful, vision-based application designed to revolutionize how users interact with their computers, providing precise and ergonomic hands-free cursor control through camera tracking technology.

### The Problem

> Traditional computer interaction often requires constant use of a mouse, leading to physical strain, repetitive stress injuries (RSI), and significant limitations for users with mobility challenges. Furthermore, systems relying on raw camera input are typically plagued by jitter, drift, and inconsistency, making fine control—such as clicking small buttons or performing detailed work—frustratingly difficult. Existing accessibility tools often lack the customizability needed for real-world scenarios.

### The Solution

Cursor Via Cam addresses these challenges head-on by leveraging cutting-edge computer vision (OpenCV and MediaPipe) and advanced smoothing algorithms. It transforms subtle movements (like head or hand motion captured by a standard webcam) into smooth, reliable, and highly accurate cursor positioning. The application offers a robust, configurable solution that not only facilitates hands-free use but significantly improves the quality of life and productivity for all users seeking ergonomic alternatives.

By integrating features like adaptive speed, automated drift correction, and specialized profile management, Cursor Via Cam moves beyond simple cursor movement to provide a fully controllable and professional accessibility platform.

### Architecture Overview

Built entirely in Python, Cursor Via Cam utilizes `PyQt6` for a robust, cross-platform graphical user interface (GUI). The core functionality relies on `opencv-python` and `mediapipe` to handle real-time tracking, translating tracked landmarks into screen coordinates. All position updates are processed through the `SmoothCursor` class, which applies sophisticated smoothing, adaptive speed adjustment, and correction algorithms before passing the final coordinates to `PyAutoGUI` for system-level mouse control.

***

## ✨ Key Features

The primary goal of Cursor Via Cam is to provide a reliable and highly usable hands-free interface. Every feature is engineered to optimize precision and reduce user fatigue.

#### ✨ **Advanced Real-Time Cursor Smoothing**
The core engine employs proprietary smoothing techniques to eliminate the jitter and noise inherent in webcam feeds. This ensures that even small, rapid, or shaky movements translate into predictable and fluid cursor trajectories.
*   **User Benefit:** Experience natural, high-precision control essential for detailed tasks like graphic design, document editing, or navigating complex interfaces, significantly reducing frustration caused by jitter.

#### 🎯 **Target-Aware "Button Sticking" (Windows Only)**
This crucial feature enhances user accuracy on Windows operating systems. When the cursor approaches a known clickable UI element (like a button or menu item), the system intelligently applies a temporary "sticking" force, gently guiding the cursor to the exact center of the target.
*   **User Benefit:** Drastically reduces the required fine motor control for clicking. This feature is instrumental for users who struggle with the precision needed to land on small targets, making Windows application usage seamless. *Requires the optional `pywin32` dependency.*

#### 🚀 **Adaptive Speed and Acceleration**
The system intelligently analyzes the user's current movement velocity to dynamically adjust the cursor acceleration. Small, deliberate movements allow for fine control (slow speed), while larger, faster movements result in rapid screen traversal (high speed).
*   **User Benefit:** Navigate quickly across a large multi-monitor setup and instantly switch to high-precision mode for micro-adjustments without having to manually change settings.

#### ⚙️ **Comprehensive Profile Management**
All settings—including smoothing parameters, padding levels, blink thresholds, and highlighting options—can be saved, loaded, and managed as distinct profiles via a dedicated JSON configuration file (`cursorviacam_profiles.json`).
*   **User Benefit:** Quickly switch between "Gaming Mode" (high speed, low smoothing), "Work Mode" (medium speed, high sticking), or profiles optimized for different users or environmental lighting conditions.

#### 👁️ **Visual Cursor Feedback & Highlighting**
An optional, customizable overlay window (`CursorHighlighterWindow`) is employed to draw a visible, colored ring around the current cursor location. This transparent overlay moves seamlessly with the system cursor.
*   **User Benefit:** Provides immediate visual confirmation of the cursor's location, especially useful in complex interfaces, multi-screen environments, or during presentations. Users can customize the color for optimal visibility.

#### 🔄 **Automated Drift and Correction**
The system incorporates internal mechanisms for drift correction, ensuring that if tracking remains static, the cursor does not unintentionally creep across the screen over time due to slight camera shifts or minor tracking errors.
*   **User Benefit:** Reliable, persistent cursor positioning without the need for constant manual recalibration.

#### 💻 **Intuitive Settings Interface (PyQt6)**
The application provides a centralized graphical interface (`cvc_app.py`) for managing all runtime parameters, including selecting the active camera, adjusting tracking boundaries (padding), configuring blink-to-click thresholds, and toggling features like button sticking and highlighting.
*   **User Benefit:** Easy access to all controls without needing to touch configuration files, ensuring a smooth setup and continuous adjustment process.

***

## 🛠️ Tech Stack & Architecture

Cursor Via Cam is engineered using a robust set of open-source libraries focused on performance, vision processing, and user interface reliability.

| Technology | Purpose | Why it was Chosen |
| :--- | :--- | :--- |
| **Python** | Primary development language for rapid iteration and rich ecosystem. | High readability and extensive support for ML/CV libraries, allowing for complex algorithmic implementation. |
| **PyQt6** | Cross-platform GUI framework for the application interface. | Provides a professional, native-looking, and high-performance user experience for configuring settings. |
| **OpenCV-Python** | Core library for video stream handling, image processing, and camera initialization. | Industry standard for computer vision tasks, essential for reliable frame acquisition. |
| **Mediapipe** | Advanced library for robust real-time face and hand tracking models. | Essential for efficiently translating user movements (e.g., facial landmarks) into screen coordinates. |
| **PyAutoGUI** | Programmatic control and manipulation of the system mouse cursor. | Necessary for accurately translating tracked points to screen positions and simulating clicks/inputs. |
| **NumPy** | Fundamental library for high-performance numerical operations. | Optimized array manipulation required for efficiency within the OpenCV and Mediapipe pipelines. |
| **Pywin32** | Windows-specific interface for advanced UI element inspection (Optional). | Enables the "Button Sticking" feature by accessing and finding clickable elements within the Windows operating environment. |

***

## 📁 Project Structure

The project is logically segmented into core processing units, settings management, and the main application interface, ensuring modularity and maintainability.

```
📂 Deepender25-CursorViaCam-5bef312/
├── 📄 cvc_app.py                  # Main application entry point and PyQt6 GUI handler.
├── 📄 smooth_cursor.py            # Core logic for movement smoothing, adaptive speed, drift correction, and button sticking (SmoothCursor class).
├── 📄 cursor_highlighter.py       # Handles the transparent overlay window and drawing the visual cursor ring (CursorHighlighterWindow class).
├── 📄 settings_manager.py         # Utility functions for loading default settings and managing persistent profile data (load_profiles, save_profiles).
├── 📄 utils.py                    # General utility functions, including color conversion (hex_to_bgr) and dimension calculations.
├── 📄 constants.py                # Contains fixed values and application constants.
├── 📄 requirements.txt            # Lists all mandatory and optional (Win32) Python dependencies.
├── 📄 cursorviacam_profiles.json  # JSON file used for storing user-defined tracking profiles and settings.
├── 📄 CursorViaCam(Whightbg).ico  # Application icon file.
├── 📄 README.md                   # This project documentation file.
└── 📄 .gitignore                  # Files and directories ignored by Git.
```

***

## 📸 Demo & Screenshots

These sections are placeholders illustrating the application's functionality. The user interface allows for detailed configuration of tracking parameters, selection of input devices, and visual feedback elements.

### 🖼️ Screenshots

![Screenshot 2025-07-09 145149](https://github.com/user-attachments/assets/face7226-8dda-4240-a832-cf78fa4ed272)
<em><p align="center">The main application interface displaying real-time camera feed and tracking controls.</p></em>

![Screenshot 2025-07-09 145149](https://github.com/user-attachments/assets/933bea88-9c88-4968-a372-6004b4c6276e)
<em><p align="center">A closer look at the settings panel, showing various customization options for cursor behavior and highlighting.</p></em>

### 🎬 Video Demos


https://github.com/user-attachments/assets/bb4ce28e-ddbb-4923-886c-fa93e8eb3914

<em><p align="center">See CursorViaCam's core head-tracking functionality in action.</p></em>


https://github.com/user-attachments/assets/049119de-51fb-4f54-863d-8db9f2a09e9f

<em><p align="center">A demonstration of the advanced cursor smoothing and Left-Click, Double-Click, Scrolling in play.</p></em>


https://github.com/user-attachments/assets/fc9d2e22-1c25-4436-9152-ab554b340ecb

<em><p align="center">Exploring the visual cursor highlighter and its customizable appearance.</p></em>


https://github.com/user-attachments/assets/cd93c9ff-9fbe-40d4-bd3f-29e7b5ae4940

<em><p align="center">Showcasing the Intractive Tutorial Feature.</p></em>

***

## 🚀 Getting Started

To run Cursor Via Cam, you will need a stable installation of Python 3.x and a webcam connected to your system.

### Prerequisites

*   **Python:** Version 3.8 or higher.
*   **Package Manager:** `pip` (comes bundled with Python).

### Installation

Follow these steps to set up the project environment and install all necessary dependencies.

#### 1. Clone the Repository

```bash
# Clone the main repository (replace the URL with the actual repo link)
git clone https://github.com/Deepender25/CursorViaCam-5bef312.git
cd Deepender25-CursorViaCam-5bef312
```

#### 2. Create and Activate a Virtual Environment

It is highly recommended to use a virtual environment to manage dependencies and avoid conflicts with other Python projects.

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment (Linux/macOS)
source venv/bin/activate

# Activate the virtual environment (Windows Command Prompt)
.\venv\Scripts\activate.bat
```

#### 3. Install Dependencies

Install all required packages listed in `requirements.txt`. Note that `pywin32` is a conditional dependency and will only be installed automatically if you are running this command on a Windows machine, enabling the "Button Sticking" feature.

```bash
pip install -r requirements.txt
```

***

## 🔧 Usage

Once the dependencies are installed, you can launch the application and begin configuring your hands-free cursor control.

### Starting the Application

The main application logic and GUI are contained within `cvc_app.py`. Execute this file directly from your activated virtual environment:

```bash
# Ensure your virtual environment is active
python cvc_app.py
```

### Initial Configuration Steps

1.  **Camera Selection:** Upon launch, use the camera selector dropdown in the application interface to choose your input device.
2.  **Tracking Initialization:** Click the "Start Tracking" button (or equivalent) in the UI to initialize the Mediapipe models and begin processing the video feed.
3.  **Configure Parameters:**
    *   **Smoothing:** Adjust the smoothing window size in the settings panel to balance responsiveness (low smoothing) and stability (high smoothing).
    *   **Padding/Tracking Area:** Define the boundaries of the tracking area to map movements accurately to your screen size.
    *   **Blink Threshold:** Adjust the threshold for blink detection, which is typically used to trigger a "click" action.
4.  **Enable Advanced Features:** Toggle the **Cursor Highlighting** (to show the transparent ring) or **Button Sticking** (if on Windows) features from the relevant checkboxes in the settings UI.
5.  **Save Profile:** Once configured, use the Profile Manager to save your current settings (e.g., "Daylight Profile" or "Precision Work Profile") to `cursorviacam_profiles.json` for quick recall later.

The application will run in the background, updating the system cursor position in real-time based on the tracked movements, applying all configured smoothing and correction algorithms.

***

## 🤝 Contributing

We welcome contributions to improve Cursor Via Cam! Your input helps make this project better for everyone, especially those relying on accessibility tools.

### How to Contribute

1. **Fork the repository** - Click the 'Fork' button at the top right of this page
2. **Create a feature branch** 
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Make your changes** - Improve code, documentation, or features, focusing on enhancements to tracking accuracy, performance, or GUI usability.
4. **Test thoroughly** - Ensure all functionality works as expected. While formal test scripts are not provided in the current structure, manually verifying changes across different configurations (profiles, camera types) is essential.
   ```bash
   # Execute the application to test changes
   python cvc_app.py
   ```
5. **Commit your changes** - Write clear, descriptive commit messages
   ```bash
   git commit -m 'Feat: Implement enhanced adaptive speed algorithm in smooth_cursor.py'
   ```
6. **Push to your branch**
   ```bash
   git push origin feature/amazing-feature
   ```
7. **Open a Pull Request** - Submit your changes for review against the `main` branch.

### Development Guidelines

- ✅ Follow the existing Python code style and conventions, especially for class and function naming.
- 📝 Add clear docstrings and inline comments for complex logic, particularly within `smooth_cursor.py` and tracking functions in `cvc_app.py`.
- 📚 Update documentation (including this README) if you introduce new configuration options or change application behavior.
- 🔄 Ensure backward compatibility when modifying core tracking or smoothing logic.
- 🎯 Keep commits focused and atomic.

### Ideas for Contributions

We're looking for help with:

- 🐛 **Bug Fixes:** Report and fix bugs related to camera initialization or tracking stability.
- ✨ **New Features:** Implement requested tracking methods or add platform-specific UI interaction enhancements.
- 📖 **Documentation:** Improve README, add detailed tutorials for feature configuration.
- 🎨 **UI/UX:** Enhance the PyQt6 interface for better accessibility and user experience.
- ⚡ **Performance:** Optimize video processing loops for lower CPU usage and faster frame rates.
- 🧪 **Testing:** Introduce unit tests for core utilities and algorithms (e.g., in `utils.py` and `smooth_cursor.py`).
- ♿ **Accessibility:** Further enhancements to control and calibration for users with diverse needs.

### Code Review Process

- All submissions require review by maintainers before merging.
- Maintainers will provide constructive feedback on functionality, style, and performance.
- Changes may be requested before approval.
- Once approved, your PR will be merged and you'll be credited for your contribution.

### Questions?

Feel free to open an issue for any questions or concerns regarding development, feature requests, or bugs. We're here to help!

***

## 📝 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for complete details.

### What this means:

- ✅ **Commercial use:** You are permitted to use this project commercially.
- ✅ **Modification:** You can modify the source code to suit your needs.
- ✅ **Distribution:** You can distribute this software (modified or unmodified).
- ✅ **Private use:** You can use this project privately for any purpose.
- ⚠️ **Liability:** The software is provided "as is," without warranty of any kind, express or implied.
- ⚠️ **Trademark:** This license does not grant rights to use the names, trademarks, or service marks of the contributors.

---

<p align="center">Made with ❤️ by the Cursor Via Cam Team</p>
<p align="center">
  <a href="#-overview">⬆️ Back to Top</a>
</p>
