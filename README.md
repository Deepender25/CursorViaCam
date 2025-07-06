<h1 align="center"> CursorViaCam </h1>
<p align="center">
  <img alt="Build" src="https://img.shields.io/badge/Build-Passing-brightgreen?style=for-the-badge">
  <img alt="Issues" src="https://img.shields.io/badge/Issues-0%20Open-blue?style=for-the-badge">
  <img alt="Contributions" src="https://img.shields.io/badge/Contributions-Welcome-orange?style=for-the-badge">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge">
</p>
<!-- 
  **Note:** These are static placeholder badges. Replace them with your project's actual badges.
  You can generate your own at https://shields.io
-->

##  Table of Contents

- [⭐ Overview](#-overview)
- [✨ Key Features](#-key-features)
- [️ Tech Stack & Architecture](#️-tech-stack--architecture)
- [ Demo & Screenshots](#-demo--screenshots)
- [ Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
- [ Usage](#-usage)
- [ Contributing](#-contributing)
- [ License](#-license)

## ⭐ Overview

CursorViaCam revolutionizes human-computer interaction by enabling precise mouse cursor control through advanced camera-based head tracking.

> The increasing demand for hands-free computing, enhanced accessibility, and innovative interaction methods highlights a significant gap in traditional input devices. Repetitive mouse movements can lead to fatigue, and certain physical limitations can make standard cursor manipulation challenging or impossible. Presenters and power users often seek more dynamic and less restrictive ways to control their screens.

CursorViaCam provides an elegant solution by transforming your webcam into a sophisticated input device. Leveraging cutting-edge computer vision techniques, it tracks your head movements and translates them into seamless cursor navigation on your screen. Beyond basic control, the application integrates intelligent features like adaptive cursor speed, customizable smoothing, visual feedback, and unique "button sticking" capabilities, offering a truly intuitive and ergonomic computing experience.

### Inferred Architecture

CursorViaCam is designed as a robust desktop application, primarily built with Python and leveraging a modular architecture to separate concerns:

*   **User Interface (PyQt6):** The `cvc_app.py` serves as the core application entry point, managing the graphical user interface, user interactions, and orchestrating various functionalities.
*   **Computer Vision Core (OpenCV, MediaPipe):** Utilizes `opencv-python` for camera interfacing and `mediapipe` for advanced real-time head/face tracking, providing the raw input for cursor control.
*   **Cursor Control & Enhancements (PyAutoGUI, SmoothCursor):** `PyAutoGUI` directly interfaces with the operating system to move the cursor. The `smooth_cursor.py` module applies sophisticated algorithms for smoothing, adaptive speed adjustment, drift correction, and intelligent button sticking to enhance the user experience.
*   **Visual Feedback (CursorHighlighter):** The `cursor_highlighter.py` module creates a dynamic, transparent overlay to provide real-time visual cues around the cursor, improving user awareness and interaction.
*   **Settings & Profile Management:** The `settings_manager.py` module handles the persistence and retrieval of application settings and user-defined profiles, ensuring a highly customizable experience.
*   **Utilities:** A `utils.py` module encapsulates common helper functions and transformations used across the application.

## ✨ Key Features

*   **Camera-Based Head Tracking:** Utilizes your webcam and advanced computer vision (MediaPipe's Face Mesh) to accurately track head movements, translating them into precise on-screen cursor control.
*   **Advanced Cursor Smoothing & Adaptive Speed:** The `smooth_cursor.py` module dynamically adjusts cursor movement, applying intelligent smoothing and adaptive speed algorithms for a more fluid and less erratic user experience.
*   **Intelligent Button Sticking (Windows Only):** Features a unique "button sticking" capability, leveraging `pywin32` on Windows systems to automatically find and align the cursor with the nearest clickable UI element, simplifying interactions.
*   **Real-time Visual Cursor Highlighter:** A transparent overlay window (`cursor_highlighter.py`) draws a configurable, colored ring around your cursor, providing immediate visual feedback and improving cursor visibility.
*   **Customizable User Profiles:** Users can create, save, load, and delete multiple profiles via `cursorviacam_profiles.json`, allowing for personalized settings tailored to different users or use cases (e.g., presentation mode, accessibility mode).
*   **Intuitive Graphical User Interface (GUI):** Built with `PyQt6`, the application offers an easy-to-use interface for camera selection, sensitivity adjustments, feature toggles, and profile management.
*   **Interactive Onboarding Tutorial:** An integrated tutorial (`run_tutorial` in `cvc_app.py`) guides new users through the application's core functionalities, ensuring a smooth first-time experience.
*   **Real-time Performance Monitoring:** Provides live updates on the tracking performance, allowing users to optimize their setup for the best experience.

## ️ Tech Stack & Architecture

| Technology      | Purpose                                     | Why it was Chosen                                                            |
| :-------------- | :------------------------------------------ | :--------------------------------------------------------------------------- |
| `Python`        | Core Programming Language                   | Flexibility, extensive library ecosystem, and rapid prototyping capabilities. |
| `PyQt6`         | Graphical User Interface (GUI) Framework    | Robust, cross-platform capabilities for building native desktop applications. |
| `OpenCV`        | Computer Vision Library (Image Processing)  | Industry standard for real-time image and video processing, camera interfacing. |
| `MediaPipe`     | Machine Learning Framework (Face Mesh)      | Provides high-performance, pre-trained models for accurate head/face tracking. |
| `PyAutoGUI`     | Cross-Platform GUI Automation               | Simple and effective library for controlling the mouse and keyboard at the OS level. |
| `NumPy`         | Numerical Computing Library                 | Essential for efficient array operations and mathematical computations in computer vision workflows. |
| `pywin32`       | Windows API Extension (Windows Only)        | Enables direct interaction with the Windows operating system for advanced features like button sticking. |

##  Demo & Screenshots

![Placeholder Screenshot 1](https://placehold.co/800x450/1a1a2e/ffffff?text=App+Screenshot+1)
_The main application interface displaying real-time camera feed and tracking controls._

![Placeholder Screenshot 2](https://placehold.co/800x450/1a1a2e/ffffff?text=App+Screenshot+2)
_A closer look at the settings panel, showing various customization options for cursor behavior and highlighting._

[![Watch Demo Video 1](https://placehold.co/800x450/1a1a2e/c5a8ff?text=Watch+Demo+1)](https://www.youtube.com/watch?v=dQw4w9WgXcQ)
_See CursorViaCam's core head-tracking functionality in action._

[![Watch Demo Video 2](https://placehold.co/800x450/1a1a2e/c5a8ff?text=Watch+Demo+2)](https://www.youtube.com/watch?v=dQw4w9WgXcQ)
_A demonstration of the advanced cursor smoothing and adaptive speed features._

[![Watch Demo Video 3](https://placehold.co/800x450/1a1a2e/c5a8ff?text=Watch+Demo+3)](https://www.youtube.com/watch?v=dQw4w9WgXcQ)
_Exploring the visual cursor highlighter and its customizable appearance._

[![Watch Demo Video 4](https://placehold.co/800x450/1a1a2e/c5a8ff?text=Watch+Demo+4)](https://www.youtube.com/watch?v=dQw4w9WgXcQ)
_Showcasing the "Button Sticking" feature's precision (Windows-specific functionality)._

##  Getting Started

Follow these steps to get CursorViaCam up and running on your local machine.

### Prerequisites

Before you begin, ensure you have the following installed:

*   **Python 3.8+:** Download from [python.org](https://www.python.org/downloads/).
*   **A functional Webcam:** Required for head tracking.
*   **`pip`:** Python's package installer, usually comes with Python.

### Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/CursorViaCam.git
    cd CursorViaCam
    ```

2.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```
    *Note: If you are on Windows, `pywin32` will be automatically installed, enabling the "Button Sticking" feature.*

##  Usage

To launch CursorViaCam and start controlling your cursor:

1.  **Run the main application script:**

    ```bash
    python cvc_app.py
    ```

2.  The CursorViaCam GUI application will launch.
3.  Select your desired camera from the dropdown menu.
4.  Adjust settings such as padding, gap, and blink threshold as needed.
5.  Click the "Start Tracking" button to enable head-based cursor control.
6.  Explore the various options, including toggling the cursor highlighter and button sticking, and creating custom profiles.

##  Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also open an issue with the tag "enhancement".

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

##  License

Distributed under the MIT License. See `LICENSE` for more information.