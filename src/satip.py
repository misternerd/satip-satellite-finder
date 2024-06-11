from dataclasses import dataclass
from typing import Optional


@dataclass
class SatipChannel:
    frontend: Optional[int]
    src: int
    frequency: float
    symbol_rate: int
    modulation_system: str
    modulation_type: str
    polarisation: str
    fec: int
    rolloff: float
    pids: list[int]

    def __post_init__(self):
        if self.frontend is not None and (self.frontend < 1 or self.frontend > 65535):
            raise ValueError('Invalid frontend')
        if self.src < 1 or self.src > 255:
            raise ValueError('Invalid src')
        if self.polarisation not in ['v', 'h']:
            raise ValueError('Invalid polarity')
        if self.modulation_system not in ['dvbs', 'dvbs2']:
            raise ValueError('Invalid modulation_system')
        if self.modulation_type not in ['qpsk', '8psk']:
            raise ValueError('Invalid modulation_type')
        if self.fec not in [12, 23, 34, 56, 78, 89, 35, 45, 910]:
            raise ValueError('Invalid fec')
        if self.rolloff not in [0.20, 0.25, 0.35]:
            raise ValueError('Invalid rolloff')

    def to_stream_uri_params(self):
        result = (
            f'?src={self.src}'
            f'&freq={self.frequency}'
            f'&sr={self.symbol_rate}'
            f'&msys={self.modulation_system}'
            f'&mtype={self.modulation_type}'
            f'&pol={self.polarisation}'
            f'&fec={self.fec}'
            f'&ro={self.rolloff}'
            f'&pids={",".join(map(str, self.pids))}'
        )

        if self.frontend is not None:
            result += f'&fe={self.frontend}'

        return result
