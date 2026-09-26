"""
Window Backdrop
===============

The popup window's Windows 11 frame: rounded corners and a shadow without a
border line, and for the glass material (beta) the native layer that shows
the desktop behind the page.

Every call here is a documented DWM attribute on the popup's own window
(``DwmSetWindowAttribute``, ``DwmEnableBlurBehindWindow``), a property of its
WinForms host, or the glass layer compiled from ``glass_layer.cs``.  Nothing
is written to disk or the registry, and nothing outlives the window.  The one
registry read is Windows' own "Transparency effects" switch.

Glass is three layers, and none of them reads the screen.  The glass layer
(``glass_layer.cs``) sits under the page and has the Windows compositor draw
what lies behind the window - blurred, more saturated and capped in
brightness - on the GPU, frame by frame.  The window lets it through: its
system backdrop is off and a blur-behind with an empty region makes the
WinForms form's black paint transparent.  WebView2 draws the page over both
with a transparent default background, so the page's tint (``glass.css``)
decides how much shows through.  pywebview's ``transparent=True`` is
deliberately not used: it shows the form as soon as navigation starts, before
the popup has been sized and positioned.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import winreg
from pathlib import Path
from typing import Any

__all__ = ['GLASS_SUPPORTED', 'frame_window', 'is_dark_color', 'release_glass', 'release_window_icon', 'set_glass', 'set_glass_scale']

# The system backdrop attribute that has to be switched off arrived with
# Windows 11 22H2, the rounded-corner preference with the first Windows 11
# release.  Older systems keep the square, opaque window.  Glass also needs
# the glass layer, which build.py compiles next to this module.
_WINDOWS_BUILD = sys.getwindowsversion().build
_GLASS_LAYER = Path(__file__).with_name('glass_layer.dll')
GLASS_SUPPORTED = _WINDOWS_BUILD >= 22621 and _GLASS_LAYER.is_file()
_ROUNDED_CORNERS = _WINDOWS_BUILD >= 22000

# What the glass layer draws, owned here and handed to glass_layer.cs: a light
# blur (CSS pixels, scaled to the monitor), saturation for vivid color, and
# the brightness every pixel is capped at.  The cap is what holds text
# contrast over a white window without looking at the screen; glass.css sets
# its tint against it, so the two change together.
_GLASS_BLUR = 3.0
_GLASS_SATURATION = 1.5
_GLASS_BRIGHTNESS_CAP = 0.35

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWA_BORDER_COLOR = 34
_DWMWA_SYSTEMBACKDROP_TYPE = 38
_DWMWCP_ROUND = 2
_DWMWA_COLOR_NONE = 0xFFFFFFFE
_DWMSBT_NONE = 1
_DWM_BB_ENABLE = 0x1
_DWM_BB_BLURREGION = 0x2
_BASELINE_DPI = 96
_S_OK = 0

_PERSONALIZE_KEY = r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'

_CreateRectRgn = ctypes.WINFUNCTYPE(ctypes.wintypes.HRGN, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)(
    ('CreateRectRgn', ctypes.windll.gdi32),
)
_DeleteObject = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HGDIOBJ)(('DeleteObject', ctypes.windll.gdi32))


class _DWM_BLURBEHIND(ctypes.Structure):
    _fields_ = [
        ('dwFlags', ctypes.wintypes.DWORD), ('fEnable', ctypes.wintypes.BOOL),
        ('hRgnBlur', ctypes.wintypes.HRGN), ('fTransitionOnMaximized', ctypes.wintypes.BOOL),
    ]


def frame_window(hwnd: int, background: str) -> bool:
    """Give the popup Windows 11's rounded corners and shadow, without a border.

    DWM would otherwise draw a 1px grey line around a rounded window - over the
    window's outermost pixels, so it also covers the signature strip along the
    top of the detail view.  The dark-mode attribute matches the frame to the
    theme.

    Parameters
    ----------
    hwnd : int
        The popup's top-level window handle.
    background : str
        The theme's ``bg`` color, which picks the dark or the light frame.

    Returns
    -------
    bool
        True when DWM rounds the window, so the page leaves its own edge
        stroke out: the shadow separates the window from what is behind it,
        and a stroke would be cut at the corners.
    """
    if not _ROUNDED_CORNERS:
        return False

    _set_attribute(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, int(is_dark_color(background)))
    _set_attribute(hwnd, _DWMWA_BORDER_COLOR, _DWMWA_COLOR_NONE)

    return _set_attribute(hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, _DWMWCP_ROUND) == _S_OK


def set_glass(form: Any, enabled: bool, background: str) -> bool:
    """Turn the glass layer behind the page on or off.

    Turning it on attaches the layer first, while the form still paints
    opaque, and makes the window and the page transparent only once it is in
    place; turning it off paints the window opaque before the layer goes.
    Either way the desktop never shows behind the page without the layer's
    brightness cap.

    Parameters
    ----------
    form : Any
        pywebview's WinForms window (``window.native``).
    enabled : bool
        True shows the desktop behind the page, False restores the opaque window.
    background : str
        The theme's ``bg`` color: what the window paints once glass is off.

    Returns
    -------
    bool
        True when the window now shows the glass.  False when glass was
        turned off, is unavailable, the user switched Windows' transparency
        effects off, or the layer could not be built - the page must then
        draw an opaque surface, because a transparent page over a window
        without the layer shows the black form behind it.
    """
    hwnd = form.Handle.ToInt32()

    if not enabled:
        _paint_behind_page(form, background)
        _enable_see_through(hwnd, False)
        _on_ui_thread(form, lambda: _glass_layer().Detach())
        return False

    if not GLASS_SUPPORTED or not _transparency_enabled():
        return False

    failure = _on_ui_thread(form, lambda: _glass_layer().Attach(
        _handle(hwnd), _blur_for(hwnd), _GLASS_SATURATION, _GLASS_BRIGHTNESS_CAP,
    ))
    if failure:
        return False

    if _set_attribute(hwnd, _DWMWA_SYSTEMBACKDROP_TYPE, _DWMSBT_NONE) != _S_OK or not _enable_see_through(hwnd, True):
        _on_ui_thread(form, lambda: _glass_layer().Detach())
        return False

    _paint_behind_page(form, None)

    return True


def set_glass_scale(form: Any) -> None:
    """Match the glass layer's blur to the monitor the window is on now.

    The blur is set in physical pixels, so a window dragged onto a monitor
    with another scale would otherwise blur more or less than before.
    """
    hwnd = form.Handle.ToInt32()
    _on_ui_thread(form, lambda: _glass_layer().SetBlur(_blur_for(hwnd)))


def release_glass(form: Any) -> None:
    """Take the glass layer off a popup that is about to close.

    The compositor holds GPU resources for the layer until it is detached.
    Nothing is repainted: the window is going away, and painting it opaque
    first would flash.
    """
    _on_ui_thread(form, lambda: _glass_layer().Detach())


def release_window_icon(form: Any) -> None:
    """Free the icon pywebview gives every window it creates.

    pywebview clones the executable's icon for each window and never disposes
    of it, so every popup opened and closed kept one icon - a USER object and
    its GDI bitmaps - for the rest of the process.  The popup is frameless and
    hidden from the taskbar, so it has no use for an icon.  WinForms' default
    icon, which a form reports when it has none of its own, is shared by every
    form and is left alone.
    """
    def release() -> None:
        own = form.Icon
        form.Icon = None
        if own is not None and not own.Equals(form.Icon):
            own.Dispose()

    _on_ui_thread(form, release)


def is_dark_color(color: str) -> bool:
    """Tell whether a ``#rrggbb`` or ``#rgb`` color reads as dark.

    Anything else counts as dark, the default theme, so an unexpected value
    keeps the frame the app ships with.
    """
    digits = color.lstrip('#')
    if len(digits) == 3:
        digits = ''.join(digit * 2 for digit in digits)
    if len(digits) != 6:
        return True
    try:
        red, green, blue = (int(digits[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return True

    # Rec. 601 luma, in thousandths so mid-grey falls exactly on the boundary
    # rather than on a floating-point rounding of it.
    return 299 * red + 587 * green + 114 * blue < 128_000


def _set_attribute(hwnd: int, attribute: int, value: int) -> int:
    """Set one 32-bit DWM window attribute and return its HRESULT."""
    data = ctypes.wintypes.DWORD(value)
    return ctypes.windll.dwmapi.DwmSetWindowAttribute(
        ctypes.wintypes.HWND(hwnd), attribute, ctypes.byref(data), ctypes.sizeof(data),
    )


def _enable_see_through(hwnd: int, enabled: bool) -> bool:
    """Let the window's black paint show what is under it, or stop it.

    A blur-behind with an empty region blurs nothing; what it does is make
    DWM honor the window's per-pixel alpha, so the form's black - alpha 0 -
    shows the glass layer underneath.
    """
    region = _CreateRectRgn(0, 0, -1, -1) if enabled else None
    blur = _DWM_BLURBEHIND(_DWM_BB_ENABLE | (_DWM_BB_BLURREGION if enabled else 0), enabled, region, False)
    try:
        return ctypes.windll.dwmapi.DwmEnableBlurBehindWindow(ctypes.wintypes.HWND(hwnd), ctypes.byref(blur)) == _S_OK
    finally:
        if region:
            _DeleteObject(region)


def _blur_for(hwnd: int) -> float:
    dpi = ctypes.windll.user32.GetDpiForWindow(hwnd) or _BASELINE_DPI
    return _GLASS_BLUR * dpi / _BASELINE_DPI


def _transparency_enabled() -> bool:
    """Read Windows' "Transparency effects" switch; on when it cannot be read.

    Someone who switched it off has asked for opaque windows, so glass
    falls back to matte for them the way Windows' own surfaces do.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, 'EnableTransparency')
    except OSError:
        return True

    return bool(value)


