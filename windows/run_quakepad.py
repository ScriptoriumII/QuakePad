"""Lanceur de QuakePad (utilisé aussi comme point d'entrée PyInstaller)."""
import sys

from quakepad.app import main

if __name__ == "__main__":
    sys.exit(main())
