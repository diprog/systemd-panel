"""
Low-level systemd interaction helpers.
"""
import asyncio
from pathlib import Path

from models import ServiceStatus

_UNIT_DIR = Path("/etc/systemd/system")


class ServiceManager:
    """
    Encapsulates all systemd interactions.
    """

    async def list_services(self) -> list[ServiceStatus]:
        """
        Returns a list of ServiceStatus objects for every *.service file
        found in /etc/systemd/system and refreshes their runtime status.
        """
        files = _UNIT_DIR.glob("*.service")
        names = [f.stem for f in files]

        tasks = [self._status(name) for name in names]
        return [s for s in await asyncio.gather(*tasks) if s]

    async def action(self, unit: str, act: str) -> None:
        """
        Performs systemctl <act> on the given unit.

        :param unit: Name of the systemd unit.
        :param act: start | stop | restart.
        """
        proc = await asyncio.create_subprocess_exec(
            "systemctl", act, unit,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

    async def _status(self, unit: str) -> ServiceStatus | None:
        """
        Queries systemctl show for a single unit.

        :param unit: Unit name.
        :returns: ServiceStatus or None when the unit does not exist.
        """
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "show",
            unit,
            "--property=ActiveState,SubState",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None

        data = stdout.decode()
        active = "ActiveState=active" in data
        sub = next(
            (line.split("=", 1)[1] for line in data.splitlines() if "SubState=" in line),
            "unknown",
        )
        return ServiceStatus(name=unit, active=active, sub=sub)

    async def tail_logs(self, unit: str):
        """
        Starts journalctl -fu <unit> and returns the asyncio process.

        :param unit: Unit whose logs to tail.
        :returns: asyncio.subprocess.Process.
        """
        return await asyncio.create_subprocess_exec(
            "journalctl",
            "-fu",
            unit,
            "--no-pager",
            "--output=short",
            stdout=asyncio.subprocess.PIPE,
        )