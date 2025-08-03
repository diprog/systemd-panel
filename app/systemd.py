import asyncio
from pathlib import Path


def _read_description(unit_path: str) -> str:
    """
    Read Description from [Unit] section of a .service file.

    :param unit_path: Absolute path to unit file.

    :returns: Description string or empty.
    """
    try:
        with open(unit_path, "r", encoding="utf-8", errors="ignore") as f:
            in_unit = False
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    in_unit = line.lower() == "[unit]"
                    continue
                if in_unit and line.lower().startswith("description="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        return ""
    return ""


def discover_units(service_dir: str) -> dict:
    """
    Discover only admin-owned .service units placed directly in service_dir.

    The scan is non-recursive and ignores symlinks and subdirectories, so
    units pulled in via *.wants/ etc. are not included.

    :param service_dir: Base directory to scan, typically /etc/systemd/system.

    :returns: Dict unit_name -> absolute path within service_dir.
    """
    result = {}
    base = Path(service_dir)
    if not base.is_dir():
        return result

    for p in base.glob("*.service"):
        try:
            if p.parent == base and p.is_file() and not p.is_symlink():
                result[p.name] = str(p)
        except Exception:
            continue
    return result


async def _run(*args: str) -> tuple[int, str, str]:
    """
    Run a subprocess and capture output.

    :param args: argv list.

    :returns: (returncode, stdout, stderr).
    """
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")


async def get_unit_status(unit: str) -> dict:
    """
    Return service status via `systemctl show`.

    :param unit: Service unit name.

    :returns: Dict with ActiveState, SubState, LoadState, UnitFileState.
    """
    rc, out, _ = await _run(
        "systemctl",
        "show",
        unit,
        "--no-pager",
        "--property=ActiveState,SubState,LoadState,UnitFileState",
    )
    data = {"ActiveState": "", "SubState": "", "LoadState": "", "UnitFileState": ""}
    if rc == 0:
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                if k in data:
                    data[k] = v
    return {
        "unit": unit,
        "active_state": data["ActiveState"],
        "sub_state": data["SubState"],
        "load_state": data["LoadState"],
        "unit_file_state": data["UnitFileState"],
    }


async def services_snapshot(service_dir: str) -> list:
    """
    Build a snapshot of services with statuses and descriptions.

    :param service_dir: Directory to scan.

    :returns: List of service dicts.
    """
    units = discover_units(service_dir)
    tasks = [get_unit_status(u) for u in units.keys()]
    results = await asyncio.gather(*tasks) if tasks else []
    for item in results:
        path = units.get(item["unit"])
        item["description"] = _read_description(path) if path else ""
    results.sort(key=lambda x: x["unit"])
    return results


async def is_allowed_unit(unit: str, service_dir: str) -> bool:
    """
    Check if a unit exists under service_dir.

    :param unit: Unit name.
    :param service_dir: Directory to scan.

    :returns: True if exists, False otherwise.
    """
    return unit in discover_units(service_dir)


async def start_unit(unit: str) -> tuple[int, str, str]:
    """
    Start a systemd service.

    :param unit: Unit name.

    :returns: (rc, stdout, stderr).
    """
    return await _run("systemctl", "start", unit)


async def stop_unit(unit: str) -> tuple[int, str, str]:
    """
    Stop a systemd service.

    :param unit: Unit name.

    :returns: (rc, stdout, stderr).
    """
    return await _run("systemctl", "stop", unit)


async def restart_unit(unit: str) -> tuple[int, str, str]:
    """
    Restart a systemd service.

    :param unit: Unit name.

    :returns: (rc, stdout, stderr).
    """
    return await _run("systemctl", "restart", unit)


async def journal_stream(unit: str, lines: int = 200):
    """
    Async generator streaming journalctl lines for a unit.

    :param unit: Unit name.
    :param lines: Number of backlog lines to include.

    :returns: Async iterator of single text lines.
    """
    proc = await asyncio.create_subprocess_exec(
        "journalctl",
        "-fu",
        unit,
        "-n",
        str(lines),
        "-o",
        "short-iso",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        while True:
            if proc.stdout.at_eof():
                break
            line = await proc.stdout.readline()
            if not line:
                await asyncio.sleep(0.05)
                continue
            yield line.decode(errors="replace").rstrip("\n")
    finally:
        if proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), 2.0)
            except Exception:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass


async def status_stream(service_dir: str):
    """
    Async generator that yields snapshots periodically.

    :param service_dir: Directory to scan.

    :returns: Async iterator of service lists.
    """
    while True:
        yield await services_snapshot(service_dir)
        await asyncio.sleep(1.5)
