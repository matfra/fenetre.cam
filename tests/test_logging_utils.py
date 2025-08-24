import logging

from fenetre.logging_utils import ModuleColorFormatter

def test_header_has_color_only():
    formatter = ModuleColorFormatter("[%(levelname)s] %(message)s")
    record = logging.LogRecord("mod", logging.INFO, "", 0, "msg", (), None)
    formatted = formatter.format(record)
    color = ModuleColorFormatter.COLORS[logging.INFO]
    header, message = formatted.split("\x1b[0m", 1)
    assert header == f"{color}[INFO]"
    assert "\x1b[" not in message
