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
        ('ai_agents_usage_monitor/popup/popup.html', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/popup.css', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/popup.js', 'ai_agents_usage_monitor/popup'),
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
