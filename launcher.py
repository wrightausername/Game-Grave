"""Application entrypoint."""
import sys

if "--auto" in sys.argv:
    from core import run_auto_cleanup
    count, total, summary = run_auto_cleanup()
    print(summary)
else:
    from ui import GameGraveApp
    GameGraveApp().mainloop()
