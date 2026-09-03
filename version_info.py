# pyright: reportUndefinedVariable=false

VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=(1, 80, 0, 0),
        prodvers=(1, 80, 0, 0),
        mask=0x3F,
        flags=0x0,
        OS=0x40004,          # VOS_NT_WINDOWS32
        fileType=0x1,        # VFT_APP
        subtype=0x0,
    ),
    kids=[
        StringFileInfo([
            StringTable(
                '041204B0',  # Lang: Korean, Charset: Unicode
                [
                    StringStruct('CompanyName', 'deuxdoom'),
                    StringStruct('FileDescription', 'Usage Monitor for Claude'),
                    StringStruct('FileVersion', '1.80.0.0'),
                    StringStruct('InternalName', 'UsageMonitorForClaude'),
                    StringStruct('OriginalFilename', 'UsageMonitorForClaude.exe'),
                    StringStruct('ProductName', 'Usage Monitor for Claude'),
                    StringStruct('ProductVersion', '1.80.0.0'),
                ],
            ),
        ]),
        VarFileInfo([VarStruct('Translation', [0x0412, 1200])]),
    ],
)
