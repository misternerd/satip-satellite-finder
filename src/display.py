from dataclasses import dataclass

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TaskID, TaskProgressColumn


@dataclass
class TunerData:
    level_progress: Progress
    level_task: TaskID
    snr_progress: Progress
    snr_task: TaskID


class Display:
    _tuners: list[TunerData] = []
    _console = Console()

    def __init__(self, number_of_tuners: int):
        rows = []
        self._layout = Layout(size=number_of_tuners * 2)
        for i in range(number_of_tuners):
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
            panel = Panel(row_layout, title=f'Tuner {i + 1}', border_style='blue')
            rows.append(panel)
            self._tuners.append(TunerData(level_progress, level_task, snr_progress, snr_task))
        self._layout.split_column(*rows)
        self._live = Live(self._layout, console=self._console, refresh_per_second=4)
        self._live.start(True)

    def update_tuner(self, tuner_index: int, level: int, snr: int):
        if tuner_index >= len(self._tuners):
            raise IndexError(f'Invalid tuner index {tuner_index}')

        tuner_data = self._tuners[tuner_index]
        tuner_data.level_progress.update(tuner_data.level_task, completed=level)
        tuner_data.snr_progress.update(tuner_data.snr_task, completed=snr)

    def close(self):
        self._live.stop()
        self._console.clear()
