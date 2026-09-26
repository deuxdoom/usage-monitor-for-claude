# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for AI Agents Usage Monitor.

Build:
  pyinstaller ai_agents_usage_monitor.spec
"""

a = Analysis(
    ['ai_agents_usage_monitor/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('locale/*.json', 'locale'),
        ('ai_agents_usage_monitor/notification_logo.ico', 'ai_agents_usage_monitor'),
        # Compiled from glass_layer.cs by build.py before PyInstaller runs.
        ('ai_agents_usage_monitor/glass_layer.dll', 'ai_agents_usage_monitor'),
        ('ai_agents_usage_monitor/popup/popup.html', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/popup.css', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/matte.css', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/glass.css', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/popup.js', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/updater.html', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/PretendardJPVariable.woff2', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/Pretendard-OFL.txt', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/Octicons-MIT.txt', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/FluentUI-MIT.txt', 'ai_agents_usage_monitor/popup'),
    ],
    hiddenimports=[
        'pystray._win32',
        'pystray._util',
        'pystray._util.win32',
        'webview',
        'webview.platforms.edgechromium',
        'clr_loader',
        'pythonnet',
        'bottle',
        'truststore',
        'truststore._windows',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'unittest', 'test',
        'xmlrpc', 'pydoc',
        'tkinter', '_tkinter',
        'PIL._avif', 'PIL._webp',
        'PIL._imagingcms', 'PIL._imagingmath', 'PIL._imagingtk', 'PIL._imagingmorph',
        'setuptools', '_distutils_hack',
        'asyncio', 'concurrent',
        'multiprocessing',
        'xml', 'tomllib',
        'sqlite3',
        # Pillow only references numpy in type hints; nothing here calls an API
        # that needs it. tray_icon.py uses Image, ImageDraw and ImageFont and
        # never fromarray.
        # Following that hint pulled in numpy and its bundled OpenBLAS, which
        # alone was ~20 MB of the frozen binary.
        'numpy', 'scipy',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AIAgentsUsageMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon='ai_agents_usage_monitor.ico',
    version='version_info.py',
)
