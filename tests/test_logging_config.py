import logging

from src.kvm_core.logging_config import configure_logging


def test_configure_logging_writes_rotating_file(tmp_path):
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        log_path = configure_logging(tmp_path, "INFO")
        logging.getLogger("test.logging").info("hello from test")
        for handler in root.handlers:
            handler.flush()

        assert log_path == tmp_path / "comet-kvm.log"
        assert "hello from test" in log_path.read_text(encoding="utf-8")
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers[:] = original_handlers
        root.setLevel(original_level)
