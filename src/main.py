#!/usr/bin/env python3
import argparse
import contextlib
import signal
from typing import Optional

from display import Display
from rtcp import get_first_rtcp_app_packet_from_rtcp_data
from rtp import RtpConnection
from rtsp import RtspClient, RtspStream
from satip import SatIpChannel, fetch_satip_device_xml_descriptor
from util import create_logger

RTSP_PORT = 554

log = create_logger('Main')


def parse_args() -> (str, list[SatIpChannel]):
    parser = argparse.ArgumentParser(description='A sat finder for SAT>IP servers')
    parser.add_argument(
        '-s',
        '--server-descriptor-url',
        type=str,
        help="The full URL to the SAT>IP server's XML descriptor",
        required=True
    )
    parser.add_argument(
        '-t',
        '--tune',
        action='append',
        help='The service to tune to in the format '
             'frequency,polarisation,modulation_system,symbol_rate,fec[,name] '
             '(e.g. 10714.25,h,dvbs,22000,56,SomeName). The name is optional and is used for display purposes. '
             'Can be specified once per tuner available.',
        required=True
    )

    args = parser.parse_args()

    if len(args.tune) == 0:
        log('At least one --tune must be specified')
        exit(1)

    channels = []

    for i, tune in enumerate(args.tune):
        parts = tune.split(',')
        if len(parts) < 5 or len(parts) > 6:
            log(f'Invalid tune format: {tune}')
            exit(1)

        modulation_system = parts[2]
        try:
            channels.append(SatIpChannel(
                frontend=i + 1,
                src=1,
                frequency=(float(parts[0])),
                symbol_rate=(int(parts[3])),
                modulation_system=modulation_system,
                modulation_type="8psk" if modulation_system == "dvbs2" else "qpsk",
                polarisation=(parts[1]),
                fec=(int(parts[4])),
                rolloff=0.35,
                pids=[0],
                display_name=(parts[5].strip() if len(parts) == 6 else None)
            ))
        except ValueError:
            log(f'Invalid tune format: {tune}')
            exit(1)

    return args.server_descriptor_url, channels


def close_everything(
        display: Optional[Display],
        rtsp_clients: list[Optional[RtspClient]],
        rtsp_streams: list[Optional[RtspStream]],
        rtp_connections: list[Optional[RtpConnection]]):
    if display:
        with contextlib.suppress(Exception):
            display.close()

    for s in rtsp_streams:
        if s:
            with contextlib.suppress(Exception):
                s.teardown()

    for r in rtp_connections:
        if r:
            with contextlib.suppress(Exception):
                r.close()

    for c in rtsp_clients:
        if c:
            with contextlib.suppress(Exception):
                c.close()


def main():
    arg_descriptor_url, arg_channels = parse_args()
    device_info = fetch_satip_device_xml_descriptor(arg_descriptor_url)

    if device_info.number_of_tuners < len(arg_channels):
        log(f'Not enough tuners available on the SAT>IP server. '
            f'({device_info.number_of_tuners} vs {len(arg_channels)})')
        exit(1)

    log(f'Connecting to {device_info.hostname} '
        f'({device_info.manufacturer} {device_info.model_name}, {device_info.number_of_tuners} tuners)')

    display_names = [
        f'{c.frequency}/{c.polarisation}|{c.display_name}' if c.display_name else f'{c.frequency}/{c.polarisation}'
        for c in arg_channels]
    display = Display(display_names)
    rtsp_clients = []
    rtsp_streams = []
    rtp_connections = []

    def signal_handler(signal, frame):
        # Display has to be closed first, so we can log to stderr again
        display.close()
        log(f'Got signal {signal} => exiting')
        close_everything(None, rtsp_clients, rtsp_streams, rtp_connections)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    for tuner_idx, channel in enumerate(arg_channels):
        rtsp_client = RtspClient(device_info.hostname, RTSP_PORT)
        rtsp_clients.append(rtsp_client)
        client_rtp_port = 57000 + (tuner_idx * 2)
        try:
            rtsp_stream = rtsp_client.setup_stream(channel, client_rtp_port, client_rtp_port + 1)
            rtsp_streams.append(rtsp_stream)
        except Exception as e:
            log(f'Failed to setup stream {tuner_idx}: {e}')
            close_everything(display, rtsp_clients, rtsp_streams, rtp_connections)
            exit(1)

        try:
            rtp_connection = rtsp_stream.play([1])
            rtp_connections.append(rtp_connection)
        except Exception as e:
            log(f'Failed to play stream: {e}')
            close_everything(display, rtsp_clients, rtsp_streams, rtp_connections)
            exit(1)

        def show_signal_and_quality(packet_data):
            app_packet = get_first_rtcp_app_packet_from_rtcp_data(packet_data)
            level = int((app_packet.signal_level / 255) * 100)
            snr = int((app_packet.quality / 15) * 100)
            display.update_tuner(tuner_idx, level, snr)

        rtp_connection.register_rtcp_packet_received_callback(show_signal_and_quality)

    display.start()


if __name__ == '__main__':
    main()
