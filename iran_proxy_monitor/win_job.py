"""Windows Job Object: kill the sing-box client if the GUI process crashes.

This is intentionally used only for our persistent client, not the many
short-lived benchmark processes. Handle inheritance is disabled.
"""
from __future__ import annotations
import ctypes
import os


class WindowsKillJob:
    def __init__(self, process):
        self._handle = None
        if os.name != 'nt':return
        from ctypes import wintypes

        class BasicLimit(ctypes.Structure):
            _fields_=[('PerProcessUserTimeLimit',ctypes.c_int64),
                      ('PerJobUserTimeLimit',ctypes.c_int64),
                      ('LimitFlags',wintypes.DWORD),
                      ('MinimumWorkingSetSize',ctypes.c_size_t),
                      ('MaximumWorkingSetSize',ctypes.c_size_t),
                      ('ActiveProcessLimit',wintypes.DWORD),
                      ('Affinity',ctypes.c_size_t),
                      ('PriorityClass',wintypes.DWORD),
                      ('SchedulingClass',wintypes.DWORD)]
        class IoCounters(ctypes.Structure):
            _fields_=[('ReadOperationCount',ctypes.c_ulonglong),
                      ('WriteOperationCount',ctypes.c_ulonglong),
                      ('OtherOperationCount',ctypes.c_ulonglong),
                      ('ReadTransferCount',ctypes.c_ulonglong),
                      ('WriteTransferCount',ctypes.c_ulonglong),
                      ('OtherTransferCount',ctypes.c_ulonglong)]
        class ExtendedLimit(ctypes.Structure):
            _fields_=[('BasicLimitInformation',BasicLimit),
                      ('IoInfo',IoCounters),
                      ('ProcessMemoryLimit',ctypes.c_size_t),
                      ('JobMemoryLimit',ctypes.c_size_t),
                      ('PeakProcessMemoryUsed',ctypes.c_size_t),
                      ('PeakJobMemoryUsed',ctypes.c_size_t)]
        kernel = ctypes.windll.kernel32
        kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p]
        kernel.CreateJobObjectW.restype=ctypes.c_void_p
        kernel.SetInformationJobObject.argtypes=[ctypes.c_void_p,wintypes.INT,
                                                ctypes.c_void_p,wintypes.DWORD]
        kernel.SetInformationJobObject.restype=wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        kernel.AssignProcessToJobObject.restype=wintypes.BOOL
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        kernel.CloseHandle.restype=wintypes.BOOL
        h=kernel.CreateJobObjectW(None,None)
        if not h:raise OSError('Windows could not create a cleanup Job Object.')
        try:
            limits=ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags=0x00002000  # KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(h,9,ctypes.byref(limits),ctypes.sizeof(limits)):
                raise OSError('Windows could not configure cleanup Job Object.')
            proc_handle=getattr(process,'_handle',None)
            if proc_handle is None or not kernel.AssignProcessToJobObject(h,ctypes.c_void_p(int(proc_handle))):
                raise OSError('Windows could not attach client to crash-cleanup Job Object.')
            self._handle=h
        finally:
            if self._handle is None:kernel.CloseHandle(h)

    def close(self):
        if self._handle is not None:
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle=None
