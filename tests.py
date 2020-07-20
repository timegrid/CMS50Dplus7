#!/usr/bin/env python
import datetime
import unittest
from unittest.mock import patch
from cms50dplus import (
    test_package,
    CMS50Dplus,
    RealtimeDataPoint,
    StorageDataPoint
)


def test_stream(byte_list):
    for byte in byte_list:
        yield chr(byte)
    yield ''


class CMS50DplusClassTests(unittest.TestCase):

    def test_set_bit(self):
        # 0 to 1
        for position in range(0, 8):
            result = CMS50Dplus.set_bit(0x00, 1, position)
            self.assertTrue(result & 0x01 << position)

        # 1 to 1
        for position in range(0, 8):
            result = CMS50Dplus.set_bit(0xff, 1, position)
            self.assertTrue(result & 0x01 << position)

        # 0 to 0
        for position in range(0, 8):
            result = CMS50Dplus.set_bit(0x00, 0, position)
            self.assertFalse(result & 0x01 << position)

        # 1 to 0
        for position in range(0, 8):
            result = CMS50Dplus.set_bit(0xff, 0, position)
            self.assertFalse(result & 0x01 << position)

    def test_decode_package_packet_length(self):
        packets = [0x00, 0x80] + [0x80] * 11

        # length too short
        for length in range(0, 3):
            self.assertRaisesRegex(
                ValueError, 'too short',
                CMS50Dplus.decode_package, packets[:length])

        # length ok
        for length in range(3, 10):
            CMS50Dplus.decode_package(packets[:length])

        # length too long
        for length in range(10, 13):
            self.assertRaisesRegex(
                ValueError, 'too long',
                CMS50Dplus.decode_package, packets[:length])

    def test_decode_package_synchronization_bits(self):
        # all bytes ok
        packets = [0x00, 0x80] + [0x80] * 7
        CMS50Dplus.decode_package(packets)

        # first byte wrong
        packets = [0x80, 0x80] + [0x80] * 7
        self.assertRaises(
            ValueError, CMS50Dplus.decode_package, [1] * 9)

        # other bytes wrong
        for position in range(1, 9):
            packets = [0x00, 0x80] + [0x80] * 7
            packets[position] = 0
            self.assertRaises(
                ValueError, CMS50Dplus.decode_package, packets)

    def test_decode_package_package_types(self):
        for byte in range(0x00, 0x80):
            packets = [byte, 0x80] + [0x80] * 7
            package_type, package = CMS50Dplus.decode_package(packets)
            self.assertEqual(byte, package_type)

    def test_decode_package_high_byte(self):
        # high: 0b11111111, packets: 0b10000000 => package: 0b10000000
        packets = [0, 0xff] + [0x80] * 7
        package_type, package = CMS50Dplus.decode_package(packets)
        for byte in package:
            self.assertEqual(byte, 0x80)

        # high: 0b11111111, packets: 0b11111111 => package: 0b11111111
        packets = [0, 0xff] + [0xff] * 7
        package_type, package = CMS50Dplus.decode_package(packets)
        for byte in package:
            self.assertEqual(byte, 0xff)

        # high: 0b10000000, packets: 0b10000000 => package: 0b00000000
        packets = [0, 0x80] + [0x80] * 7
        package_type, package = CMS50Dplus.decode_package(packets)
        for byte in package:
            self.assertEqual(byte, 0x00)

        # high: 0b10000000, packets: 0b11111111 => package: 0b01111111
        packets = [0, 0x80] + [0xff] * 7
        package_type, package = CMS50Dplus.decode_package(packets)
        for byte in package:
            self.assertEqual(byte, 0x7f)

    def test_encode_package_packet_length(self):
        package_type = 0x00
        package = [0x00] * 11

        # length too long
        for length in range(9, 11):
            self.assertRaisesRegex(
                ValueError, 'too long',
                CMS50Dplus.encode_package, package_type, package[:length])

    def test_encode_package_padding(self):
        package_type = 0x00

        # no padding
        for length in range(1, 8):
            package = [0x00] * length
            packets = CMS50Dplus.encode_package(package_type, package)
            self.assertEqual(len(packets), len(package) + 2)

        # padding too short
        for length in range(2, 8):
            package = [0x00] * length
            for padding in range(1, len(package)):
                self.assertRaisesRegex(
                    ValueError, 'too short',
                    CMS50Dplus.encode_package, package_type, package, padding)

        # padding ok
        for length in range(1, 8):
            package = [0x00] * length
            for padding in range(len(package), 8):
                packets = CMS50Dplus.encode_package(
                    package_type, package, padding)
                self.assertEqual(len(packets), padding + 2)

        # padding too long
        package = [0x00]
        for padding in range(8, 10):
            self.assertRaisesRegex(
                ValueError, 'too long',
                CMS50Dplus.encode_package, package_type, package, padding)

    def test_encode_package_padding_byte(self):
        package_type = 0x00
        package_byte = 0x00
        padding = 7
        for padding_byte in range(0x00, 0xff):
            for length in range(1, 8):
                package = [package_byte] * length
                packets = CMS50Dplus.encode_package(
                    package_type, package, padding, padding_byte)
                self.assertEqual(
                    packets[2:],
                    [CMS50Dplus.set_bit(package_byte)] * length +
                    [CMS50Dplus.set_bit(padding_byte)] * (padding - length))

    def test_encode_package_high_byte(self):
        package_type = 0x00

        # package: 0b10000000 => high: 0b11111111, packets: 0b10000000
        package = [0x80] * 7
        packets = CMS50Dplus.encode_package(package_type, package)
        self.assertEqual(packets[1], 0xff)

        # package: 0b00000000 => high: 0b10000000, packets: 0b10000000
        package = [0x00] * 7
        packets = CMS50Dplus.encode_package(package_type, package)
        self.assertEqual(packets[1], 0x80)

    def test_encode_package_synchronization_bits(self):
        package_type = 0x00
        package = [0x00] * 7
        packets = CMS50Dplus.encode_package(package_type, package)

        # first byte
        self.assertFalse(packets[0] & 0x80)

        # other bytes
        for idx in range(1, 9):
            self.assertTrue(packets[idx] & 0x80)

    def test_encode_package_decode_package(self):
        package_type = 0x00
        for run in range(0, 10):
            original_package = test_package()
            packets = CMS50Dplus.encode_package(package_type, original_package)
            _, decoded_package = CMS50Dplus.decode_package(packets)
            self.assertEqual(decoded_package, original_package)


