"""Windows-only native titlebar icon regression; skipped on Unix CI/dev machines."""
import ctypes
from pathlib import Path
import sys
import tkinter as tk
import unittest

from iran_proxy_monitor.windows_icon import apply_windows_icon


@unittest.skipUnless(sys.platform == 'win32', 'Native Tk icon test requires Windows')
class WindowsIconTests(unittest.TestCase):
    def test_real_windows_root_has_small_and_big_branded_icons(self):
        root=tk.Tk()
        handles=[]
        try:
            root.geometry('400x200')
            root.update_idletasks()
            root.update()
            path=Path(__file__).resolve().parent.parent/'assets'/'iran-remains-connected.ico'
            result=apply_windows_icon(root.winfo_id(),str(path))
            handles=result['handles']
            self.assertTrue(result['applied'])
            self.assertEqual(len(handles),2)
            user32=ctypes.WinDLL('user32')
            user32.GetAncestor.restype=ctypes.c_void_p
            user32.GetAncestor.argtypes=(ctypes.c_void_p,ctypes.c_uint)
            user32.SendMessageW.restype=ctypes.c_ssize_t
            user32.SendMessageW.argtypes=(ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t)
            hwnd=user32.GetAncestor(root.winfo_id(),2)
            self.assertIn(user32.SendMessageW(hwnd,0x7f,0,0),handles)  # WM_GETICON, ICON_SMALL
            self.assertIn(user32.SendMessageW(hwnd,0x7f,1,0),handles)  # WM_GETICON, ICON_BIG
        finally:
            root.destroy()
            if handles:
                user32=ctypes.WinDLL('user32')
                for handle in handles:user32.DestroyIcon(ctypes.c_void_p(handle))
