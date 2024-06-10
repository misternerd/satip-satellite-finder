import select
import socket
import time
from email.message import Message
import threading
from threading import Thread
from typing import Optional
from email.parser import BytesParser

import pycurl

RTSP_PREAMBLE = 'RTSP/1.0'
RTSP_METHODS = ['DESCRIBE', 'SETUP', 'PLAY', 'PAUSE', 'TEARDOWN', 'OPTIONS', 'ANNOUNCE', 'RECORD', 'GET_PARAMETER', 'SET_PARAMETER', 'REDIRECT']


class RtspResponse:
    _header_buffer = ''.encode('ascii')
    _package_buffer = ''.encode('ascii')
    status_code: int
    headers: Message
    data: str

    def append_header(self, data: bytes) -> None:
        self._header_buffer += data

    def append_data(self, data: bytes) -> None:
        self._package_buffer += data

    def finalize(self):
        raw_headers = self._header_buffer.decode('ascii')
        raw_data = self._package_buffer.decode('ascii')
        header_lines = raw_headers.split('\r\n')

        if len(header_lines) < 2:
            raise ValueError(f'Invalid RTSP response: Less than two lines: {header_lines}')

        self.status_code = RtspResponse.parse_status_line_return_code(header_lines.pop(0))
        self.headers = BytesParser().parsebytes(('\r\n'.join(header_lines)).encode('ascii'))
        self.data = raw_data

    @classmethod
    def parse_status_line_return_code(self, status_line: str) -> int:
        if not status_line.startswith('RTSP/1.0 '):
            raise ValueError('Invalid RTSP response')

        status_line = status_line[len('RTSP/1.0 '):]
        status_split_by_space = status_line.split(' ')

        # Check that first element is only digits
        if not status_split_by_space[0].isdigit():
            raise ValueError(f'Invalid RTSP response, expecting status code, got {status_split_by_space[0]}')

        return int(status_split_by_space[0])

    def __str__(self):
        return f'RtspResponse(status_code={self.status_code}, headers={self.headers}, data={self.data})'


class RtspConnection(object):
    _curl = pycurl.Curl()
    base_uri: str
    _lock = threading.Lock()

    def __init__(self, server_host: str, server_port: int) -> None:
        self.base_uri = f'rtsp://{server_host}:{server_port}/'

    def perform_rtsp_request(self, url: str, method: int, extra_curl_opts: dict[int, any] = None) -> RtspResponse:
        with self._lock:
            rtsp_response = RtspResponse()
            self._curl.setopt(pycurl.URL, url)
            self._curl.setopt(pycurl.OPT_RTSP_REQUEST, method)
            self._curl.setopt(pycurl.WRITEFUNCTION, rtsp_response.append_data)
            self._curl.setopt(pycurl.HEADERFUNCTION, rtsp_response.append_header)

            if extra_curl_opts is not None:
                for key, value in extra_curl_opts.items():
                    self._curl.setopt(key, value)

            self._curl.perform()
            rtsp_response.finalize()
            return rtsp_response

    def close(self):
        self._curl.close()


class RtpConnection(object):
    _rtp_socket: socket.socket
    _rtcp_socket: socket.socket
    _received_thread: Thread
    _received_thread_running: bool = False

    def __init__(self, client_rtp_port: int, client_rtcp_port: int) -> None:
        self._rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rtp_socket.bind(('0.0.0.0', client_rtp_port))
        self._rtcp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rtcp_socket.bind(('0.0.0.0', client_rtcp_port))
        self._received_thread = threading.Thread(target=self._packet_receiver_handler)
        self._received_thread.start()
        self._received_thread_running = True
        print(f'RtpConnection running, listening on {client_rtp_port}/rtp and {client_rtcp_port}/rtcp')

    def _packet_receiver_handler(self):
        socket_list = [self._rtp_socket, self._rtcp_socket]
        while self._received_thread_running:
            read_sockets, _, _ = select.select(socket_list, [], [])
            for sock in read_sockets:
                if sock == self._rtp_socket:
                    packet = sock.recv(4096)
                    print(f'RTP packet={packet}')
                elif sock == self._rtcp_socket:
                    packet = sock.recv(4096)
                    print(f'RTCP packet={packet}')

    def close(self):
        self._received_thread_running = False
        self._received_thread.join()


