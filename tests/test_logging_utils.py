import logging
from fenetre.logging_utils import ModuleColorFormatter, MODULE_COLORS, setup_logging


def test_setup_logging_sets_level():
    root = logging.getLogger()
    prev_handlers = root.handlers[:]
    prev_level = root.level
    try:
        setup_logging(level="DEBUG")
        assert root.level == logging.DEBUG
    finally:
        root.handlers = prev_handlers
        root.setLevel(prev_level)


def test_module_color_formatter_unique_colors():
    MODULE_COLORS.clear()
    formatter = ModuleColorFormatter("%(message)s")
    rec1 = logging.LogRecord(
        name="fenetre.mod1",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="m1",
        args=(),
        exc_info=None,
    )
    rec2 = logging.LogRecord(
        name="fenetre.mod2",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="m2",
        args=(),
        exc_info=None,
    )
    out1 = formatter.format(rec1)
    out2 = formatter.format(rec2)
    assert out1 != out2
    assert out1.startswith("\x1b[") and out1.endswith("\x1b[0m")
