import re

def normalize(line: str, ds: str, subds: str) -> str:
    """Return a normalized version of *line* appropriate for *ds*/*subds*."""
    platform = _get_platform(ds, subds)
    line = _normalize_common(line)

    if platform == "freebsd":
        line = _normalize_freebsd(line)
    elif platform == "android":
        line = _normalize_android(line)
    elif platform == "windows":
        line = _normalize_windows(line)
    elif platform == "linux":
        line = _normalize_linux(line)

    return line.strip()


# Platform router
def _get_platform(ds: str, subds: str) -> str:
    if subds == "cadets":
        return "freebsd"
    if subds == "clearscope":
        return "android"
    if subds in ("fivedirections", "marple") or ds == "optc":
        return "windows"
    if subds in ("theia", "trace"):
        return "linux"
    if ds == "hpc":
        return "linux"
    raise

# Cross-platform rules
def _normalize_common(line: str) -> str:
    # IP addresses -> <IP>
    line = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '<IP>', line)

    # --port <N>
    line = re.sub(r'(--port\s+)\d+', r'\1<PORT>', line)

    # --pid <N>
    line = re.sub(r'(--pid\s+)\d+', r'\1<PID>', line)

    # scp: collapse variable source/destination paths
    scp_match = re.match(r'(scp\s+(?:-[a-z]\s+)*)(.+)', line)
    if scp_match and line.lstrip().startswith('scp'):
        flags = scp_match.group(1).strip()
        rest = scp_match.group(2).strip()
        if re.search(r'\S+@<IP>:', rest) or re.search(r'-[td]\s+', rest):
            line = flags + ' <SRC> <DST>'

    # ping -n <count>
    line = re.sub(r'(ping\s+-n\s+)\d+', r'\1<N>', line)

    # kill -SIG <PID>
    line = re.sub(r'(kill\s+-\S+\s+)\d+', r'\1<PID>', line)

    return line

# FreeBSD  (cadets) 
def _normalize_freebsd(line: str) -> str:
    # /tmp/foo.XXXXXXXX
    line = re.sub(r'(/tmp/\S+\.)[A-Za-z0-9]{6,}', r'\1<RAND>', line)

    # /tmp/<word><rand>/...  (e.g. /tmp/locatexhmAyn5hWz/_updatedb...)
    line = re.sub(
        r'(/tmp/)[a-z]+[A-Za-z0-9]{6,}(/\S+)', r'\1<TMPDIR>\2', line
    )

    # Build-script sed: sed s/XXX_FUNCTION_NAME_XXX/<func>/ base.c
    line = re.sub(
        r'(sed\s+s/XXX_FUNCTION_NAME_XXX/)\w+(/\s+\S+)',
        r'\1<FUNC>\2', line,
    )

    # Build-script cc: cc ... XX.c -o XX.o
    line = re.sub(
        r'(cc\s+.*?\s+)\w+\.c(\s+-o\s+)\w+\.o',
        r'\1<SRC>.c\2<SRC>.o', line,
    )

    # Embedded PIDs in logger messages etc.
    line = re.sub(r'(kill\s+-\w+\s+)\d+', r'\1<PID>', line)

    return line

# clearscope
def _normalize_android(line: str) -> str:
    # Package names are the behaviour identity
    return line


