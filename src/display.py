from dataclasses import dataclass

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TaskID, TaskProgressColumn

from threading import Lock


@dataclass
class TunerData:
    level_progress: Progress
    level_task: TaskID
    snr_progress: Progress
    snr_task: TaskID


class Display:
    _lock = Lock()
    _tuners: list[TunerData] = []
    _console = Console()

    def __init__(self, tuner_display_names: list[str]):
        rows = []
        self._layout = Layout(size=len(tuner_display_names) * 2)
        for i, display_name in enumerate(tuner_display_names):
            level_progress = Progress(TextColumn("Signal"),
                                      BarColumn(),
                                      TaskProgressColumn(),
                                      disable=True,
                                      expand=False,
                                      )
            level_task = level_progress.add_task("Signal", total=100)
            snr_progress = Progress(TextColumn("SNR"),
                                    BarColumn(),
                                    TaskProgressColumn(),
                                    disable=True,
                                    expand=False,
                                    )
            snr_task = snr_progress.add_task("SNR", total=100)
            row_layout = Layout(name=f'Tuner {i + 1}', size=2)
            row_layout.split_row(level_progress, snr_progress)
            panel = Panel(row_layout, title=f'Tuner {i + 1} ({display_name})', border_style='blue')
            rows.append(panel)
            self._tuners.append(TunerData(level_progress, level_task, snr_progress, snr_task))
        self._layout.split_column(*rows)
        self._live = Live(self._layout, console=self._console, refresh_per_second=4)

    def start(self):
        self._live.start(True)

    def close(self):
        if self._live.is_started:
            self._live.stop()
            self._console.clear()

    def update_tuner(self, tuner_index: int, level: int, snr: int):
        with self._lock:
            if tuner_index >= len(self._tuners):
                raise IndexError(f'Invalid tuner index {tuner_index}')

            # this can happen during shutdown
            if not self._live.is_started:
                return

            tuner_data = self._tuners[tuner_index]
            tuner_data.level_progress.update(tuner_data.level_task, completed=level)
            tuner_data.snr_progress.update(tuner_data.snr_task, completed=snr)
