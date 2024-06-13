import base64
import unittest

from src.rtcp import get_first_rtcp_app_packet_from_rtcp_data


class TestRtcp(unittest.TestCase):
    def test_given_rtcp_data_returns_app_package(self):
        # given
        rtcp_data = base64.b64decode('gMgABgCCerUAAAAAAAAAAIx7ggAAAABAAAE3YIHKAAYAgnq1ARFGRjpGRjpGRjpGRjpGRjpGRgCAzAAfAIJ6tVNFUzEAAABudmVyPTEuMDtzcmM9MTt0dW5lcj0xLDExNSwxLDEzLDEwNzE0LGgsZHZicyxxcHNrLG9mZiwwLjM1LDIyMDAwLDU2O3BpZHM9MCwxLDE2LDE3LDI2NiwyMzUzLDIzNTQsMjM1NSwyMzU2LDIzNTcAAA==')

        # when
        app_packet = get_first_rtcp_app_packet_from_rtcp_data(rtcp_data)

        # then
        assert app_packet.fec_inner == 56
        assert app_packet.frequency == 10714.0
        assert app_packet.frontend_id == 1
        assert app_packet.signal_level == 115
        assert app_packet.lock == False
        assert app_packet.name == 'SES1'
        assert app_packet.pids == [0, 1, 16, 17, 266, 2353, 2354, 2355, 2356, 2357]
        assert app_packet.pilots == False
        assert app_packet.polarisation == 'h'
        assert app_packet.quality == 13
        assert app_packet.roll_off == 0.35
        assert app_packet.source == 1
        assert app_packet.symbol_rate == 22000
        assert app_packet.system == 'dvbs'
        assert app_packet.type == 'qpsk'
        assert app_packet.version == '1.0'


if __name__ == '__main__':
    unittest.main()