# Windows  (fivedirections, marple, optc/*)
def _normalize_windows(line: str) -> str:
    # path-case canonicalisation
    line = re.sub(
        r'(?i)c:\\\\windows\\\\system32',
        r'C:\\\\Windows\\\\System32', line,
    )
    line = re.sub(
        r'(?i)c:\\\\windows\\\\syswow64',
        r'C:\\\\Windows\\\\SysWOW64', line,
    )
    line = re.sub(r'(?i)c:\\\\windows', r'C:\\\\Windows', line)

    # GUIDs (braced and bare)
    line = re.sub(
        r'\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}'
        r'-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}',
        '{<GUID>}', line,
    )
    line = re.sub(
        r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}'
        r'-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b',
        '<GUID>', line,
    )

    # smss.exe hex boot args
    line = re.sub(r'\b0{4,}[0-9a-fA-F]+\b', '<HEX>', line)

    # WerFault
    line = re.sub(r'(Global\\\\)[0-9a-f]{16,}', r'\1<HASH>', line)
    line = re.sub(r'(WerFault\.exe\s.*-p\s+)\d+', r'\1<PID>', line)
    line = re.sub(r'(WerFault\.exe\s.*-s\s+)\d+', r'\1<SESSION>', line)
    line = re.sub(r'(WerFault\.exe\s.*-ip\s+)\d+', r'\1<PID>', line)

    # taskeng.exe
    line = re.sub(r'(taskeng\.exe\s+)\{[^}]+\}', r'\1{<TASKGUID>}', line)
    line = re.sub(r'TA1-\w+-\d+', 'TA1-<HOST>', line)
    line = re.sub(r'LUA\[\d+\]', 'LUA[<N>]', line)

    # SIDs
    line = re.sub(r'S-1-\d+-[\d-]+', 'S-<SID>', line)

    # encoded PowerShell
    line = re.sub(r'(-EncodedCommand\s+)\S+', r'\1<ENCODED>', line)

    # consent.exe
    line = re.sub(
        r'(consent\.exe\s+)\d+\s+\d+\s+\S+',
        r'\1<PID> <SESSION> <HANDLE>', line,
    )

    # /t <PID>
    line = re.sub(r'(/t\s+)\d+', r'\1<PID>', line)

    # telemetry correlation vectors
    line = re.sub(r'(-c[vV][:\s]+)\S+', r'\1<CV>', line)

    # AppData temp directories
    line = re.sub(
        r'(AppData\\\\Local\\\\Temp\\\\)[^\\]+',
        r'\1<TMPDIR>', line,
    )

    # Windows.WARP.JITService trailing session
    line = re.sub(
        r'(JITService\.exe\s+<GUID>\s+S-<SID>\s+S-<SID>\s+)\d+',
        r'\1<SESSION>', line,
    )

    # Office registry version
    line = re.sub(
        r'(\\\\Microsoft\\\\Office\\\\)\d+\.\d+',
        r'\1<VER>', line,
    )

    # Marple UI-automation event strings
    line = re.sub(
        r'(@ name # )[^@]+(@ value #)', r'\1<UINAME> \2', line
    )
    line = re.sub(
        r'(@ value # )[^@]+(@ controlType #)', r'\1<UIVAL> \2', line
    )
    line = re.sub(r'(@ className # ).*$', r'\1<UICLASS>', line)

    return line

