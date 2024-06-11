import select
import socket
import sys
from threading import Thread
from typing import Optional


class RtpConnection(object):
    _rtp_socket: socket.socket
    _rtcp_socket: socket.socket
    _received_thread: Thread
    _received_thread_running: bool = True
    _rtp_callback: Optional[callable] = None
    _rtcp_callback: Optional[callable] = None

    def __init__(self, client_rtp_port: int, client_rtcp_port: int) -> None:
        self._rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rtp_socket.bind(('0.0.0.0', client_rtp_port))
        self._rtcp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rtcp_socket.bind(('0.0.0.0', client_rtcp_port))
        self._received_thread = Thread(target=self._packet_receiver_handler)
        self._received_thread.start()
        print(f'RtpConnection running, listening on {client_rtp_port}/rtp and {client_rtcp_port}/rtcp', file=sys.stderr)

    def _packet_receiver_handler(self):
        socket_list = [self._rtp_socket, self._rtcp_socket]
        while self._received_thread_running:
            read_sockets, _, _ = select.select(socket_list, [], [], 1000)
            for sock in read_sockets:
                if sock == self._rtp_socket:
                    packet = sock.recv(4096)
                    if packet and self._rtp_callback:
                        self._rtp_callback(packet)
                elif sock == self._rtcp_socket:
                    packet = sock.recv(4096)
                    if packet and self._rtcp_callback:
                        self._rtcp_callback(packet)

    def close(self):
        print(
            f'Closing RtpConnection on ports {self._rtp_socket.getsockname()[1]}/rtp and {self._rtcp_socket.getsockname()[1]}/rtcp',
            file=sys.stderr)
        self._received_thread_running = False
        self._rtp_socket.close()
        self._rtcp_socket.close()
        self._received_thread.join()
        print(f'RtpConnection closed', file=sys.stderr)

    def register_rtp_packet_received_callback(self, callback: callable):
        self._rtp_callback = callback

    def register_rtcp_packet_received_callback(self, callback: callable):
        self._rtcp_callback = callback