@patch('serial.Serial')
class CMS50DplusInstanceTests(unittest.TestCase):

    @patch('serial.Serial')
    def setUp(self, MockSerial):
        self.oxi = CMS50Dplus()

    def test_is_connected(self, MockSerial):
        # no connection
        self.oxi.connection = None
        self.assertIsNone(self.oxi.connection)
        self.assertFalse(self.oxi.is_connected())

        # connection established
        self.oxi.connection = MockSerial()
        self.assertTrue(self.oxi.is_connected())

        # connection closed
        self.oxi.connection.isOpen.return_value = False
        self.assertFalse(self.oxi.is_connected())

    def test_connect(self, MockSerial):
        # no connection
        self.oxi.connection = None
        self.assertFalse(self.oxi.is_connected())

        # establish connection
        self.oxi.connect()
        self.assertTrue(self.oxi.is_connected())

        # reopen connection
        def mock_open():
            self.oxi.connection.isOpen.return_value = True
        self.oxi.connection.open.side_effect = mock_open
        self.oxi.connection.isOpen.return_value = False
        self.assertFalse(self.oxi.is_connected())
        self.oxi.connect()
        self.assertTrue(self.oxi.is_connected())

        # already connected
        self.oxi.connect()

        # check calls
        MockSerial.assert_called_once()
        self.oxi.connection.open.assert_called_once()

    def test_disconnect(self, MockSerial):
        self.oxi.disconnect()
        self.oxi.connection.close.assert_called_once()

    def test_get_byte(self, MockSerial):
        # stream
        byte_list = range(0x00, 0xff)
        self.oxi.connection.read.side_effect = test_stream(byte_list)
        for byte in byte_list:
            self.assertEqual(self.oxi.get_byte(), byte)

        # end of stream
        self.assertIsNone(self.oxi.get_byte())

    def test_send_bytes(self, MockSerial):
        byte_list = range(0x00, 0xff)
        string = b''
        for byte in byte_list:
            string += chr(byte).encode('raw_unicode_escape')
        self.oxi.send_bytes(byte_list)
        self.oxi.connection.write.assert_called_once_with(string)

    def test_expect_byte(self, MockSerial):
        byte_list = range(0x00, 0xfe)
        self.oxi.connection.read.side_effect = test_stream(byte_list)

        # found
        for byte in byte_list:
            self.assertTrue(self.oxi.expect_byte(byte))

        # not found
        self.assertFalse(self.oxi.expect_byte(0xff))

    def test_send_command_commands(self, MockSerial):
        commands = range(0x80, 0xff)
        for command in commands:
            self.oxi.send_command(command)
            string = b''
            for byte in [0x7d, 0x81, command] + [0x80] * 6:
                string += chr(byte).encode('raw_unicode_escape')
            self.oxi.connection.write.assert_called_with(string)
        self.assertEqual(self.oxi.connection.flush.call_count, len(commands))

    def test_send_command_data(self, MockSerial):
        command = 0x80
        data = [0xff] * 6
        self.oxi.send_command(command, data)
        string = b''
        for byte in [0x7d, 0xff, command] + data:
            string += chr(byte).encode('raw_unicode_escape')
        self.oxi.connection.write.assert_called_with(string)

    def test_send_keepalive(self, MockSerial):
        self.oxi.keepalive_interval = datetime.timedelta(milliseconds=5)
        test_interval = datetime.timedelta(milliseconds=50)
        start = datetime.datetime.now()
        while datetime.datetime.now() - start < test_interval:
            self.oxi.send_keepalive()
        self.assertAlmostEqual(
            self.oxi.connection.write.call_count,
            test_interval / self.oxi.keepalive_interval,
            delta=2)

    def test_get_packets_packet_length(self, MockSerial):
        # too few bytes
        data = CMS50Dplus.encode_package(0x00, test_package())
        for length in range(0, 3):
            byte_list = data[:length] * 10
            self.oxi.connection.read.side_effect = test_stream(byte_list)
            self.assertRaisesRegex(
                ValueError, 'too few bytes', next, self.oxi.get_packets())

        # valid packets length
        data = CMS50Dplus.encode_package(0x00, test_package())
        for length in range(3, 10):
            byte_list = data[:length] * 10
            self.oxi.connection.read.side_effect = test_stream(byte_list)
            for packets in self.oxi.get_packets():
                self.assertEqual(packets, byte_list[:length])

        # too many bytes
        data = CMS50Dplus.encode_package(0x00, test_package()) + [0x80] * 3
        for length in range(10, 13):
            byte_list = data[:length] * 10
            self.oxi.connection.read.side_effect = test_stream(byte_list)
            self.assertRaisesRegex(
                ValueError, 'too many bytes', next, self.oxi.get_packets())

    def test_get_packets_yields(self, MockSerial):
        packets_list = []
        for packets in range(0, 10):
            data = CMS50Dplus.encode_package(0x00, test_package())
            packets_list.append(data)
        self.oxi.connection.read.side_effect = test_stream(
            [byte for packets in packets_list for byte in packets])
        for idx, packets in enumerate(self.oxi.get_packets()):
            self.assertEqual(packets, packets_list[idx])

    def test_get_packets_amount(self, MockSerial):
        # right amounts
        data = CMS50Dplus.encode_package(0x00, test_package()) * 10
        for amount in range(1, 11):
            self.oxi.connection.read.side_effect = test_stream(data)
            self.assertEqual(len(list(self.oxi.get_packets(amount))), amount)

        # too few packets
        for amount in range(11, 13):
            self.oxi.connection.read.side_effect = test_stream(data)
            self.assertRaisesRegex(
                ValueError, 'too few packets',
                list, self.oxi.get_packets(amount))

    def test_get_packets_keepalive(self, MockSerial):
        data = CMS50Dplus.encode_package(0x00, test_package()) * 10
        self.oxi.connection.read.side_effect = test_stream(data)
        self.oxi.keepalive_interval = datetime.timedelta(milliseconds=5)

        start = datetime.datetime.now()
        list(self.oxi.get_packets())
        end = datetime.datetime.now()
        test_interval = end - start

        self.assertAlmostEqual(
            self.oxi.connection.write.call_count,
            test_interval / self.oxi.keepalive_interval,
            delta=2)

    def test_get_packages_yields(self, MockSerial):
        package_type = 0x01
        package = test_package()
        data = CMS50Dplus.encode_package(package_type, package) * 10
        self.oxi.connection.read.side_effect = test_stream(data)
        for decoded_package_type, decoded_package in self.oxi.get_packages():
            self.assertEqual(decoded_package_type, package_type)
            self.assertEqual(decoded_package, package)

    def test_get_packages_amount(self, MockSerial):
        package_type = 0x01
        package = test_package()
        data = CMS50Dplus.encode_package(package_type, package) * 10
        for amount in range(1, 11):
            self.oxi.connection.read.side_effect = test_stream(data)
            self.assertEqual(len(list(self.oxi.get_packages(amount))), amount)

    def test_get_realtime_data(self, MockSerial):
        package_type = 0x01
        package = test_package(7)
        data = CMS50Dplus.encode_package(package_type, package) * 10
        self.oxi.connection.read.side_effect = test_stream(data)
        for realtime_data_point in self.oxi.get_realtime_data():
            self.assertIsInstance(realtime_data_point, RealtimeDataPoint)

    def test_get_storage_data(self, MockSerial):
        package_type = 0x0f
        package = test_package(6)
        data = CMS50Dplus.encode_package(package_type, package) * 10
        self.oxi.connection.read.side_effect = test_stream(data)
        for storage_data_point in self.oxi.get_storage_data():
            self.assertIsInstance(storage_data_point, StorageDataPoint)
        package_type = 0x09
        package = test_package(4)
        data = CMS50Dplus.encode_package(package_type, package) * 10
        self.oxi.connection.read.side_effect = test_stream(data)
        for storage_data_point in self.oxi.get_storage_data():
            self.assertIsInstance(storage_data_point, StorageDataPoint)


