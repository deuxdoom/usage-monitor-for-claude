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
        ('ai_agents_usage_monitor/theme.json', 'ai_agents_usage_monitor'),
        # Compiled from glass_layer.cs by build.py before PyInstaller runs.
        ('ai_agents_usage_monitor/glass_layer.dll', 'ai_agents_usage_monitor'),
        ('ai_agents_usage_monitor/popup/popup.html', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/popup.css', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/matte.css', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/glass.css', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/popup.js', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/usage-cards.js', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/bar-view.js', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/updater.html', 'ai_agents_usage_monitor/popup'),
        ('ai_agents_usage_monitor/popup/Pretendard-Regular.woff2', 'ai_agents_usage_monitor/popup'),
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
        # Optional backends that never run here: urllib3 decodes zstd only when
        # the module exists, requests falls back to UTF-8 without a charset
        # detector (every response read here is JSON), and zipfile, tarfile and
        # shutil import bz2/lzma lazily. The pure-Python fallbacks of decimal
        # and datetime are dead weight beside their C modules.
        'compression.zstd', '_zstd', 'charset_normalizer', 'bz2', '_bz2', 'lzma', '_lzma', '_pydecimal', '_pydatetime',
        # Pillow's hook bundles every image format. The tray icon is drawn in
        # memory and pystray hands it to Windows as ICO, which needs only the
        # ICO, PNG and BMP plugins; Image.init() skips a plugin that is missing.
        *['PIL.' + name for name in (
            'AvifImagePlugin', 'BlpImagePlugin', 'BufrStubImagePlugin', 'CurImagePlugin', 'DcxImagePlugin', 'DdsImagePlugin',
            'EpsImagePlugin', 'FitsImagePlugin', 'FliImagePlugin', 'FpxImagePlugin', 'FtexImagePlugin', 'GbrImagePlugin',
            'GifImagePlugin', 'GribStubImagePlugin', 'Hdf5StubImagePlugin', 'IcnsImagePlugin', 'ImImagePlugin', 'ImtImagePlugin',
            'IptcImagePlugin', 'Jpeg2KImagePlugin', 'JpegImagePlugin', 'JpegPresets', 'McIdasImagePlugin', 'MicImagePlugin',
            'MpegImagePlugin', 'MpoImagePlugin', 'MspImagePlugin', 'PalmImagePlugin', 'PcdImagePlugin', 'PcxImagePlugin',
            'PdfImagePlugin', 'PdfParser', 'PixarImagePlugin', 'PpmImagePlugin', 'PsdImagePlugin', 'QoiImagePlugin',
            'SgiImagePlugin', 'SpiderImagePlugin', 'SunImagePlugin', 'TgaImagePlugin', 'TiffImagePlugin', 'WebPImagePlugin',
            'WmfImagePlugin', 'XVThumbImagePlugin', 'XbmImagePlugin', 'XpmImagePlugin',
            'ImageQt', 'ImageTk', 'ImageShow', 'ImageCms', 'ImageMath', 'ImageDraw2',
        )],
    ],
    noarchive=False,
)

# pythonnet's API documentation, which nothing reads at run time. The WebView2
# loaders for win-arm64 and win-x86 stay although the EXE is always x64:
# pywebview's edgechromium module looks up all three folders on import and
# raises FileNotFoundError when one is missing, so the app would not start.
a.datas = [entry for entry in a.datas if not entry[0].endswith('Python.Runtime.xml')]

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
    icon='assets/images/ai_agents_usage_monitor.ico',
    version='version_info.py',
)