class RtspStream(object):
    _connection: RtspConnection
    _session_id: str
    _client_rtp_port: int
    _client_rtcp_port: int
    _stream_id: Optional[int]
    _rtcp_socket: Optional[socket.socket] = None
    _rtp_socket: Optional[socket.socket] = None

    def __init__(self, connection: RtspConnection, session_id: str, stream_id: int, client_rtp_port: int, client_rtcp_port: int) -> None:
        self._connection = connection
        self._session_id = session_id
        self._stream_id = stream_id
        self._client_rtp_port = client_rtp_port
        self._client_rtcp_port = client_rtcp_port

    def play(self, pids: list[int]) -> Optional[RtpConnection]:
        rtp_connection = RtpConnection(self._client_rtp_port, self._client_rtcp_port)
        pids_str = ','.join(map(str, pids))
        url = (
            f'{self._connection.base_uri}'
            f'stream={self._stream_id}'
            f'?addpids={pids_str}'
        )
        curl_extra_opts = {pycurl.OPT_RTSP_STREAM_URI: url}
        rtsp_response = self._connection.perform_rtsp_request(url, pycurl.RTSPREQ_PLAY, curl_extra_opts)

        if rtsp_response.status_code != 200:
            print(f'Failed to play stream={self._stream_id}, got response={rtsp_response}')
            rtp_connection.close()
            return None

        return rtp_connection

    def teardown(self) -> bool:
        url = (
            f'{self._connection.base_uri}'
            f'stream={self._stream_id}'
        )
        rtsp_response = self._connection.perform_rtsp_request(url, pycurl.RTSPREQ_TEARDOWN)

        if rtsp_response.status_code != 200:
            print(f'Failed to teardown stream={self._stream_id}, got response={rtsp_response}')
            return False

        return True


class RtspClient(object):
    _connection: RtspConnection
    _tuner_count: int
    _options_thread: Thread
    _running = True

    def __init__(self, server_ip: str, server_port: int, tuner_count: int) -> None:
        self._connection = RtspConnection(server_ip, server_port)
        self._tuner_count = tuner_count

    def close(self):
        self._running = False
        if self._options_thread and self._options_thread.is_alive():
            self._options_thread.join()
        self._connection.close()

    def _start_options_thread(self, timeout):
        def send_options_request():
            url = f'{self._connection.base_uri}'
            rtsp_response = self._connection.perform_rtsp_request(url, pycurl.RTSPREQ_OPTIONS)

            if rtsp_response.status_code != 200:
                print(f'Options request failed, got response={rtsp_response}')

        def thread_wrapper():
            while self._running:
                time.sleep(timeout - 2)
                send_options_request()

        self._running = True
        self._options_thread = threading.Thread(target=thread_wrapper)
        self._options_thread.start()

    def setup_stream(self, client_rtp_port: int, client_rtcp_port: int, tuner_index: int, frequency: float,
                     polarisation: str, msys: str, symbol_rate: int, fec: int, pids: list[int]) -> Optional[
        RtspStream]:
        if polarisation not in ['v', 'h']:
            raise ValueError(f'Invalid polarisation: {polarisation}')

        if msys not in ['dvbs', 'dvbs2']:
            raise ValueError(f'Invalid msys: {msys}')

        pid_str = ','.join(map(str, pids))
        url = (f'{self._connection.base_uri}?'
               f'src={tuner_index}&fe=1'
               f'&freq={frequency}'
               f'&pol={polarisation}'
               f'&msys={msys}'
               f'&sr={symbol_rate}'
               f'&fec={fec}'
               f'&pids={pid_str}'
               )
        transport = f'RTP/AVP;unicast;client_port={client_rtp_port}-{client_rtcp_port}'
        extra_curl_opts = {pycurl.OPT_RTSP_TRANSPORT: transport}
        rtsp_response = self._connection.perform_rtsp_request(url, pycurl.RTSPREQ_SETUP, extra_curl_opts)

        if rtsp_response.status_code != 200:
            print(f'Failed to setup stream for url={url}, got response={rtsp_response}')
            return None

        stream_id = int(rtsp_response.headers['com.ses.streamID'])
        session_id,timeout = rtsp_response.headers['Session'].split(';')
        timeout = int(timeout.replace('timeout=', '')) or 60
        result = RtspStream(self._connection, session_id, stream_id, client_rtp_port, client_rtcp_port)

        self._start_options_thread(timeout)
        print(f'Setup stream with stream_id={stream_id}, session_id={session_id}')

        return result
