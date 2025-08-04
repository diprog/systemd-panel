import asyncio
import json
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

    The scan is non-recursive and ignores symlinks and subdirectories.

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
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
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


async def journal_stream(unit: str, lines: int = 200, output: str = "short-iso"):
    """
    Async generator streaming journalctl lines for a unit.

    :param unit: Unit name.
    :param lines: Number of backlog lines to include.
    :param output: "short-iso" to keep systemd preface or "cat" to emit only MESSAGE.

    :returns: Async iterator of single text lines.
    """
    if output == "cat":
        # Жёстко берём только MESSAGE через JSON, чтобы не получить префиксы формата.
        proc = await asyncio.create_subprocess_exec(
            "journalctl",
            "-fu",
            unit,
            "-n",
            str(lines),
            "-o",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                try:
                    obj = json.loads(raw.decode(errors="replace"))
                    msg = obj.get("MESSAGE", "")
                except Exception:
                    # Фоллбэк на случай странной строки — почти не должен срабатывать
                    msg = raw.decode(errors="replace")
                if msg:
                    yield msg.rstrip("\n")
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
        return

    # Обычный путь: оставить короткую «шапку» от journalctl
    fmt = "short-iso"
    proc = await asyncio.create_subprocess_exec(
        "journalctl",
        "-fu",
        unit,
        "-n",
        str(lines),
        "-o",
        fmt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
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



# ---------- Realtime status pub/sub ----------

class StatusBus:
    """
    In-process pub/sub that broadcasts service snapshots.

    Produces snapshots on a timer and immediately when triggered.

    :param service_dir: Directory to scan for units.
    :param interval: Fallback tick interval (seconds).
    """

    def __init__(self, service_dir: str, interval: float = 1.5):
        self._dir = service_dir
        self._interval = interval
        self._subs = set()
        self._poke = asyncio.Event()
        self._task = None

    async def start(self) -> None:
        """
        Start the background producer task if not running.

        :returns: None.
        """
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """
        Stop the background task.

        :returns: None.
        """
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None

    async def _run(self) -> None:
        """
        Background loop that emits snapshots on tick or trigger.

        :returns: None.
        """
        while True:
            try:
                await asyncio.wait_for(self._poke.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass
            self._poke.clear()
            snapshot = await services_snapshot(self._dir)
            await self._broadcast(snapshot)

    async def _broadcast(self, snapshot: list) -> None:
        """
        Send a snapshot to all subscribers (drop oldest if slow).

        :param snapshot: Snapshot list.

        :returns: None.
        """
        dead = []
        for q in list(self._subs):
            try:
                if q.full():
                    q.get_nowait()
                q.put_nowait(snapshot)
            except Exception:
                dead.append(q)
        for q in dead:
            self._subs.discard(q)

    def subscribe(self) -> asyncio.Queue:
        """
        Subscribe to snapshots.

        :returns: Queue that receives snapshot lists.
        """
        q = asyncio.Queue(maxsize=1)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """
        Unsubscribe a queue.

        :param q: Queue to remove.

        :returns: None.
        """
        self._subs.discard(q)

    def trigger(self) -> None:
        """
        Request an immediate snapshot broadcast.

        :returns: None.
        """
        self._poke.set()


_BUSES = {}  # service_dir -> StatusBus


def _get_bus(service_dir: str) -> StatusBus:
    """
    Return a singleton StatusBus per service_dir, starting it if needed.

    :param service_dir: Directory to scan.

    :returns: StatusBus instance.
    """
    bus = _BUSES.get(service_dir)
    if not bus:
        bus = StatusBus(service_dir)
        _BUSES[service_dir] = bus
        # Safe to schedule when called from an async request handler.
        asyncio.create_task(bus.start())
    return bus


def trigger_status_refresh(service_dir: str) -> None:
    """
    Trigger an immediate status refresh broadcast.

    :param service_dir: Directory to scan.

    :returns: None.
    """
    _get_bus(service_dir).trigger()


async def status_stream(service_dir: str):
    """
    Async generator that yields snapshots as they are produced.

    Includes an initial snapshot, then pushes on timer or trigger.

    :param service_dir: Directory to scan.

    :returns: Async iterator of service lists.
    """
    bus = _get_bus(service_dir)
    q = bus.subscribe()
    try:
        yield await services_snapshot(service_dir)
        while True:
            snapshot = await q.get()
            yield snapshot
    finally:
        bus.unsubscribe(q)
