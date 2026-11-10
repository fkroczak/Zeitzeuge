"""Titelleiste unter Windows 10/11 passend zum Design: dunkel im dunklen Design.

Windows zeichnet die Titelleiste selbst (hell), Qt kann sie nicht färben. Mit
DwmSetWindowAttribute(DWMWA_USE_IMMERSIVE_DARK_MODE) wird sie dunkel. Unter anderen
Systemen und bei älterem Windows passiert nichts.
"""
import ctypes
import sys

# DWMWA_USE_IMMERSIVE_DARK_MODE: 20 ab Windows 10 20H1, 19 bei älteren Windows-10-Versionen
_ATTRIBUTES = (20, 19)


def apply(win_id, dark):
    """Titelleiste des Fensters (native Kennung, z. B. widget.winId()) hell oder dunkel."""
    if sys.platform != "win32" or not win_id:
        return False
    value = ctypes.c_int(1 if dark else 0)
    try:
        set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
    except (AttributeError, OSError):
        return False
    for attribute in _ATTRIBUTES:
        if set_attribute(ctypes.c_void_p(int(win_id)), attribute, ctypes.byref(value),
                         ctypes.sizeof(value)) == 0:
            return True
    return False