# Linux  (theia, trace)
def _normalize_linux(line: str) -> str:
    # Firefox content-process preference blobs
    firefox_match = re.match(
        r'(\S*firefox\S*)\s+-contentproc\s+-childID\s+\d+'
        r'\s+-isForBrowser\s+.*?(-appdir\s+\S+)\s+\d+\s+\w+\s+\w+',
        line,
    )
    if firefox_match:
        return (
            f'{firefox_match.group(1)} -contentproc -childID <N> '
            f'-isForBrowser <PREFS> {firefox_match.group(2)} <PID> true tab'
        )

    # temp files
    line = re.sub(r'(/tmp/\S*\.)[A-Za-z0-9]{6,}', r'\1<RAND>', line)
    line = re.sub(
        r'(update-notifier/tmp\.)[A-Za-z0-9]{6,}', r'\1<RAND>', line
    )

    # hex-encoded / elapsed dates
    line = re.sub(r'(date\s+-d\s+)[0-9A-Fa-f]{10,}', r'\1<HEXTIME>', line)
    line = re.sub(
        r'(date\s+-d\s+now\s+-\s+)[\d.]+(\s+seconds)',
        r'\1<ELAPSED>\2', line,
    )

    # apport PIDs
    line = re.sub(r'(apport\s+)\d+(\s+\d+\s+\d+)', r'\1<PID>\2', line)

    # ConsoleKit uid
    line = re.sub(
        r'(ck-collect-session-info\s+--uid\s+)\d+', r'\1<UID>', line
    )

    # sleep durations
    line = re.sub(r'(sleep\s+)\d{3,}', r'\1<DURATION>', line)

    # long hex strings (sed exprs, stringPrefs leftovers, etc.)
    line = re.sub(r'[0-9A-Fa-f]{16,}', '<HEXEXPR>', line)

    # UUIDs
    line = re.sub(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}'
        r'-[0-9a-f]{4}-[0-9a-f]{12}',
        '<UUID>', line,
    )

    # kernel modules: dirname, basename, modinfo, modprobe, cp 
    line = re.sub(r'(dirname\s+\S+/)\S+\.ko', r'\1<MODULE>.ko', line)
    line = re.sub(r'(basename\s+\S+/)\S+(\.ko)', r'\1<MODULE>\2', line)
    line = re.sub(r'(modinfo\s+.*?/)\S+(\.ko)', r'\1<MODULE>\2', line)
    line = re.sub(
        r'(modprobe\s+.*--show-depends\s+)\S+', r'\1<MODULE>', line
    )
    line = re.sub(
        r'(cp\s+-pL\s+/lib/modules/\S+/kernel/\S+/)\S+(\.ko\s+)',
        r'\1<MODULE>\2', line,
    )

    # firmware paths in mkdir
    line = re.sub(
        r'(mkdir\s+-p\s+\S+/firmware/\S+/)\S+', r'\1<FWDIR>', line
    )

    # hex dir names
    line = re.sub(r'\b[A-F0-9]{6,}/replay_logdb', '<HEXDIR>/replay_logdb', line)

    # binary garbage lines
    if line and all(
        c in '\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0e\x0f\ufffd'
        or not c.isprintable()
        for c in line.strip()
    ):
        line = '<BINARY_GARBAGE>'

    # # package version strings
    # line = re.sub(r'_[a-zA-Z0-9.:~+-]+_(amd64|i386|all)\.d?deb', r'_<VERSION>.deb', line)

    # # kernel version strings
    # line = re.sub(r'\b\d+\.\d+\.\d+-\d+-generic[^\s]*', '<KERNEL_VER>', line)

    # # Collapse packages from apt cache
    # line = re.sub(r'((?:/var/cache/apt/archives//?\S+\s*){3,})', '/var/cache/apt/archives/<MULTIPLE_DEBS> ', line)

    # # Collapse binaries
    # line = re.sub(r'((?:/usr/lib/klibc/bin/\S+\s*){3,})', '/usr/lib/klibc/bin/<MULTIPLE_BINS> ', line)

    # # Collapse root directory listings
    # line = re.sub(r'(/bin /boot /data /debug /dev /etc /home.*)', '<ROOT_DIRS>', line)

    # # Collapse X11 font paths
    # line = re.sub(r'(-fp\s+)[/\w.,-]+', r'\1<FONT_PATHS>', line)

    # # Collapse compiler macros
    # line = re.sub(r'((?:-D\s*\w+(?:=[^\s]+)?\s*){4,})', '<MACROS> ', line)

    # # Collapse multiple '-name X -prune -o' chains
    # line = re.sub(r'((?:-name\s+\S+\s+-prune\s+-o\s*){3,})', '<FIND_PRUNE_CHAIN> ', line)

    # # inline sed expressions while preserving the sed command itself
    # line = re.sub(r'(sed\s+-e\s+)[^\n]{20,}', r'\1<SED_SCRIPT>', line)

    # line = re.sub(
    #     r'(stat\s+-c\s+%Y\s+/{1,2}var/lib/apt/{1,2}lists/{1,2})\S+', 
    #     r'\1<APT_REPO_LIST>', 
    #     line
    # )

    # line = re.sub(
    #     r'(cp\s+-pL\s+/lib/.*?)\s+(/tmp/mkinitramfs_)[a-zA-Z0-9]+(/.*)',
    #     r'cp -pL <LIB_OR_FW> \2<RAND>\3',
    #     line
    # )
    return line
