from __future__ import annotations

import argparse
import ast
import csv
import dataclasses
import json
import re
import subprocess
import tokenize
import urllib.parse
from pathlib import Path
from typing import Sequence


GITHUB_REPOSITORY = "https://github.com/gl-inet/glkvm"
HTTP_OUTPUT_NAME = "http-endpoints.csv"
WEBSOCKET_OUTPUT_NAME = "websocket-events.csv"
COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")

HTTP_FIELDS = (
    "method",
    "path",
    "auth_required",
    "allow_usc",
    "allowed_exe_paths",
    "handler",
    "source_file",
    "source_line",
    "source_url",
)
WEBSOCKET_FIELDS = (
    "event_type",
    "binary",
    "handler",
    "source_file",
    "source_line",
    "source_url",
)


class InventoryError(ValueError):
    """Raised when source metadata cannot be inventoried deterministically."""


@dataclasses.dataclass(frozen=True, slots=True)
class HttpEndpoint:
    method: str
    path: str
    auth_required: bool
    allow_usc: bool
    allowed_exe_paths: tuple[str, ...]
    handler: str
    source_file: str
    source_line: int
    source_url: str

    def as_csv_row(self) -> dict[str, str | int]:
        return {
            "method": self.method,
            "path": self.path,
            "auth_required": _format_bool(self.auth_required),
            "allow_usc": _format_bool(self.allow_usc),
            "allowed_exe_paths": json.dumps(
                list(self.allowed_exe_paths),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "handler": self.handler,
            "source_file": self.source_file,
            "source_line": self.source_line,
            "source_url": self.source_url,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class WebSocketEvent:
    event_type: str
    binary: bool
    handler: str
    source_file: str
    source_line: int
    source_url: str

    def as_csv_row(self) -> dict[str, str | int]:
        return {
            "event_type": self.event_type,
            "binary": _format_bool(self.binary),
            "handler": self.handler,
            "source_file": self.source_file,
            "source_line": self.source_line,
            "source_url": self.source_url,
        }


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _decorator_name(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        return expression.attr
    return None


def _literal_value(expression: ast.expr, *, location: str, field: str) -> object:
    try:
        return ast.literal_eval(expression)
    except (ValueError, TypeError, SyntaxError) as exc:
        raise InventoryError(f"{location}: {field} must be a literal") from exc


def _literal_string(expression: ast.expr, *, location: str, field: str) -> str:
    value = _literal_value(expression, location=location, field=field)
    if not isinstance(value, str) or not value:
        raise InventoryError(f"{location}: {field} must be a non-empty string literal")
    return value


def _literal_bool(expression: ast.expr, *, location: str, field: str) -> bool:
    value = _literal_value(expression, location=location, field=field)
    if type(value) is not bool:
        raise InventoryError(f"{location}: {field} must be a boolean literal")
    return value


def _literal_paths(expression: ast.expr, *, location: str) -> tuple[str, ...]:
    value = _literal_value(expression, location=location, field="allowed_exe_paths")
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise InventoryError(
            f"{location}: allowed_exe_paths must be a literal list or tuple of strings"
        )
    return tuple(value)


def _public_http_path(path: str, *, location: str) -> str:
    if not path.startswith("/"):
        raise InventoryError(f"{location}: HTTP path must start with '/'")
    if path == "/redfish" or path.startswith("/redfish/"):
        return path
    return f"/api{path}"


def _source_url(commit: str, source_file: str, source_line: int) -> str:
    encoded_path = urllib.parse.quote(source_file, safe="/")
    return f"{GITHUB_REPOSITORY}/blob/{commit}/{encoded_path}#L{source_line}"


def _parse_http_decorator(
    decorator: ast.Call,
    *,
    handler: str,
    source_file: str,
    commit: str,
) -> HttpEndpoint:
    location = f"{source_file}:{decorator.lineno}"
    parameter_order = (
        "method",
        "path",
        "auth_required",
        "allow_usc",
        "allowed_exe_paths",
    )
    if len(decorator.args) > len(parameter_order):
        raise InventoryError(f"{location}: exposed_http has too many positional arguments")

    values: dict[str, ast.expr] = {}
    for name, expression in zip(parameter_order, decorator.args):
        values[name] = expression

    for keyword in decorator.keywords:
        if keyword.arg is None:
            raise InventoryError(f"{location}: exposed_http does not allow dynamic **kwargs")
        name = "method" if keyword.arg == "http_method" else keyword.arg
        if name not in parameter_order:
            raise InventoryError(
                f"{location}: unsupported exposed_http keyword {keyword.arg!r}"
            )
        if name in values:
            raise InventoryError(f"{location}: duplicate exposed_http argument {name!r}")
        values[name] = keyword.value

    if "method" not in values or "path" not in values:
        raise InventoryError(f"{location}: exposed_http requires literal method and path")

    method = _literal_string(values["method"], location=location, field="method").upper()
    internal_path = _literal_string(values["path"], location=location, field="path")
    auth_required = (
        _literal_bool(values["auth_required"], location=location, field="auth_required")
        if "auth_required" in values
        else True
    )
    allow_usc = (
        _literal_bool(values["allow_usc"], location=location, field="allow_usc")
        if "allow_usc" in values
        else True
    )
    allowed_exe_paths = (
        _literal_paths(values["allowed_exe_paths"], location=location)
        if "allowed_exe_paths" in values
        else ()
    )
    public_path = _public_http_path(internal_path, location=location)
    return HttpEndpoint(
        method=method,
        path=public_path,
        auth_required=auth_required,
        allow_usc=allow_usc,
        allowed_exe_paths=allowed_exe_paths,
        handler=handler,
        source_file=source_file,
        source_line=decorator.lineno,
        source_url=_source_url(commit, source_file, decorator.lineno),
    )


def _parse_websocket_decorator(
    decorator: ast.Call,
    *,
    handler: str,
    source_file: str,
    commit: str,
) -> WebSocketEvent:
    location = f"{source_file}:{decorator.lineno}"
    if decorator.keywords:
        raise InventoryError(f"{location}: exposed_ws accepts one positional literal")
    if len(decorator.args) != 1:
        raise InventoryError(f"{location}: exposed_ws requires exactly one literal event type")

    value = _literal_value(decorator.args[0], location=location, field="event_type")
    if isinstance(value, str):
        if not value:
            raise InventoryError(f"{location}: WebSocket event type cannot be empty")
        event_type = value
        binary = False
    elif isinstance(value, int) and not isinstance(value, bool):
        event_type = str(value)
        binary = True
    else:
        raise InventoryError(
            f"{location}: WebSocket event type must be a string or integer literal"
        )

    return WebSocketEvent(
        event_type=event_type,
        binary=binary,
        handler=handler,
        source_file=source_file,
        source_line=decorator.lineno,
        source_url=_source_url(commit, source_file, decorator.lineno),
    )


class _ExposureVisitor(ast.NodeVisitor):
    def __init__(self, *, source_file: str, commit: str) -> None:
        self.source_file = source_file
        self.commit = commit
        self.class_stack: list[str] = []
        self.http_endpoints: list[HttpEndpoint] = []
        self.websocket_events: list[WebSocketEvent] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_handler(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_handler(node)

    def _visit_handler(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        handler = ".".join([*self.class_stack, node.name])
        for decorator in node.decorator_list:
            name = _decorator_name(decorator.func) if isinstance(decorator, ast.Call) else _decorator_name(decorator)
            if name not in {"exposed_http", "exposed_ws"}:
                continue
            if not isinstance(decorator, ast.Call):
                raise InventoryError(
                    f"{self.source_file}:{decorator.lineno}: {name} must be called"
                )
            if name == "exposed_http":
                self.http_endpoints.append(
                    _parse_http_decorator(
                        decorator,
                        handler=handler,
                        source_file=self.source_file,
                        commit=self.commit,
                    )
                )
            else:
                self.websocket_events.append(
                    _parse_websocket_decorator(
                        decorator,
                        handler=handler,
                        source_file=self.source_file,
                        commit=self.commit,
                    )
                )


def _source_files(source_root: Path) -> list[Path]:
    api_directory = source_root / "kvmd" / "apps" / "kvmd" / "api"
    server_file = source_root / "kvmd" / "apps" / "kvmd" / "server.py"
    if not api_directory.is_dir():
        raise InventoryError(f"GLKVM API directory not found: {api_directory}")
    if not server_file.is_file():
        raise InventoryError(f"GLKVM server module not found: {server_file}")

    api_files = sorted(api_directory.glob("*.py"), key=lambda path: path.name)
    if not api_files:
        raise InventoryError(f"No Python API modules found under: {api_directory}")
    return [*api_files, server_file]


def _scan_source(source_root: Path, commit: str) -> tuple[list[HttpEndpoint], list[WebSocketEvent]]:
    http_endpoints: list[HttpEndpoint] = []
    websocket_events: list[WebSocketEvent] = []
    for path in _source_files(source_root):
        source_file = path.relative_to(source_root).as_posix()
        try:
            with tokenize.open(path) as source_stream:
                tree = ast.parse(source_stream.read(), filename=source_file)
        except (OSError, SyntaxError, UnicodeError) as exc:
            raise InventoryError(f"Unable to parse {source_file}: {exc}") from exc
        visitor = _ExposureVisitor(source_file=source_file, commit=commit)
        visitor.visit(tree)
        http_endpoints.extend(visitor.http_endpoints)
        websocket_events.extend(visitor.websocket_events)

    http_endpoints.sort(
        key=lambda item: (
            item.path,
            item.method,
            item.handler,
            item.source_file,
            item.source_line,
        )
    )
    websocket_events.sort(
        key=lambda item: (
            item.event_type,
            item.binary,
            item.handler,
            item.source_file,
            item.source_line,
        )
    )
    return http_endpoints, websocket_events


def _git_head(source_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    head = result.stdout.strip().lower()
    return head if COMMIT_PATTERN.fullmatch(head) else None


def verify_source_commit(
    source_root: Path,
    commit: str,
    *,
    allow_head_mismatch: bool = False,
) -> None:
    head = _git_head(source_root)
    if head is None and not allow_head_mismatch:
        raise InventoryError(
            "Unable to verify source Git HEAD; "
            "use --allow-head-mismatch only for an intentional source snapshot override"
        )
    if head is not None and head != commit and not allow_head_mismatch:
        raise InventoryError(
            f"Source Git HEAD {head} does not match requested commit {commit}; "
            "use --allow-head-mismatch only for an intentional source snapshot override"
        )


def _write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[dict[str, str | int]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate_inventory(
    source_root: Path,
    commit: str,
    output_dir: Path,
    *,
    allow_head_mismatch: bool = False,
) -> tuple[Path, Path]:
    source_root = source_root.resolve()
    output_dir = output_dir.resolve()
    commit = commit.lower()
    if not COMMIT_PATTERN.fullmatch(commit):
        raise InventoryError("commit must be an exact 40-character hexadecimal Git commit")
    if not source_root.is_dir():
        raise InventoryError(f"GLKVM source root not found: {source_root}")

    verify_source_commit(
        source_root,
        commit,
        allow_head_mismatch=allow_head_mismatch,
    )
    http_endpoints, websocket_events = _scan_source(source_root, commit)
    output_dir.mkdir(parents=True, exist_ok=True)
    http_output = output_dir / HTTP_OUTPUT_NAME
    websocket_output = output_dir / WEBSOCKET_OUTPUT_NAME
    _write_csv(
        http_output,
        HTTP_FIELDS,
        [endpoint.as_csv_row() for endpoint in http_endpoints],
    )
    _write_csv(
        websocket_output,
        WEBSOCKET_FIELDS,
        [event.as_csv_row() for event in websocket_events],
    )
    return http_output, websocket_output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic HTTP and WebSocket inventories from GLKVM source.",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="GLKVM checkout root containing kvmd/apps/kvmd.",
    )
    parser.add_argument(
        "--commit",
        required=True,
        help="Exact 40-character GLKVM source commit used in source links.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory that receives http-endpoints.csv and websocket-events.csv.",
    )
    parser.add_argument(
        "--allow-head-mismatch",
        action="store_true",
        help="Allow an available source Git HEAD to differ from --commit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        generate_inventory(
            args.source_root,
            args.commit,
            args.output_dir,
            allow_head_mismatch=args.allow_head_mismatch,
        )
    except InventoryError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