class RealtimeDataTests(unittest.TestCase):

    def test_init_package_type(self):
        package = test_package(7)

        # right type
        package_type = 0x01
        RealtimeDataPoint(package_type, package)

        # wrong type
        package_type = 0x00
        self.assertRaisesRegex(
            ValueError, 'package type',
            RealtimeDataPoint, package_type, [])

    def test_init_package_length(self):
        package_type = 0x01

        # right length
        package = test_package(7)
        RealtimeDataPoint(package_type, package)

        # wrong length
        package = test_package(6)
        self.assertRaisesRegex(
            ValueError, 'package length',
            RealtimeDataPoint, package_type, package)

    def test_get_package(self):
        package_type = 0x01
        package = test_package(7)
        dp = RealtimeDataPoint(package_type, package)
        self.assertEqual(package, dp.get_package())

    def test_time(self):
        package_type = 0x01
        package = [0x00] * 7
        time = datetime.datetime.now()
        dp = RealtimeDataPoint(package_type, package, time=time)
        self.assertEqual(dp.time, time)
        self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_signal_strength(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in range(0, 16):
            package[0] = 0x00 | value
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.signal_strength, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_seaching_too_long(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in [False, True]:
            package[0] = 0x00 | value << 4
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.searching_too_long, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_low_spO2(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in [False, True]:
            package[0] = 0x00 | value << 5
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.low_spO2, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_pulse_beep(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in [False, True]:
            package[0] = 0x00 | value << 6
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.pulse_beep, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_probe_error(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in [False, True]:
            package[0] = 0x00 | value << 7
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.probe_error, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_pulse_waveform(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in range(0, 127):
            package[1] = 0x00 | value
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.pulse_waveform, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_searching_pulse(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in [False, True]:
            package[1] = 0x00 | value << 7
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.searching_pulse, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_bar_graph(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in range(0, 16):
            package[2] = 0x00 | value
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.bar_graph, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_pi_valid(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in [False, True]:
            package[2] = 0x00 | value << 4
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.pi_valid, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_reserved(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in range(0, 8):
            package[2] = 0x00 | value << 5
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.reserved, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_pulse_rate(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in range(0, 256):
            package[3] = 0x00 | value
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.pulse_rate, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_pulse_rate_invalid(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in [0, 255]:
            package[3] = 0x00 | value
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.pulse_rate_invalid, bool(value))
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_spO2(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in range(0, 256):
            package[4] = 0x00 | value
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.spO2, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_spO2_invalid(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in [0, 127]:
            package[4] = 0x00 | value
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.spO2_invalid, bool(value))
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_pi(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in range(0, 65536):
            package[5] = 0x00 | value & 0x00ff
            package[6] = 0x00 | (value & 0xff00) >> 8
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.pi, value)
            # self.assertEqual(dp.get_package(), package)
            # self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_pi_invalid(self):
        package_type = 0x01
        package = [0x00] * 7
        for value in [0, 65535]:
            package[5] = 0x00 | value & 0x00ff
            package[6] = 0x00 | (value & 0xff00) >> 8
            dp = RealtimeDataPoint(package_type, package)
            self.assertEqual(dp.pi_invalid, bool(value))
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())


class StorageDataTests(unittest.TestCase):

    def test_init_package_type(self):
        # right type
        package_type = 0x0f
        package = test_package(2)
        StorageDataPoint(package_type, package)
        package_type = 0x09
        package = test_package(4)
        StorageDataPoint(package_type, package)

        # wrong type
        package_type = 0x00
        self.assertRaisesRegex(
            ValueError, 'package type',
            StorageDataPoint, package_type, [])

    def test_init_package_length(self):
        # right length
        package_type = 0x0f
        package = test_package(2)
        StorageDataPoint(package_type, package)
        package_type = 0x09
        package = test_package(4)
        StorageDataPoint(package_type, package)

        # wrong length
        package_type = 0x0f
        package = test_package(4)
        self.assertRaisesRegex(
            ValueError, 'package length',
            StorageDataPoint, package_type, package)
        package_type = 0x09
        package = test_package(2)
        self.assertRaisesRegex(
            ValueError, 'package length',
            StorageDataPoint, package_type, package)

    def test_get_package(self):
        package_type = 0x0f
        package = test_package(2)
        dp = StorageDataPoint(package_type, package)
        self.assertEqual(package, dp.get_package())
        package_type = 0x09
        package = test_package(4)
        dp = StorageDataPoint(package_type, package)
        self.assertEqual(package, dp.get_package())

    def test_time(self):
        package_type = 0x0f
        package = [0x00] * 2
        time = datetime.datetime.now()
        dp = StorageDataPoint(package_type, package, time=time)
        self.assertEqual(dp.time, time)
        self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())
        package_type = 0x09
        package = [0x00] * 4
        time = datetime.datetime.now()
        dp = StorageDataPoint(package_type, package, time=time)
        self.assertEqual(dp.time, time)
        self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_spO2(self):
        # without pi support
        package_type = 0x0f
        package = [0x00] * 2
        for value in range(0, 256):
            package[0] = 0x00 | value
            dp = StorageDataPoint(package_type, package)
            self.assertEqual(dp.spO2, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

        # with pi support
        package_type = 0x09
        package = [0x00] * 4
        for value in range(0, 256):
            package[0] = 0x00 | value
            dp = StorageDataPoint(package_type, package)
            self.assertEqual(dp.spO2, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_spO2_invalid(self):
        # without pi support
        package_type = 0x0f
        package = [0x00] * 2
        for value in [0, 127]:
            package[0] = 0x00 | value
            dp = StorageDataPoint(package_type, package)
            self.assertEqual(dp.spO2_invalid, bool(value))
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

        # with pi support
        package_type = 0x09
        package = [0x00] * 4
        for value in [0, 127]:
            package[0] = 0x00 | value
            dp = StorageDataPoint(package_type, package)
            self.assertEqual(dp.spO2_invalid, bool(value))
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_pulse_rate(self):
        # without pi support
        package_type = 0x0f
        package = [0x00] * 2
        for value in range(0, 256):
            package[1] = 0x00 | value
            dp = StorageDataPoint(package_type, package)
            self.assertEqual(dp.pulse_rate, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

        # with pi support
        package_type = 0x09
        package = [0x00] * 4
        for value in range(0, 256):
            package[1] = 0x00 | value
            dp = StorageDataPoint(package_type, package)
            self.assertEqual(dp.pulse_rate, value)
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_pulse_rate_invalid(self):
        # without pi support
        package_type = 0x0f
        package = [0x00] * 2
        for value in [0, 255]:
            package[1] = 0x00 | value
            dp = StorageDataPoint(package_type, package)
            self.assertEqual(dp.pulse_rate_invalid, bool(value))
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

        # with pi support
        package_type = 0x09
        package = [0x00] * 4
        for value in [0, 255]:
            package[1] = 0x00 | value
            dp = StorageDataPoint(package_type, package)
            self.assertEqual(dp.pulse_rate_invalid, bool(value))
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_pi(self):
        # without pi support
        package_type = 0x0f
        package = test_package(2)
        dp = StorageDataPoint(package_type, package)
        self.assertEqual(dp.pi, '-')

        # with pi support
        package_type = 0x09
        package = test_package(4)
        for value in range(0, 65536):
            package[2] = 0x00 | value & 0x00ff
            package[3] = 0x00 | (value & 0xff00) >> 8
            dp = StorageDataPoint(package_type, package)
            self.assertEqual(dp.pi, value)
            # self.assertEqual(dp.get_package(), package)
            # self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())

    def test_pi_invalid(self):
        # without pi support
        package_type = 0x0f
        package = test_package(2)
        dp = StorageDataPoint(package_type, package)
        self.assertEqual(dp.pi_invalid, '-')

        # with pi support
        package_type = 0x09
        package = test_package(4)
        for value in [0, 65535]:
            package[2] = 0x00 | value & 0x00ff
            package[3] = 0x00 | (value & 0xff00) >> 8
            dp = StorageDataPoint(package_type, package)
            self.assertEqual(dp.pi_invalid, bool(value))
            self.assertEqual(dp.get_package(), package)
            self.assertEqual(dp.__repr__(), eval(dp.__repr__()).__repr__())


if __name__ == '__main__':
    unittest.main()
