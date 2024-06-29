import os
import select
import socket
from threading import Event, Thread
from typing import Optional

from util import (create_logger)

log = create_logger('RTP')


class RtpConnection(object):
    _rtp_socket: socket.socket
    _rtcp_socket: socket.socket
    _receiver_thread: Thread
    _receiver_thread_stop_event: Event
    _receiver_thread_stop_pipe: tuple[int, int]
    _rtp_callback: Optional[callable]
    _rtcp_callback: Optional[callable]

    def __init__(self, client_rtp_port: int, client_rtcp_port: int) -> None:
        self._receiver_thread_stop_event = Event()
        self._receiver_thread_stop_pipe = os.pipe()
        self._rtp_callback = None
        self._rtcp_callback = None
        self._rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rtp_socket.bind(('0.0.0.0', client_rtp_port))
        self._rtcp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rtcp_socket.bind(('0.0.0.0', client_rtcp_port))
        self._receiver_thread = Thread(target=self._packet_receiver_handler)
        self._receiver_thread.start()
        log(f'Connection running, listening on {client_rtp_port}/rtp and {client_rtcp_port}/rtcp')

    def _packet_receiver_handler(self):
        socket_list = [self._rtp_socket, self._rtcp_socket, self._receiver_thread_stop_pipe[0]]
        while not self._receiver_thread_stop_event.is_set():
            try:
                read_sockets, _, _ = select.select(socket_list, [], [])
                for sock in read_sockets:
                    if sock == self._rtp_socket:
                        packet = sock.recv(4096)
                        if packet and self._rtp_callback:
                            try:
                                self._rtp_callback(packet)
                            except Exception as e:
                                log('Error in rtp callback: {e}')
                    elif sock == self._rtcp_socket:
                        packet = sock.recv(4096)
                        if packet and self._rtcp_callback:
                            try:
                                self._rtcp_callback(packet)
                            except Exception as e:
                                log('Error in rtcp callback: {e}')
            except Exception as e:
                log(f'Error receiving packet: {e}')
                break

        log(f'Connection packet receiver thread exited')

    def close(self):
        log(f'Closing connection on {self._rtp_socket.getsockname()[1]}/rtp, {self._rtcp_socket.getsockname()[1]}/rtcp')
        self._receiver_thread_stop_event.set()
        os.write(self._receiver_thread_stop_pipe[1], b'0')
        self._rtp_socket.close()
        self._rtcp_socket.close()
        self._receiver_thread.join()
        log('RtpConnection closed')

    def register_rtp_packet_received_callback(self, callback: callable):
        self._rtp_callback = callback

    def register_rtcp_packet_received_callback(self, callback: callable):
        self._rtcp_callback = callback
