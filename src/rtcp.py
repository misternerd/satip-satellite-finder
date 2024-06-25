import base64
from typing import Optional


class RtcpPacketAppSatIp:
    """
    This is a custom APP RTCP packet that the SAT>IP server sends to the client. The format is as follows:
    1. A 4-byte name field, set to `SES1`
    2. A 2-byte identifier field, set to `0000`
    3. A 2-byte string length field specifying the length of the string that follows
    4. A variable length string field padded with null bytes to the next 32-bit boundary. Format is
       ver=<major>.<minor>;src=<srcID>;tuner=<feID>,<level>,<lock>,<quality>,<frequency>,<polarisation>,
       <system>,<type>,<pilots>,<roll_off>,<symbol_rate>,<fec_inner>;pids=<pid0>,...,<pidn>
    """
    name: str
    source: int
    frontend_id: int
    signal_level: int
    """
    Numerical value between 0 and 255
    An incoming L-band satellite signal of
    -25dBm corresponds to 224
    -65dBm corresponds to 32
    No signal corresponds to 0
    """
    lock: bool
    quality: int
    """
    Numerical value between 0 and 15
    Lowest value corresponds to highest error rate
    The value 15 shall correspond to
    -a BER lower than 2x10-4 after Viterbi for DVB-S
    -a PER lower than 10-7 for DVB-S2
    """
    frequency: float
    polarisation: str
    system: str
    type: str
    pilots: bool
    roll_off: float
    symbol_rate: int
    fec_inner: int
    pids: list[int]

    def __init__(self, specific_data: bytes):
        self.name = specific_data[:4].decode('ascii')
        identifier = int.from_bytes(specific_data[4:6], byteorder='big')
        string_length = int.from_bytes(specific_data[6:8], byteorder='big')
        application_data = specific_data[8:].decode('utf-8').rstrip('\0')

        if identifier != 0:
            raise ValueError(f'Invalid SatIp APP packet, expected identifier=0000, got identifier={identifier}')

        if len(application_data) != string_length:
            raise ValueError(f'Invalid SatIp APP packet, expected len={string_length}, got len={len(application_data)}')

        for entry in application_data.split(';'):
            if entry.startswith('ver='):
                self.version = entry.replace('ver=', '')
                continue
            if entry.startswith('src='):
                self.source = int(entry.replace('src=', ''))
                continue
            if entry.startswith('tuner='):
                tuner_data = entry.replace('tuner=', '').strip().split(',')

                if len(tuner_data) != 12:
                    raise ValueError(f'Invalid SatIp APP packet, got tuner len={len(tuner_data)} != 12')

                self.frontend_id = int(tuner_data[0])
                self.signal_level = int(tuner_data[1])
                self.lock = True if tuner_data[2] == 1 else False
                self.quality = int(tuner_data[3])
                self.frequency = float(tuner_data[4])
                self.polarisation = tuner_data[5]
                self.system = tuner_data[6]  # dvbs, dvbs2
                self.type = tuner_data[7]  # qpsk, 8psk
                self.pilots = True if tuner_data[8].lower() == 'on' else False
                self.roll_off = float(tuner_data[9])
                self.symbol_rate = int(tuner_data[10])
                self.fec_inner = int(tuner_data[11])

                if self.signal_level < 0 or self.signal_level > 255:
                    raise ValueError(f'Invalid SatIp APP packet, expected signal_level=0-255, got={self.signal_level}')

                if self.quality < 0 or self.quality > 15:
                    raise ValueError(f'Invalid SatIp APP packet, expected quality=0-15, got={self.quality}')

                continue
            if entry.startswith('pids='):
                self.pids = [int(x) for x in entry.replace('pids=', '').split(',')]
                continue


def get_first_rtcp_app_packet_from_rtcp_data(packet: bytes) -> Optional[RtcpPacketAppSatIp]:
    """
    Takes received RTCP data and returns the first APP packet found, discarding all other packet types encountered.
    """
    index = 0
    packet_length = len(packet)

    while index + 4 < packet_length:
        packet_start = index
        byte_0 = packet[index]
        version = (byte_0 & 0b11000000) >> 6
        # ignoring unused: padding = (byte_0 & 0b00100000) >> 5
        reception_report_count = (byte_0 & 0b00011111)
        index += 1
        packet_type = packet[index]
        index += 1
        length = int.from_bytes(packet[index:index+2], byteorder='big') * 4 + 4
        index += 2
        # ignoring unused: ssrc = int.from_bytes(packet[index:index+4], byteorder='big')
        index += 4

        if version != 2:
            raise ValueError(f'Invalid RTCP packet, expected version=2, got {version}')

        if reception_report_count < 0:
            raise ValueError(f'Invalid RTCP packet, expected reception_report_count >= 0, got {reception_report_count}')

        if packet_start + length > packet_length:
            raise ValueError(f'Invalid RTCP packet, expected length={length}, got {packet_length}')

        specific_data = packet[index:index+length-4]
        index = packet_start + length

        # we're only interested in the APP packets, as they contain the signal & quality data
        if packet_type != 204:
            continue

        return RtcpPacketAppSatIp(specific_data)
