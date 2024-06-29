from email.message import Message
from email.parser import BytesParser
from threading import Condition, Event, Lock, Thread
from typing import Optional

import pycurl

from rtp import RtpConnection
from satip import SatIpChannel
from util import create_logger

RTSP_PREAMBLE = 'RTSP/1.0'
RTSP_METHODS = ['DESCRIBE', 'SETUP', 'PLAY', 'PAUSE', 'TEARDOWN', 'OPTIONS', 'ANNOUNCE', 'RECORD', 'GET_PARAMETER',
                'SET_PARAMETER', 'REDIRECT']

log = create_logger('RTSP')

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
        data = self._package_buffer.decode('ascii')
        header_lines = raw_headers.split('\r\n')

        if len(header_lines) < 2:
            raise ValueError(f'Invalid RTSP response: Less than two lines: {header_lines}')

        self.status_code = RtspResponse.parse_status_line_return_code(header_lines.pop(0))
        self.headers = BytesParser().parsebytes(('\r\n'.join(header_lines)).encode('ascii'))
        self.data = data

    @classmethod
    def parse_status_line_return_code(self, status_line: str) -> int:
        if not status_line.startswith('RTSP/1.0 '):
            raise ValueError('Invalid RTSP response')

        status_line = status_line[len('RTSP/1.0 '):]
        status_split_by_space = status_line.split(' ')

        if not status_split_by_space[0].isdigit():
            raise ValueError(f'Invalid RTSP response, expecting status code, got {status_split_by_space[0]}')

        return int(status_split_by_space[0])

    def __str__(self):
        header_str = self.headers.__str__().replace('\n', ' ').strip()
        return f'RtspResponse(status_code={self.status_code}, headers={header_str}, data={self.data})'


class RtspConnection(object):
    _curl = pycurl.Curl()
    _lock = Lock()
    base_uri: str

    def __init__(self, server_host: str, server_port: int) -> None:
        port_or_empty = f':{server_port}' if server_port != 554 else ''
        self.base_uri = f'rtsp://{server_host}{port_or_empty}/'

    def perform_rtsp_request(self, url_part: str, method: int, extra_curl_opts: dict[int, any] = None) -> RtspResponse:
        with self._lock:
            rtsp_response = RtspResponse()
            self._curl.setopt(pycurl.URL, f'{self.base_uri}{url_part}')
            self._curl.setopt(pycurl.OPT_RTSP_REQUEST, method)
            self._curl.setopt(pycurl.WRITEFUNCTION, rtsp_response.append_data)
            self._curl.setopt(pycurl.HEADERFUNCTION, rtsp_response.append_header)
            self._curl.setopt(pycurl.TIMEOUT, 4)
            self._curl.setopt(pycurl.USERAGENT, 'pycurl')

            if extra_curl_opts is not None:
                for key, value in extra_curl_opts.items():
                    self._curl.setopt(key, value)

            self._curl.perform()
            rtsp_response.finalize()
            return rtsp_response

    def close(self):
        log('(RTSP) Closing RtspConnection')
        with self._lock:
            self._curl.close()


class RtspStream(object):
    _connection: RtspConnection
    _session_id: str
    _client_rtp_port: int
    _client_rtcp_port: int
    _stream_id: Optional[int]

    def __init__(self, connection: RtspConnection, session_id: str, stream_id: int, client_rtp_port: int,
                 client_rtcp_port: int) -> None:
        self._connection = connection
        self._session_id = session_id
        self._stream_id = stream_id
        self._client_rtp_port = client_rtp_port
        self._client_rtcp_port = client_rtcp_port

    def play(self, pids: list[int]) -> Optional[RtpConnection]:
        log(f'(RTSP) Playing stream={self._stream_id} with pids={pids}')
        pids_str = ','.join(map(str, pids))
        url = f'stream={self._stream_id}?addpids={pids_str}'
        curl_extra_opts = {pycurl.OPT_RTSP_STREAM_URI: f'{self._connection.base_uri}{url}'}
        rtsp_response = self._connection.perform_rtsp_request(url, pycurl.RTSPREQ_PLAY, curl_extra_opts)
        rtp_connection = RtpConnection(self._client_rtp_port, self._client_rtcp_port)

        if rtsp_response.status_code != 200:
            log(f'(RTSP) Failed to play stream={self._stream_id}, got response={rtsp_response}')
            rtp_connection.close()
            raise RuntimeError(f'Failed to play stream={self._stream_id}, got response={rtsp_response}')

        return rtp_connection

    def teardown(self) -> bool:
        log(f'(RTSP) Teardown stream={self._stream_id}')
        url = f'stream={self._stream_id}'
        rtsp_response = self._connection.perform_rtsp_request(url, pycurl.RTSPREQ_TEARDOWN)

        if rtsp_response.status_code != 200:
            log(f'(RTSP) Failed to teardown stream={self._stream_id}, got response={rtsp_response}')
            return False

        log(f'(RTSP) Successfully tore down stream={self._stream_id}')
        return True


class RtspClient(object):
    _options_thread: Optional[Thread] = None
    _options_thread_stop_event = Event()
    _options_thread_sleep_cond = Condition()
    _connection: RtspConnection

    def __init__(self, server_ip: str, server_port: int,) -> None:
        self._connection = RtspConnection(server_ip, server_port)

    def close(self):
        log('(RTSP) Closing RtspClient')
        self._options_thread_stop_event.set()
        with self._options_thread_sleep_cond:
            self._options_thread_sleep_cond.notify()
        if self._options_thread and self._options_thread.is_alive():
            self._options_thread.join()
            log('Options thread joined')
        self._connection.close()

    def _start_options_thread(self, timeout_s):
        def send_options_request():
            rtsp_response = self._connection.perform_rtsp_request('', pycurl.RTSPREQ_OPTIONS)

            if rtsp_response.status_code != 200:
                log(f'(RTSP) Options request failed, got response={rtsp_response}')

        # Subtract a little time to account for setup process etc
        timeout_s -= 2

        def thread_wrapper():
            while not self._options_thread_stop_event.is_set():
                send_options_request()
                with self._options_thread_sleep_cond:
                    self._options_thread_sleep_cond.wait(timeout_s)

        self._options_thread = Thread(target=thread_wrapper)
        self._options_thread.start()

    def setup_stream(self, channel: SatIpChannel, client_rtp_port: int, client_rtcp_port: int) -> Optional[RtspStream]:
        log(f'(RTSP) Setting up stream: tuner #{channel.frontend}, frequency={channel.frequency}/{channel.polarisation}')
        url = channel.to_stream_uri_params()
        transport = f'RTP/AVP;unicast;client_port={client_rtp_port}-{client_rtcp_port}'
        extra_curl_opts = {
            pycurl.OPT_RTSP_STREAM_URI: f'{self._connection.base_uri}{url}',
            pycurl.OPT_RTSP_TRANSPORT: transport
        }
        rtsp_response = self._connection.perform_rtsp_request(url, pycurl.RTSPREQ_SETUP, extra_curl_opts)

        if rtsp_response.status_code != 200:
            log(f'(RTSP) Failed to setup stream for url={url}, got response={rtsp_response}')
            raise ValueError(f'Failed to setup stream for url={url}, got response={rtsp_response}')

        stream_id = int(rtsp_response.headers['com.ses.streamID'])
        session_id, timeout = rtsp_response.headers['Session'].split(';')
        timeout = int(timeout.replace('timeout=', '')) or 60
        result = RtspStream(self._connection, session_id, stream_id, client_rtp_port, client_rtcp_port)

        self._start_options_thread(timeout)
        return result
