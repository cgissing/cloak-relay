from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .server import run as run_server


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18796
APP_NAME = "cloak-relay"


@dataclass(frozen=True)
class RuntimePaths:
    data_dir: Path

    @property
    def pid_file(self) -> Path:
        return self.data_dir / "cloak-relay.pid"

    @property
    def log_file(self) -> Path:
        return self.data_dir / "logs" / "cloak-relay.log"

    @property
    def profiles_root(self) -> Path:
        return self.data_dir / "profiles"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.profiles_root.mkdir(parents=True, exist_ok=True)


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return windows_pid_is_running(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def windows_pid_is_running(pid: int) -> bool:
    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def read_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def write_pid(pid_file: Path, pid: int) -> None:
    pid_file.write_text(str(pid), encoding="utf-8")


def detect_platform() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform.startswith("linux"):
        release = platform.release().lower()
        if "microsoft" in release or "wsl" in release or os.environ.get("WSL_DISTRO_NAME"):
            return "wsl"
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    return sys.platform


def serve(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    paths = RuntimePaths(data_dir)
    paths.ensure_dirs()
    run_server(args.host, args.port, args.profiles_root or paths.profiles_root)
    return 0


def start_background(args: argparse.Namespace) -> int:
    paths = RuntimePaths(Path(args.data_dir).resolve())
    paths.ensure_dirs()
    profiles_root = Path(args.profiles_root).resolve() if args.profiles_root else paths.profiles_root
    profiles_root.mkdir(parents=True, exist_ok=True)
    existing = read_pid(paths.pid_file)
    if existing and pid_is_running(existing):
        print(json.dumps({"running": True, "pid": existing, "url": relay_url(args)}, ensure_ascii=False))
        return 0

    command = [
        sys.executable,
        "-m",
        "cloak_relay.cli",
        "serve",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--data-dir",
        str(paths.data_dir),
        "--profiles-root",
        str(profiles_root),
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags |= subprocess.CREATE_NO_WINDOW
    with paths.log_file.open("ab") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=str(Path.cwd()),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            close_fds=os.name != "nt",
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    write_pid(paths.pid_file, process.pid)
    print(
        json.dumps(
            {
                "running": True,
                "pid": process.pid,
                "url": relay_url(args),
                "log": str(paths.log_file),
            },
            ensure_ascii=False,
        )
    )
    return 0


def stop_background(args: argparse.Namespace) -> int:
    paths = RuntimePaths(Path(args.data_dir).resolve())
    pid = read_pid(paths.pid_file)
    if not pid:
        print(json.dumps({"running": False, "stopped": False}, ensure_ascii=False))
        return 0
    if pid_is_running(pid):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
    if paths.pid_file.exists():
        paths.pid_file.unlink()
    print(json.dumps({"running": False, "stopped": True, "pid": pid}, ensure_ascii=False))
    return 0


def status(args: argparse.Namespace) -> int:
    paths = RuntimePaths(Path(args.data_dir).resolve())
    pid = read_pid(paths.pid_file)
    running = bool(pid and pid_is_running(pid))
    print(
        json.dumps(
            {
                "running": running,
                "pid": pid if running else None,
                "url": relay_url(args),
                "pidFile": str(paths.pid_file),
                "log": str(paths.log_file),
            },
            ensure_ascii=False,
        )
    )
    return 0


def install_service(args: argparse.Namespace) -> int:
    if detect_platform() == "windows":
        return install_windows_task(args)
    if detect_platform() in {"linux", "wsl"}:
        return install_systemd_user_service(args)
    raise SystemExit(f"install-service is not supported on {detect_platform()}")


def install_windows_task(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    command_parts = [
        f'"{sys.executable}"',
        "-m",
        "cloak_relay.cli",
        "start",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--data-dir",
        f'"{data_dir}"',
    ]
    if args.profiles_root:
        command_parts.extend(["--profiles-root", f'"{Path(args.profiles_root).resolve()}"'])
    command = " ".join(command_parts)
    subprocess.run(
        [
            "schtasks",
            "/Create",
            "/TN",
            args.task_name,
            "/SC",
            "ONLOGON",
            "/TR",
            command,
            "/RL",
            "LIMITED",
            "/F",
        ],
        check=True,
    )
    if args.start_now:
        start_background(args)
    print(json.dumps({"installed": True, "taskName": args.task_name}, ensure_ascii=False))
    return 0


def uninstall_service(args: argparse.Namespace) -> int:
    if detect_platform() == "windows":
        return uninstall_windows_task(args)
    if detect_platform() in {"linux", "wsl"}:
        return uninstall_systemd_user_service(args)
    raise SystemExit(f"uninstall-service is not supported on {detect_platform()}")


def uninstall_windows_task(args: argparse.Namespace) -> int:
    subprocess.run(["schtasks", "/Delete", "/TN", args.task_name, "/F"], check=False)
    print(json.dumps({"installed": False, "taskName": args.task_name}, ensure_ascii=False))
    return 0


def install_systemd_user_service(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    profiles_root = Path(args.profiles_root).resolve() if args.profiles_root else data_dir / "profiles"
    service_name = service_file_name(args.service_name)
    service_dir = systemd_user_dir()
    service_dir.mkdir(parents=True, exist_ok=True)
    service_path = service_dir / service_name
    service_path.write_text(
        build_systemd_unit(
            python_executable=sys.executable,
            working_dir=Path.cwd(),
            host=args.host,
            port=args.port,
            data_dir=data_dir,
            profiles_root=profiles_root,
        ),
        encoding="utf-8",
    )

    systemctl = systemctl_available()
    result: dict[str, object] = {
        "installed": True,
        "backend": "systemd-user",
        "serviceName": service_name,
        "serviceFile": str(service_path),
        "systemctl": systemctl,
    }
    if systemctl:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", service_name], check=True)
        result["enabled"] = True
        if args.start_now:
            subprocess.run(["systemctl", "--user", "start", service_name], check=True)
            result["started"] = True
    else:
        result["enabled"] = False
        result["warning"] = (
            "systemctl --user is not available. The unit file was written, but auto-start was not enabled. "
            "Use `cloak-relay start` as the PID-based background fallback."
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0


def uninstall_systemd_user_service(args: argparse.Namespace) -> int:
    service_name = service_file_name(args.service_name)
    service_path = systemd_user_dir() / service_name
    systemctl = systemctl_available()
    if systemctl:
        subprocess.run(["systemctl", "--user", "disable", "--now", service_name], check=False)
    if service_path.exists():
        service_path.unlink()
    if systemctl:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    print(
        json.dumps(
            {
                "installed": False,
                "backend": "systemd-user",
                "serviceName": service_name,
                "serviceFile": str(service_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


def service_file_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("service name must not be empty")
    if "/" in normalized or "\\" in normalized or ".." in normalized:
        raise ValueError("service name must not contain path components")
    if not normalized.endswith(".service"):
        normalized += ".service"
    return normalized


def systemd_user_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def systemctl_available() -> bool:
    try:
        completed = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return False
    return completed.returncode == 0


def build_systemd_unit(
    *,
    python_executable: str,
    working_dir: Path,
    host: str,
    port: int,
    data_dir: Path,
    profiles_root: Path,
) -> str:
    command = [
        python_executable,
        "-m",
        "cloak_relay.cli",
        "serve",
        "--host",
        host,
        "--port",
        str(port),
        "--data-dir",
        str(data_dir),
        "--profiles-root",
        str(profiles_root),
    ]
    return "\n".join(
        [
            "[Unit]",
            "Description=Cloak Relay local browser automation bridge",
            "After=default.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={quote_systemd_arg(str(working_dir))}",
            f"ExecStart={' '.join(quote_systemd_arg(part) for part in command)}",
            "Restart=on-failure",
            "RestartSec=3",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )


def quote_systemd_arg(value: str) -> str:
    if value and all(ch not in value for ch in ' \t\n"\\'):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def relay_url(args: argparse.Namespace) -> str:
    return f"http://{args.host}:{args.port}"


def default_runtime_data_dir(
    *,
    os_name: str | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
    home: Path | None = None,
) -> Path:
    current_os = os_name or os.name
    current_env = env or os.environ
    current_home = home or Path.home()
    if current_os == "nt":
        root = current_env.get("LOCALAPPDATA")
        if root:
            return Path(root) / APP_NAME
        return current_home / "AppData" / "Local" / APP_NAME
    root = current_env.get("XDG_DATA_HOME")
    if root:
        return Path(root) / APP_NAME
    return current_home / ".local" / "share" / APP_NAME


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Cloak Relay.")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    subparsers = parser.add_subparsers(dest="command")

    for name in ["serve", "start", "stop", "status", "install-service", "uninstall-service", "enable", "disable"]:
        sub = subparsers.add_parser(name)
        add_common_runtime_args(sub)
        if name in {"install-service", "uninstall-service", "enable", "disable"}:
            sub.add_argument("--task-name", default="CloakRelay")
            sub.add_argument("--service-name", default="cloak-relay.service")
        if name in {"install-service", "enable"}:
            sub.add_argument("--start-now", action="store_true")

    return parser


def add_common_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--data-dir", default=str(default_runtime_data_dir()))
    parser.add_argument("--profiles-root")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.version:
        from . import __version__

        print(__version__)
        return 0
    if args.command == "serve":
        return serve(args)
    if args.command == "start":
        return start_background(args)
    if args.command == "stop":
        return stop_background(args)
    if args.command == "status":
        return status(args)
    if args.command in {"install-service", "enable"}:
        return install_service(args)
    if args.command in {"uninstall-service", "disable"}:
        return uninstall_service(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
