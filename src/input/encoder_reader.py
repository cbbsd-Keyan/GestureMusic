"""Reader for the USB JSON protocol emitted by firmware/EncoderControl."""
import ctypes
from ctypes import wintypes
import json


class _WindowsSerial:
    """Small pyserial-free reader for a Windows COM port.

    It is used only when pyserial is unavailable.  Read timeouts are immediate
    so the desktop menu can keep polling without blocking its audio loop.
    """
    GENERIC_READ = 0x80000000
    OPEN_EXISTING = 3
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class DCB(ctypes.Structure):
        _fields_ = [
            ('DCBlength', wintypes.DWORD), ('BaudRate', wintypes.DWORD),
            ('flags', wintypes.DWORD), ('wReserved', wintypes.WORD),
            ('XonLim', wintypes.WORD), ('XoffLim', wintypes.WORD),
            ('ByteSize', ctypes.c_ubyte), ('Parity', ctypes.c_ubyte),
            ('StopBits', ctypes.c_ubyte), ('XonChar', ctypes.c_char),
            ('XoffChar', ctypes.c_char), ('ErrorChar', ctypes.c_char),
            ('EofChar', ctypes.c_char), ('EvtChar', ctypes.c_char),
            ('wReserved1', wintypes.WORD),
        ]

    class COMMTIMEOUTS(ctypes.Structure):
        _fields_ = [
            ('ReadIntervalTimeout', wintypes.DWORD),
            ('ReadTotalTimeoutMultiplier', wintypes.DWORD),
            ('ReadTotalTimeoutConstant', wintypes.DWORD),
            ('WriteTotalTimeoutMultiplier', wintypes.DWORD),
            ('WriteTotalTimeoutConstant', wintypes.DWORD),
        ]

    def __init__(self, port, baudrate=115200, timeout=0):
        del timeout
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel32.CreateFileW.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        self.kernel32.CreateFileW.restype = wintypes.HANDLE
        self.kernel32.GetCommState.argtypes = (wintypes.HANDLE, wintypes.LPVOID)
        self.kernel32.GetCommState.restype = wintypes.BOOL
        self.kernel32.SetCommState.argtypes = (wintypes.HANDLE, wintypes.LPVOID)
        self.kernel32.SetCommState.restype = wintypes.BOOL
        self.kernel32.SetCommTimeouts.argtypes = (wintypes.HANDLE, wintypes.LPVOID)
        self.kernel32.SetCommTimeouts.restype = wintypes.BOOL
        self.kernel32.ReadFile.argtypes = (
            wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
            wintypes.LPVOID, wintypes.LPVOID,
        )
        self.kernel32.ReadFile.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        path = '\\\\.\\' + str(port).upper()
        self.handle = self.kernel32.CreateFileW(
            path, self.GENERIC_READ, 0, None, self.OPEN_EXISTING, 0, None,
        )
        if self.handle == self.INVALID_HANDLE_VALUE:
            raise OSError(ctypes.get_last_error(), f'无法打开串口 {port}')
        try:
            dcb = self.DCB()
            dcb.DCBlength = ctypes.sizeof(self.DCB)
            if not self.kernel32.GetCommState(self.handle, ctypes.byref(dcb)):
                raise OSError(ctypes.get_last_error(), f'无法读取串口 {port} 的设置')
            dcb.BaudRate = baudrate
            dcb.ByteSize = 8
            dcb.Parity = 0
            dcb.StopBits = 0
            dcb.flags |= 1  # fBinary
            if not self.kernel32.SetCommState(self.handle, ctypes.byref(dcb)):
                raise OSError(ctypes.get_last_error(), f'无法设置串口 {port}')
            timeouts = self.COMMTIMEOUTS(0xFFFFFFFF, 0, 0, 0, 0)
            if not self.kernel32.SetCommTimeouts(self.handle, ctypes.byref(timeouts)):
                raise OSError(ctypes.get_last_error(), f'无法设置串口 {port} 的读取超时')
        except Exception:
            self.close()
            raise
        self.pending = bytearray()

    def readline(self):
        if b'\n' in self.pending:
            index = self.pending.index(b'\n') + 1
            result = bytes(self.pending[:index])
            del self.pending[:index]
            return result
        chunk = ctypes.create_string_buffer(512)
        count = wintypes.DWORD()
        if not self.kernel32.ReadFile(self.handle, chunk, len(chunk), ctypes.byref(count), None):
            raise OSError(ctypes.get_last_error(), '串口读取失败')
        self.pending.extend(chunk.raw[:count.value])
        if b'\n' not in self.pending:
            return b''
        index = self.pending.index(b'\n') + 1
        result = bytes(self.pending[:index])
        del self.pending[:index]
        return result

    def close(self):
        if getattr(self, 'handle', self.INVALID_HANDLE_VALUE) != self.INVALID_HANDLE_VALUE:
            self.kernel32.CloseHandle(self.handle)
            self.handle = self.INVALID_HANDLE_VALUE


def _default_serial_factory():
    try:
        import serial
        return serial.Serial
    except (ImportError, AttributeError):
        return _WindowsSerial


class EncoderReader:
    """Read one valid encoder event at a time; invalid serial input is ignored."""

    def __init__(self, port, baudrate=115200, serial_factory=None):
        if serial_factory is None:
            serial_factory = _default_serial_factory()
        self.serial = serial_factory(port, baudrate=baudrate, timeout=0)

    @staticmethod
    def parse(line):
        try:
            event = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(event, dict) or event.get('type') != 'encoder':
            return None
        if event.get('delta') in (-1, 1) and len(event) == 2:
            return event
        if event.get('press') in ('short', 'long') and len(event) == 2:
            return event
        if event.get('status') == 'ready' and len(event) == 2:
            return event
        return None

    def read(self):
        raw = self.serial.readline()
        if not raw:
            return None
        return self.parse(raw.decode('utf-8', errors='replace').strip())

    def close(self):
        self.serial.close()
