from dataclasses import dataclass
from threading import Lock

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TaskID, TaskProgressColumn

from rtcp import get_first_rtcp_app_packet_from_rtcp_data
from satip import SatIpChannel
from util import create_logger

BORDER_COLORS = ['bright_red', 'bright_blue', 'bright_magenta', 'bright_cyan', 'bright_green', 'bright_yellow']

log = create_logger('Display')


@dataclass
class TunerData:
    channel: SatIpChannel
    display_name: str
    level_progress: Progress
    level_task: TaskID
    quality_progress: Progress
    quality_task: TaskID


class Display:
    _lock: Lock
    _tuners: list[TunerData]
    _console: Console
    _layout: Layout
    _live: Live

    def __init__(self):
        self._lock = Lock()
        self._tuners: list[TunerData] = []
        self._console = Console()

    def register_tuner_return_update_callback(self, channel: SatIpChannel):
        if self._is_started():
            raise RuntimeError('Display already started')

        display_name = f'{channel.frequency}/{channel.polarisation}'

        if channel.display_name:
            display_name += f'|{channel.display_name}'

        level_progress = Progress(TextColumn("Signal"),
                                  BarColumn(),
                                  TaskProgressColumn(),
                                  disable=True,
                                  expand=False,
                                  )
        level_task = level_progress.add_task("Signal", total=100)
        quality_progress = Progress(TextColumn("Quality"),
                                    BarColumn(),
                                    TaskProgressColumn(),
                                    disable=True,
                                    expand=False,
                                    )
        quality_task = quality_progress.add_task("Quality", total=100)
        self._tuners.append(TunerData(
            channel=channel,
            display_name=display_name,
            level_progress=level_progress,
            level_task=level_task,
            quality_progress=quality_progress,
            quality_task=quality_task))

        def update_tuner_data(packet_data: bytes):
            try:
                # this can happen during initialization and shutdown
                if not self._is_started():
                    return

                app_packet = get_first_rtcp_app_packet_from_rtcp_data(packet_data)
                level = int((app_packet.signal_level / 255) * 100)
                quality = int((app_packet.quality / 15) * 100)

                with self._lock:
                    if not self._live.is_started:
                        return

                    level_progress.update(level_task, completed=level)
                    quality_progress.update(quality_task, completed=quality)
            except Exception as e:
                log(f'Error displaying tuner update packet: {e}')

        return update_tuner_data

    def start(self):
        if self._is_started():
            raise RuntimeError('Display already started')

        rows = []
        self._layout = Layout(size=len(self._tuners) * 2)
        for i, tuner_data in enumerate(self._tuners):
            border_color = BORDER_COLORS[i % len(BORDER_COLORS)]
            row_layout = Layout(name=f'Tuner {i + 1}', size=2)
            row_layout.split_row(tuner_data.level_progress, tuner_data.quality_progress)
            panel = Panel(row_layout, title=f'Tuner {i + 1} ({tuner_data.display_name})', border_style=border_color)
            rows.append(panel)
        self._layout.split_column(*rows)
        self._live = Live(self._layout, console=self._console, refresh_per_second=4)
        self._live.start(True)

    def close(self):
        if self._is_started():
            self._live.stop()
            self._console.clear()

    def _is_started(self):
        return getattr(self, '_live', False) and self._live.is_started
