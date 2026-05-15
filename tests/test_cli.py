from pathlib import Path

from cloak_relay.cli import (
    RuntimePaths,
    build_systemd_unit,
    default_runtime_data_dir,
    detect_platform,
    pid_is_running,
    service_file_name,
)


def test_pid_is_running_false_for_impossible_pid():
    assert pid_is_running(99999999) is False


def test_runtime_paths_are_under_data_dir(tmp_path):
    paths = RuntimePaths(tmp_path)
    assert paths.pid_file == tmp_path / "cloak-relay.pid"
    assert paths.log_file == tmp_path / "logs" / "cloak-relay.log"


def test_runtime_paths_create_log_parent(tmp_path):
    paths = RuntimePaths(tmp_path)
    paths.ensure_dirs()
    assert (tmp_path / "logs").is_dir()


def test_default_runtime_data_dir_uses_xdg_data_home(tmp_path):
    assert (
        default_runtime_data_dir(
            os_name="posix",
            env={"XDG_DATA_HOME": str(tmp_path)},
            home=tmp_path / "home",
        )
        == tmp_path / "cloak-relay"
    )


def test_service_file_name_adds_service_suffix():
    assert service_file_name("cloak-relay") == "cloak-relay.service"
    assert service_file_name("cloak-relay.service") == "cloak-relay.service"


def test_service_file_name_rejects_path_components():
    try:
        service_file_name("../cloak-relay")
    except ValueError as exc:
        assert "service name" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_detect_platform_recognizes_wsl(monkeypatch):
    monkeypatch.setattr("os.name", "posix")
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("platform.release", lambda: "5.15.153.1-microsoft-standard-WSL2")
    assert detect_platform() == "wsl"


def test_build_systemd_unit_uses_user_level_foreground_server(tmp_path):
    unit = build_systemd_unit(
        python_executable="/home/user/project/.venv/bin/python",
        working_dir=tmp_path,
        host="127.0.0.1",
        port=18796,
        data_dir=tmp_path / "data",
        profiles_root=tmp_path / "data" / "profiles",
    )
    assert "[Unit]" in unit
    assert "ExecStart=/home/user/project/.venv/bin/python -m cloak_relay.cli serve" in unit
    assert "--host 127.0.0.1" in unit
    assert "--port 18796" in unit
    assert "Restart=on-failure" in unit
    assert "WantedBy=default.target" in unit
