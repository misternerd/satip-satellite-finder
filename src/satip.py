import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests

from util import create_logger

log = create_logger('SatIp')

@dataclass
class SatIpDeviceInfo:
    hostname: str
    manufacturer: str
    model: str
    model_name: str
    serial_number: str
    capability: str
    number_of_tuners: int

    def __str__(self):
        return (
            'Sat>IP Device('
            f'hostname={self.hostname}, '
            f'manufacturer={self.manufacturer}, '
            f'model={self.model}, '
            f'serialNumber={self.serial_number}, '
            f'capability={self.capability}, '
            f'numberOfTuners={self.number_of_tuners})'
        )


def fetch_satip_device_xml_descriptor(descriptor_url: str) -> SatIpDeviceInfo:
    log(f'Fetching SAT>IP device descriptor from {descriptor_url}')
    server_url = urlparse(descriptor_url)
    response = requests.get(descriptor_url)
    response.raise_for_status()
    raw_xml = response.text

    parsed_descriptor = ET.fromstring(raw_xml)
    namespaces = {
        'root': 'urn:schemas-upnp-org:device-1-0',
        'ses': 'urn:ses-com:satip',
    }
    device_manufacturer = parsed_descriptor.find('root:device/root:manufacturer', namespaces).text.strip()
    device_model = parsed_descriptor.find('root:device/root:modelName', namespaces).text.strip()
    serial_number = parsed_descriptor.find('root:device/root:serialNumber', namespaces).text.strip()
    satipcap = parsed_descriptor.find('root:device/ses:X_SATIPCAP', namespaces).text.strip().split('-')

    if len(satipcap) != 2 or not satipcap[1].isdigit():
        raise ValueError('Invalid SAT>IP capability, expecting two parts separated by a dash')

    if satipcap[0] not in ['DVBS2',  'DVBT', 'DVBT2', 'DVBC', 'DVBC2']:
        raise ValueError('Invalid SAT>IP capability type')

    return SatIpDeviceInfo(
        hostname=server_url.hostname,
        manufacturer=device_manufacturer,
        model=device_model,
        model_name=device_model,
        serial_number=serial_number,
        capability=satipcap[0],
        number_of_tuners=int(satipcap[1]),
    )


@dataclass
class SatIpChannel:
    frontend: Optional[int]
    """
    If a SAT>IP server provides multiple tuners, this is the frontend to use (1 based). Default is None.
    """
    src: int
    """
    The satellite position, if a SAT>IP server provides multiple positions via DISEQC (1 based). Default is 1.
    """
    frequency: float
    """
    Frequency expressed in MHz.
    """
    symbol_rate: int
    modulation_system: str
    """
    Either dvbs or dvbs2
    """
    modulation_type: str
    """
    Either qpsk or or 8psk. For dvbs modulation type only qpsk.
    """
    polarisation: str
    """
    h for horizontal, v for vertical.
    """
    fec: int
    """
    One of 12, 23, 34, 56, 78, 89, 35, 45, 910.
    """
    rolloff: float
    """
    One of 0.35, 0.25, 0.20.
    """
    pids: list[int]
    display_name: Optional[str] = None

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
        for pid in self.pids:
            if pid < 0 or pid > 8191:
                raise ValueError('Invalid pid')

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
