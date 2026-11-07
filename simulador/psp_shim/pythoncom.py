"""Shim de pythoncom para correr los conectores de presion contra el simulador (sin COM)."""


def PumpWaitingMessages():
    return 0


def CoInitialize():
    pass


def CoUninitialize():
    pass
