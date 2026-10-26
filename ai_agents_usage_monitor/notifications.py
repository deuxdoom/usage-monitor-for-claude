"""
Windows Notifications
=====================

Post expiring Windows Runtime toasts under the app's registered identity.
"""
from __future__ import annotations

import functools
import html
import logging
from typing import Any

from .notification_identity import APP_USER_MODEL_ID

__all__ = ['show_notification']

logger = logging.getLogger(__name__)
_TOAST_LIFETIME_SECONDS = 300
_WINRT_TYPE_QUALIFIER = ', Windows, ContentType=WindowsRuntime'


def show_notification(icon: Any, message: str, title: str, identity_registered: bool) -> None:
    """Post a toast, falling back to the tray balloon if identity or runtime is unavailable.

    Parameters
    ----------
    icon : pystray.Icon
        Tray icon used for the fallback.
    message : str
        Notification body.
    title : str
        Notification title.
    identity_registered : bool
        Whether startup registered and adopted the app's notification identity.
    """
    if identity_registered:
        try:
            _show_toast(message, title)
            return
        except Exception:
            logger.warning('Windows toast failed; using tray notification', exc_info=True)
    icon.notify(message, title)


def _show_toast(message: str, title: str) -> None:
    xml_type, toast_type, manager_type = _toast_types()
    from System import Activator, DateTimeOffset, TimeSpan, Type  # type: ignore[import-untyped]  # .NET types via pythonnet

    document = Activator.CreateInstance(xml_type)
    document.LoadXml(_toast_xml(message, title))
    toast = Activator.CreateInstance(toast_type, document)
    # The registered logo lives in this process's private runtime directory.
    # An old stored toast must not pin that logo path indefinitely after exit.
    toast.ExpirationTime = DateTimeOffset.Now.Add(TimeSpan.FromSeconds(_TOAST_LIFETIME_SECONDS))
    create_notifier = manager_type.GetMethod('CreateToastNotifier', [Type.GetType('System.String')])
    create_notifier.Invoke(None, [APP_USER_MODEL_ID]).Show(toast)


@functools.cache
def _toast_types() -> tuple[Any, Any, Any]:
    """Load the Windows Runtime types without creating or posting a notification."""
    import clr  # type: ignore[import-untyped]  # pythonnet bridge already used by pywebview

    clr.AddReference('System.Runtime.WindowsRuntime')  # type: ignore[attr-defined]  # pythonnet assembly loader
    from System import Type  # type: ignore[import-untyped]  # .NET reflection via pythonnet

    names = ('Windows.Data.Xml.Dom.XmlDocument', 'Windows.UI.Notifications.ToastNotification',
             'Windows.UI.Notifications.ToastNotificationManager')
    resolved = [Type.GetType(name + _WINRT_TYPE_QUALIFIER) for name in names]
    if any(runtime_type is None for runtime_type in resolved):
        raise RuntimeError('Windows notification types are unavailable')
    return resolved[0], resolved[1], resolved[2]


def _toast_xml(message: str, title: str) -> str:
    return ('<toast><visual><binding template="ToastGeneric">'
            f'<text>{html.escape(title)}</text><text>{html.escape(message)}</text>'
            '</binding></visual></toast>')
