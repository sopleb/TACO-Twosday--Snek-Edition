#!/usr/bin/env python3
"""T.A.C.O. Twosday: Python Edition
Python port using PyQt6 + PyOpenGL.

Entry point for the application.
"""
import sys
import os
import platform

# Ensure the parent directory is in the path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows-only: preload Qt6 DLLs for frozen (PyInstaller) builds.
if getattr(sys, 'frozen', False) and platform.system() == 'Windows':
    import ctypes
    _exe_dir = os.path.dirname(sys.executable)
    _qt6_bin = os.path.join(sys._MEIPASS, 'PyQt6', 'Qt6', 'bin')
    _pyqt6_dir = os.path.join(sys._MEIPASS, 'PyQt6')

    try:
        ctypes.windll.kernel32.SetDllDirectoryW(_exe_dir)
    except Exception:
        pass

    for _dll_dir in [_qt6_bin, _pyqt6_dir, _exe_dir]:
        if os.path.isdir(_dll_dir):
            os.environ['PATH'] = _dll_dir + os.pathsep + os.environ.get('PATH', '')
            try:
                os.add_dll_directory(_dll_dir)
            except (OSError, AttributeError):
                pass

    for _dll_name in ['Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll',
                      'Qt6OpenGL.dll', 'Qt6OpenGLWidgets.dll', 'Qt6Network.dll',
                      'Qt6Svg.dll', 'Qt6Pdf.dll', 'Qt6Multimedia.dll']:
        for _dll_dir in [_exe_dir, _pyqt6_dir, _qt6_bin]:
            _dll_path = os.path.join(_dll_dir, _dll_name)
            if os.path.exists(_dll_path):
                try:
                    ctypes.WinDLL(_dll_path)
                except OSError:
                    pass
                break

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QSurfaceFormat

from taco.ui.main_window import MainWindow


def main():
    # On Windows, set AppUserModelID so the taskbar shows our icon
    # instead of the default Python icon.
    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "taco.twosday.python.edition"
            )
        except Exception:
            pass

    # On Linux (including Steam Deck), request an OpenGL 3.3 Core context
    # *before* creating QApplication so Qt picks a valid GLX/EGL surface.
    if platform.system() == "Linux":
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setStencilBufferSize(8)
        QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setApplicationName("T.A.C.O. Twosday: Python Edition")
    app.setOrganizationName("TACO")

    # Set app icon if available
    # When frozen by PyInstaller, resources are in sys._MEIPASS
    if getattr(sys, 'frozen', False):
        base_path = os.path.join(sys._MEIPASS, "taco")
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_path, "resources", "textures", "AngryTaco.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
