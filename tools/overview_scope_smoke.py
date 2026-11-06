"""Compatibility entrypoint for the owner-photo and safety-engine guard.

The owner rejected the previous plain-table baseline. The original photographs,
actual photo_ui_smoke geometry and rendered comparisons now define visual QA.
"""
if __package__:
    from .photo_reference_guard import main
else:
    from photo_reference_guard import main

if __name__ == "__main__":
    raise SystemExit(main())
