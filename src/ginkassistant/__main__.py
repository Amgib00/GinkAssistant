"""
Entry point Briefcase runs. Mirrors the IS_ANDROID gating the real
__main__.py already had working correctly for the old PySide6/Toga
split -- now that PySide6 is gone entirely, every platform just runs
this same Toga app.
"""

from ginkassistant.app import main

if __name__ == "__main__":
    app = main()
    app.main_loop()
