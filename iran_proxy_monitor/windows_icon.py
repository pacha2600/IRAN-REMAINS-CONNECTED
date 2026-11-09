"""Windows-native application icon for frozen and source-run Tkinter windows.

Uses the top-level window, rather than assuming GetParent(winfo_id()) is the
visible taskbar window. HICON ownership is retained by the caller.
"""
from __future__ import annotations


def apply_windows_icon(tk_hwnd: int, ico_file: str) -> dict:
    import ctypes
    from ctypes import wintypes
    from pathlib import Path

    if not Path(ico_file).is_file():
        raise FileNotFoundError('Application icon file is absent')
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetAncestor.argtypes=(wintypes.HWND,wintypes.UINT)
    user32.GetAncestor.restype=wintypes.HWND
    user32.GetParent.argtypes=(wintypes.HWND,)
    user32.GetParent.restype=wintypes.HWND
    user32.LoadImageW.argtypes=(wintypes.HINSTANCE,wintypes.LPCWSTR,wintypes.UINT,
                                ctypes.c_int,ctypes.c_int,wintypes.UINT)
    user32.LoadImageW.restype=wintypes.HANDLE
    user32.SendMessageW.argtypes=(wintypes.HWND,wintypes.UINT,ctypes.c_size_t,ctypes.c_ssize_t)
    user32.SendMessageW.restype=ctypes.c_ssize_t
    user32.GetClassLongPtrW.argtypes=(wintypes.HWND,ctypes.c_int)
    user32.GetClassLongPtrW.restype=ctypes.c_ssize_t
    user32.SetClassLongPtrW.argtypes=(wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t)
    user32.SetClassLongPtrW.restype=ctypes.c_ssize_t

    # GA_ROOT=2 follows a chain of *parent* windows to the actual frame.
    # Tk's winfo_id is often a child beneath an invisible/native wrapper.
    root=int(user32.GetAncestor(tk_hwnd,2) or tk_hwnd)
    parent=int(user32.GetParent(tk_hwnd) or 0)
    windows=list(dict.fromkeys(hwnd for hwnd in (root,parent,tk_hwnd) if hwnd))
    applied=False
    handles=[]
    # LOAD_LIBRARY_AS_DATAFILE is not needed with LR_LOADFROMFILE (0x10).
    for size,kind,class_index in ((16,0,-34),(32,1,-14)):
        icon=int(user32.LoadImageW(None,ico_file,1,size,size,0x10) or 0)
        if not icon:
            continue
        handles.append(icon)
        for hwnd in windows:
            # WM_SETICON=0x80; ICON_SMALL=0, ICON_BIG=1.
            user32.SendMessageW(hwnd,0x80,kind,icon)
            applied=True
        # Tk's frame class may provide the default Python/Tk icon even
        # after WM_SETICON; update the class fallback for this window.
        user32.SetClassLongPtrW(root,class_index,icon)
    # SWP_FRAMECHANGED=0x20, SWP_NOSIZE=1, SWP_NOMOVE=2,
    # SWP_NOZORDER=4, SWP_NOACTIVATE=0x10. Request a non-disruptive
    # frame refresh after updating its icon properties.
    if applied:
        user32.SetWindowPos.argtypes=(wintypes.HWND,wintypes.HWND,ctypes.c_int,
                                      ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT)
        user32.SetWindowPos.restype=wintypes.BOOL
        user32.SetWindowPos(root,None,0,0,0,0,0x37)
    return {'applied':applied,'windows':windows,'handles':handles}