def _glass_layer() -> Any:
    """The compiled glass layer, loaded into pywebview's .NET runtime on first use."""
    import clr  # type: ignore[import-not-found]  # pythonnet, loaded by pywebview's WinForms backend

    clr.AddReference(str(_GLASS_LAYER))
    from AIAgentsUsageMonitor import GlassLayer  # type: ignore[import-not-found]  # .NET class in glass_layer.dll

    return GlassLayer


def _handle(hwnd: int) -> Any:
    from System import IntPtr  # type: ignore[import-not-found]  # .NET namespace provided by pythonnet

    return IntPtr(hwnd)


def _on_ui_thread(form: Any, call: Any) -> Any:
    """Run *call* on the form's WinForms UI thread, which owns the glass layer, and return its result."""
    from System import Action  # type: ignore[import-not-found]  # .NET namespace provided by pythonnet

    result = []
    form.Invoke(Action(lambda: result.append(call())))

    return result[0] if result else None


def _paint_behind_page(form: Any, background: str | None) -> None:
    """Set what WinForms and WebView2 paint underneath the page.

    ``None`` paints black behind a transparent WebView2 for the glass layer to
    show through; a color paints the window opaque again.  Both properties
    belong to the WinForms UI thread, so the change is marshalled onto it.
    """
    # pythonnet provides these .NET namespaces once pywebview has loaded the
    # WinForms runtime, which it has by the time a window exists to pass here.
    from System.Drawing import Color, ColorTranslator  # type: ignore[import-not-found]  # .NET namespace provided by pythonnet

    def apply() -> None:
        if background is None:
            form.BackColor = Color.Black
            form.webview.DefaultBackgroundColor = Color.Transparent
        else:
            opaque = ColorTranslator.FromHtml(background)
            form.BackColor = opaque
            form.webview.DefaultBackgroundColor = opaque

    _on_ui_thread(form, apply)
