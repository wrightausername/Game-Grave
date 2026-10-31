"""Application entrypoint."""
import sys

if "--auto" in sys.argv:
    from core import run_auto_cleanup
    count, total, summary = run_auto_cleanup()
    print(summary)
elif "--ui-preview" in sys.argv:
    # Opt-in Crimson Command Qt UI. Classic Tk remains the default.
    try:
        from gg_desktop.app import main as crimson_main
    except ImportError:
        print("Crimson Command is optional. Install ui-preview-requirements.txt "
              "or run the dedicated Crimson preview EXE.")
        raise SystemExit(2)
    raise SystemExit(crimson_main())
else:
    from ui import GameGraveApp
    GameGraveApp().mainloop()
