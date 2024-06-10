import argparse
import time
import xml
import xml.etree.ElementTree as ET
import requests
import pycurl

from src.rtsp import RtspClient


def parse_args():
    parser = argparse.ArgumentParser(description='A sat finder for SAT>IP servers')
    parser.add_argument('-s', '--server-xml-descriptor', type=str, help='The full URL to the SAT>IP server XML descriptor', required=True)
    return parser.parse_args()

def fetch_xml_descriptor(descriptor_url: str):
    response = requests.get(descriptor_url)
    response.raise_for_status()
    raw_xml = response.text

    # namespaces = {'owl': 'urn:schemas-upnp-org:device-1-0'}
    parsed_descriptor = ET.fromstring(raw_xml)
    #
    namespaces = {
        'root': 'urn:schemas-upnp-org:device-1-0',
        'ses': 'urn:ses-com:satip',
    }
    server_manufacturer = parsed_descriptor.find('root:device/root:manufacturer', namespaces).text.strip()
    server_model = parsed_descriptor.find('root:device/root:modelName', namespaces).text.strip()

    # TODO Parse number of tuners from
    # <satip:X_SATIPCAP xmlns:satip="urn:ses-com:satip">DVBS2-2</satip:X_SATIPCAP>

    print(f'Server manufacturer: {server_manufacturer}, model: {server_model}')
    return (server_manufacturer, server_model)


class Test:
    def __init__(self):
        self.contents = ''.encode('ascii')

    def body_callback(self, buf):
        self.contents = self.contents + buf


def main():
    args = parse_args()
    # xml_descriptor = fetch_xml_descriptor(args.server_xml_descriptor)

    client = RtspClient('192.168.1.1', 554, 1)
    stream=client.setup_stream(57000, 57001, 1, 12265.5, 'h', 'dvbs2', 27500, 23, [0])
    rtp_connection = stream.play([1,16,17])

    # print(f'RtspSession={res}')

    time.sleep(70)

    rtp_connection.close()
    stream.teardown()
    client.close()




if __name__ == '__main__':
    main()