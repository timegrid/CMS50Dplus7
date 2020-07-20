#!/usr/bin/env python
import sys
import datetime
import time
import random
import csv
import argparse
import threading
import tkinter
from tkinter import messagebox, simpledialog, filedialog

import serial
from serial.tools import list_ports
from dateutil import parser as dateparser
import numpy as np
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import cbook
from matplotlib.backend_bases import key_press_handler
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk
)


def test_package(length=7):
    result = [0x00] * length
    for idx in range(0, length):
        result[idx] = random.getrandbits(8)
    return result


def test_storage(starttime=False):
    if not starttime:
        starttime = datetime.datetime.now()
    delay = datetime.timedelta(seconds=1)
    for idx in range(60*60*3):
        time = starttime + delay * idx
        yield StorageDataPoint(15, test_package(2), time)


def test_realtime():
    while True:
        time.sleep(1/60)
        yield RealtimeDataPoint(1, test_package(7))


class DataPoint():
    datatype = ''
    specs = {}  # {package_type: package_length, ...}
    attributes = []  # [(attribute, string, csvheader), ...]

    def __init__(self, package_type, package, time=False):
        self.time = time and time or datetime.datetime.now()

        # package type
        if package_type not in self.specs:
            raise ValueError("Invalid package type.")
        self.package_type = package_type

        # packet length
        if len(package) != self.specs[self.package_type]:
            raise ValueError("Invalid package length.")

        # set data
        self.set_package(package_type, package, time)

    def __repr__(self):
        hexBytes = ['0x{0:02X}'.format(byte) for byte in self.get_package()]
        return "{}({}, [{}], {})".format(
            self.__class__.__name__, self.package_type, ', '.join(hexBytes),
            repr(self.time))

    def __str__(self):
        return ",\n".join([attr[1] for attr in self.attributes]).format(
            **[getattr(self, attr[0]) for attr in self.attributes]
        )

    @classmethod
    def get_attribute_names(cls):
        return [attr[0] for attr in cls.attributes]

    @classmethod
    def get_csv_header(cls):
        return [attr[2] for attr in cls.attributes]

    def get_csv_data(self):
        return [getattr(self, attr[0]) for attr in self.attributes]

    def set_csv_data(self, data):
        for attr, _, key in self.attributes:
            if key in data:
                value = data[key]
                if isinstance(value, float):
                    value = int(value)
                if attr == 'time':
                    value = dateparser.parse(value)
                setattr(self, attr, value)

    def get_dict_data(self):
        ret = dict()
        for n, d in zip(self.get_csv_header(), self.get_csv_data()):
            ret[n] = d
        return ret

    def set_package(package_type, package, time):
        raise NotImplementedError('set_package() not implemented.')

    def get_package(self):
        raise NotImplementedError('get_package() not implemented.')


class RealtimeDataPoint(DataPoint):
    datatype = 'realtime'
    specs = {  # {package_type: package_length, ...}
        0x01: 7
    }
    attributes = [  # [(attribute, string, csvheader), ...]
        ('time',               "Time = {}",               "Time"),
        ('spO2',               "SpO2 = {}%",              "SpO2"),
        ('pulse_rate',         "Pulse Rate = {} bpm",     "PulseRate"),
        ('pulse_waveform',     "Pulse Waveform = {}",     "PulseWaveform"),
        ('pulse_beep',         "Pulse Beep = {}",         "PulseBeep"),
        ('bar_graph',          "Bar Graph = {}",          "BarGraph"),
        ('pi',                 "PI = {}%",                "Pi"),
        ('signal_strength',    "Signal Strength = {}",    "SignalStrength"),
        ('probe_error',        "Probe Error = {}",        "ProbeError"),
        ('low_spO2',           "Low SpO2 = {}",           "LowSpO2"),
        ('searching_too_long', "Searching Too Long = {}", "SearchingTooLong"),
        ('searching_pulse',    "Searching Pulse = {}",    "SearchingPulse"),
        ('spO2_invalid',       "SpO2 Invalid = {}",       "SpO2Invalid"),
        ('pulse_rate_invalid', "Pulse Rate Invalid = {}", "PulseRateInvalid"),
        ('pi_valid',           "PI Valid = {}",           "PiValid"),
        ('pi_invalid',         "PI Invalid = {}",         "PiInvalid"),
        ('reserved',           "Reserved = {}",           "Reserved"),
        ('datatype',           "Data Type = {}",          "DataType"),
        ('package_type',       "Package Type = {}",       "PackageType"),
    ]

    def set_package(self, package_type, package, time):
        # packet byte 2 / package byte 0
        self.signal_strength = package[0] & 0x0f
        self.searching_too_long = (package[0] & 0x10) >> 4
        self.low_spO2 = (package[0] & 0x20) >> 5
        self.pulse_beep = (package[0] & 0x40) >> 6
        self.probe_error = (package[0] & 0x80) >> 7

        # packet byte 3 / package byte 1
        self.pulse_waveform = package[1] & 0x7f
        self.searching_pulse = (package[1] & 0x80) >> 7

        # packet byte 4 / package byte 2
        self.bar_graph = package[2] & 0x0f
        self.pi_valid = (package[2] & 0x10) >> 4
        self.reserved = (package[2] & 0xe0) >> 5

        # packet byte 5 / package byte 3
        self.pulse_rate = package[3]
        self.pulse_rate_invalid = int(self.pulse_rate == 0xff)

        # packet byte 6 / package byte 4
        self.spO2 = package[4]
        self.spO2_invalid = int(self.spO2 == 0x7f)

        # packet byte 7-8 / package byte 5-6
        self.pi = package[6] << 8 | package[5]
        self.pi_invalid = int(self.pi == 0xffff)

    def get_package(self):
        package = [0] * self.specs[self.package_type]

        # packet byte 2 / package byte 0
        package[0] = self.signal_strength & 0x0f
        if self.searching_too_long:
            package[0] |= 0x10
        if self.low_spO2:
            package[0] |= 0x20
        if self.pulse_beep:
            package[0] |= 0x40
        if self.probe_error:
            package[0] |= 0x80

        # packet byte 3 / package byte 1
        package[1] = self.pulse_waveform & 0x7f
        if self.searching_pulse:
            package[1] |= 0x80

        # packet byte 4 / package byte 2
        package[2] = self.bar_graph & 0x0f
        if self.pi_valid:
            package[2] |= 0x10
        package[2] |= (self.reserved << 5) & 0xe0

        # packet byte 5 / package byte 3
        package[3] = self.pulse_rate & 0xff

        # packet byte 6 / package byte 4
        package[4] = self.spO2 & 0xff

        # packet byte 7-8 / package byte 5-6
        package[5] = self.pi & 0x00ff
        package[6] = (self.pi & 0xff00) >> 8

        return package


class StorageDataPoint(DataPoint):
    datatype = 'storage'
    specs = {  # {package_type: package_length, ...}
        0x0f: 2,  # one package of 6 bytes split into 3 datapoints
        0x09: 4,
    }
    attributes = [  # [(attribute, string, csvheader), ...]
        ('time',               "Time = {}",               "Time"),
        ('spO2',               "SpO2 = {}%",              "SpO2"),
        ('pulse_rate',         "Pulse Rate = {} bpm",     "PulseRate"),
        ('pi',                 "PI = {}%",                "Pi"),
        ('pi_support',         "PI Support = {}",         "PiSupport"),
        ('pulse_rate_invalid', "Pulse Rate Invalid = {}", "PulseRateInvalid"),
        ('spO2_invalid',       "SpO2 Invalid = {}",       "SpO2Invalid"),
        ('pi_invalid',         "PI Invalid = {}",         "PiInvalid"),
        ('datatype',           "Data Type = {}",          "DataType"),
        ('package_type',       "Package Type = {}",       "PackageType"),
    ]

    def set_package(self, package_type, package, time):
        # pi support
        self.pi_support = 0
        if self.package_type == 0x09:
            self.pi_support = 1

        # packet byte 2|4|6 / package byte 0
        self.spO2 = package[0] & 0xff
        self.spO2_invalid = int(self.spO2 == 0x7f)

        # packet byte 3|5|7 / package byte 1
        self.pulse_rate = package[1] & 0xff
        self.pulse_rate_invalid = int(self.pulse_rate == 0xff)

        # packet byte 4-5 / package byte 2-3
        if self.pi_support:
            self.pi = package[3] << 8 | package[2]
            self.pi_invalid = int(self.pi == 0xffff)
        else:
            self.pi = "-"
            self.pi_invalid = "-"

    def get_package(self):
        package = [0] * self.specs[self.package_type]

        # packet byte 2|4|6 / package byte 0
        package[0] = self.spO2 & 0xff

        # packet byte 3|5|7 / package byte 1
        package[1] = self.pulse_rate & 0xff

        # packet byte 4-5 / package byte 2-3
        if self.pi_support:
            package[2] = self.pi & 0x00ff
            package[3] = (self.pi & 0xff00) >> 8

        return package


class CMS50Dplus():
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200, timeout=0.5,
                 connect=True):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.keepalive_interval = datetime.timedelta(seconds=5)
        self.keepalive_timestamp = datetime.datetime.now()
        self.storage_time_interval = datetime.timedelta(seconds=1)
        self.connection = None
        if connect:
            self.connect()

    def __del__(self):
        self.disconnect()

    @staticmethod
    def set_bit(byte, value=1, index=7):
        mask = 1 << index
        byte &= ~mask
        if value:
            byte |= mask
        return byte

    @classmethod
    def decode_package(cls, packets):
        # check packet length
        if len(packets) < 3:
            raise ValueError("Package too short to decode.")
        if len(packets) > 9:
            raise ValueError("Package too long to decode")

        # check synchronization bits
        if packets[0] & 0x80:
            raise ValueError("Invalid synchronization bit.")
        for byte in packets[1:]:
            if not byte & 0x80:
                raise ValueError("Invalid synchronization bit.")

        # define packet parts
        package_type = packets[0]
        high_byte = packets[1]
        package = packets[2:]

        # decode high byte
        for idx, byte in enumerate(package):
            package[idx] = cls.set_bit(byte, high_byte & 0x01 << idx)

        return package_type, package

    @classmethod
    def encode_package(cls, package_type, package,
                       padding=0, padding_byte=0x00):
        # check package length
        if len(package) > 7:
            raise ValueError("Package too long to encode.")

        # define packet parts
        high_byte = 0x80
        package = package[:]

        # pad package
        if padding:
            if padding < len(package):
                raise ValueError("Padding too short.")
            if padding > 7:
                raise ValueError("Padding too long.")
            if padding > len(package):
                package += [padding_byte] * (padding - len(package))

        # encode high byte
        for idx, byte in enumerate(package):
            high_byte |= (byte & 0x80) >> (7 - idx)

        # set synchronization bits
        package_type = cls.set_bit(package_type, 0)
        for idx, byte in enumerate(package):
            package[idx] = cls.set_bit(byte)

        # compose packets
        packets = [package_type, high_byte] + package

        return packets

    def is_connected(self):
        if self.connection and self.connection.isOpen():
            return True
        return False

    def connect(self):
        if self.connection is None:
            self.connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                xonxoff=1
            )
        elif not self.is_connected():
            self.connection.open()

    def disconnect(self):
        if self.is_connected():
            self.connection.close()

    def get_byte(self):
        char = self.connection.read()
        if len(char) == 0:
            return None
        else:
            return ord(char)

    def send_bytes(self, values):
        return self.connection.write(
            b''.join([
                chr(value & 0xff).encode('raw_unicode_escape')
                for value in values]))

    def expect_byte(self, value):
        while True:
            byte = self.get_byte()
            if byte is None:
                return False
            elif byte == value:
                return True

    def send_command(self, command, data=[]):
        package = self.encode_package(
            package_type=0x7d,  # command
            package=[command] + data, padding=7, padding_byte=0x00)
        self.send_bytes(package)
        self.connection.flush()

    def send_keepalive(self):
        now = datetime.datetime.now()
        if now - self.keepalive_timestamp > self.keepalive_interval:
            self.send_command(0xaf)  # keepalive
            self.keepalive_timestamp = now

    def get_packets(self, amount=0):
        count = 0
        idx = 0
        packets = []
        while True:
            if not amount:
                self.send_keepalive()
            byte = self.get_byte()
            if byte is None:
                if len(packets[:idx]) < 3:
                    raise ValueError("Recieved too few bytes for packets.")
                if amount and count + 1 < amount:
                    raise ValueError("Recieved too few packets.")
                yield packets[:idx]
                break
            sync_bit = bool(byte & 0x80)
            if not sync_bit:
                if packets:
                    if len(packets[:idx]) < 3:
                        raise ValueError("Recieved too few bytes for packets.")
                    yield packets[:idx]
                    if amount:
                        count += 1
                        if count == amount:
                            break
                packets = [0x00] * 9
                idx = 0
            if idx > 8:
                raise ValueError("Received too many bytes for packets.")
            packets[idx] = byte
            idx += 1

    def get_packages(self, amount=0):
        for packets in self.get_packets(amount):
            package_type, package = self.decode_package(packets)
            if package_type == 0x0d:  # disconnect notice
                if package[0] in [0x00, 0x01]:
                    break
                raise ValueError(
                    "Received reasoncode 0x{:02X}".format(package[0]))
            yield package_type, package

    def get_realtime_data(self):
        try:
            self.connection.reset_input_buffer()
            self.send_command(0xa1)  # start realtime data
            for package_type, package in self.get_packages():
                yield RealtimeDataPoint(package_type, package)
        except KeyboardInterrupt:
            pass
        finally:
            self.send_command(0xa2)  # stop realtime data

    def get_storage_data(self, starttime=False,
                         user_index=0x01, storage_segment=0x01):
        if not starttime:
            starttime = datetime.datetime.now()
        try:
            self.connection.reset_input_buffer()
            self.send_command(  # start storage data
                0xa6, [user_index, storage_segment])
            for package_type, package in self.get_packages():
                if package_type == 0x0f:
                    if package[0] and package[1]:
                        yield StorageDataPoint(
                            package_type, package[0:2], time=starttime)
                        starttime += self.storage_time_interval
                    if package[2] and package[3]:
                        yield StorageDataPoint(
                            package_type, package[2:4], time=starttime)
                        starttime += self.storage_time_interval
                    if package[4] and package[5]:
                        yield StorageDataPoint(
                            package_type, package[4:6], time=starttime)
                        starttime += self.storage_time_interval
                else:
                    yield StorageDataPoint(
                        package_type, package, time=starttime)
                    starttime += self.storage_time_interval
        except KeyboardInterrupt:
            pass
        finally:
            self.send_command(0xa7)  # stop storage data


class CMS50DplusGui():
    def __init__(self, port=False, testdata=False):
        # debug
        self.testdata = testdata

        # data
        self.reset()
        self.starttime = False

        # config
        self.plot_refreshrate = 10  # ms
        self.plot_samplerate = 0  # 0: off, 1-60: Hz
        self.plot_xmin_window = datetime.timedelta(seconds=10)
        self.plot_xmax_margin = datetime.timedelta(seconds=1)
        self.date_format = "%d.%m.%Y %H:%M:%S"
        self.spO2_high = 100
        self.spO2_low = 90
        self.pulse_rate_high = 100
        self.pulse_rate_low = 50

        # oximeter
        if not port:
            port = self.oximeter.port
        self.oximeter = CMS50Dplus(port, connect=False)
        try:
            self.oximeter.connect()
        except serial.serialutil.SerialException:
            self.oximeter.disconnect()

        # root window
        self.root = root = tkinter.Tk()
        self.root.title("Contec CMS50D+ v7 Data Processor")

        # top menue
        self.menuindex = {
            'filemenu': {
                'load': 0,
                'save': 1,
                'autoresize': 3,
                'quit': 5,
            },
            'devicemenu': {
                'connect': 0,
                'disconnect': 1,
                'start_realtime': 3,
                'stop_realtime': 4,
                'get_storage': 6
            }
        }
        self.menu = menu = tkinter.Menu(root)
        root.config(menu=menu)

        # file menu
        self.filemenu = filemenu = tkinter.Menu(menu, tearoff=0)
        filemenu.add_command(label="Open File...", command=self.load,
                             accelerator="ctrl+o")
        filemenu.add_command(label="Save File...", command=self.save,
                             accelerator="ctrl+s")
        filemenu.add_separator()
        filemenu.add_command(label="Autoresize", command=self.resize_plot,
                             accelerator="ctrl+a")
        filemenu.add_separator()
        filemenu.add_command(label="Quit", command=self.quit,
                             accelerator="ctrl+q")
        menu.add_cascade(label="File", menu=filemenu)

        # device menu
        self.devicemenu = devicemenu = tkinter.Menu(menu, tearoff=0)
        devicemenu.add_command(label="Connect...", command=self.connect,
                               accelerator="ctrl+c")
        devicemenu.add_command(label="Disconnect", command=self.disconnect,
                               accelerator="ctrl+c")
        devicemenu.add_separator()
        devicemenu.add_command(label="Start Realtime",
                               command=self.start_realtime,
                               accelerator="ctrl+r")
        devicemenu.add_command(label="Stop Realtime",
                               command=self.stop_realtime,
                               accelerator="ctrl+r")
        devicemenu.add_separator()
        devicemenu.add_command(label="Get Storage", command=self.get_storage,
                               accelerator="ctrl+t")
        menu.add_cascade(label="Device", menu=devicemenu)

        # initial menu states
        self.disable_menuitems([
            ('filemenu', 'save'),
            ('filemenu', 'autoresize'),
            ('devicemenu', 'stop_realtime'),
            ])
        if self.oximeter.is_connected():
            self.disable_menuitems([
                ('devicemenu', 'connect'),
                ])
        else:
            self.disable_menuitems([
                ('devicemenu', 'disconnect'),
                ('devicemenu', 'start_realtime'),
                ('devicemenu', 'stop_realtime'),
                ('devicemenu', 'get_storage'),
                ])
        if self.testdata:
            self.connect()

        # figure
        self.fig, (
            self.ax_spO2,
            self.ax_pulse_rate,
            self.ax_other
        ) = plt.subplots(3, sharex=True)
        self.fig.tight_layout()
        self.ax_spO2.fmt_xdata = mdates.DateFormatter(self.date_format)
        self.ax_pulse_rate.fmt_xdata = mdates.DateFormatter(self.date_format)
        self.ax_other.fmt_xdata = mdates.DateFormatter(self.date_format)
        self.canvas = canvas = FigureCanvasTkAgg(self.fig, master=root)

        # toolbar
        self.toolbar = NavigationToolbar2Tk(canvas, root)
        self.toolbar._Button(
            "Autoscale", str(cbook._get_data_path("images/help.gif")),
            False, self.resize_plot)
        canvas.get_tk_widget().pack(side='top', fill='both', expand=1)
        self.toolbar.update()

        # keyboard shortcuts
        def on_key_press(event):
            if event.key in ['ctrl+w', 'ctrl+q']:
                return self.quit()
            if event.key == 'ctrl+s':
                return self.save()
            if event.key == 'ctrl+o':
                return self.load()
            if event.key == 'ctrl+a':
                return self.resize_plot()
            if event.key == 'ctrl+c':
                return self.toggle_connection()
            if event.key == 'ctrl+r':
                return self.toggle_realtime()
            if event.key == 'ctrl+t':
                return self.get_storage()
            key_press_handler(event, canvas, self.toolbar)
        canvas.mpl_connect("key_press_event", on_key_press)

        # plot
        self.plot()

    def change_menuitems(self, identifiers, state):
        for identifier in identifiers:
            menu = getattr(self, identifier[0], False)
            index = self.menuindex[identifier[0]][identifier[1]]
            menu.entryconfig(index, state=state)

    def enable_menuitems(self, identifier):
        self.change_menuitems(identifier, 'normal')

    def disable_menuitems(self, identifier):
        self.change_menuitems(identifier, 'disabled')

    def start(self):
        self.root.mainloop()

    def quit(self, event=None):
        self.root.stop_thread = True
        if hasattr(self, 'thread'):
            while self.thread.is_alive():
                pass
        self.root.quit()
        self.oximeter.disconnect()

    def load(self, event=None):
        try:
            csvfile = filedialog.askopenfile(
                filetypes=[('csv', '*.csv')], defaultextension='csv')
            reader = csv.DictReader(csvfile, quoting=csv.QUOTE_NONNUMERIC)

            # get first row
            row = next(reader)

            # get datatype
            self.reset()
            self.data['datatype'] = datatype = row['DataType']
            self.data['package_type'] = package_type = row['PackageType']
            if datatype == 'realtime':
                DataPointClass = RealtimeDataPoint
            elif datatype == 'storage':
                DataPointClass = StorageDataPoint
            else:
                raise ValueError('Datatype unknown.')

            # get data
            while row:

                # create empty datapoint
                datapoint = DataPointClass(
                    package_type, [0] * DataPointClass.specs[package_type])

                # set datapoint attributes
                datapoint.set_csv_data(row)

                # set collected data
                self.data['count'] += 1
                self.data['point'].append(datapoint)
                self.data['time'].append(datapoint.time)
                spO2 = np.nan
                if datapoint.spO2:
                    spO2 = datapoint.spO2
                self.data['spO2'].append(spO2)
                pulse_rate = np.nan
                if datapoint.pulse_rate:
                    pulse_rate = datapoint.pulse_rate
                self.data['pulse_rate'].append(pulse_rate)

                if self.data['datatype'] == 'realtime':
                    pulse_waveform = np.nan
                    if datapoint.pulse_waveform:
                        pulse_waveform = datapoint.pulse_waveform
                    self.data['pulse_waveform'].append(pulse_waveform)
                    self.data['pulse_beep'].append(datapoint.pulse_beep)
                    self.data['bar_graph'].append(datapoint.bar_graph)
                    self.data['pi'].append(datapoint.pi)
                    self.data['signal_strength'].append(
                        datapoint.signal_strength)
                    self.data['probe_error'].append(datapoint.probe_error)
                    self.data['low_spO2'].append(datapoint.low_spO2)
                    self.data['searching_too_long'].append(
                        datapoint.searching_too_long)
                    self.data['searching_pulse'].append(
                        datapoint.searching_pulse)
                    self.data['spO2_invalid'].append(datapoint.spO2_invalid)
                    self.data['pulse_rate_invalid'].append(
                        datapoint.pulse_rate_invalid)
                    self.data['pi_valid'].append(datapoint.pi_valid)
                    self.data['pi_invalid'].append(datapoint.pi_invalid)
                    self.data['reserved'].append(datapoint.reserved)

                # get next row
                row = next(reader, False)

            # calculate samplerate
            start = self.data['time'][0]
            end = self.data['time'][-1]
            seconds = (end - start).total_seconds()
            self.data['samplerate'] = len(self.data['time']) / seconds

            # plot data
            self.plot(samplerate=self.plot_samplerate, limit=False)

        except TypeError as e:
            if 'argument 1 must be an iterator' in str(e):
                return
            messagebox.showerror(title='Error:', message=e)
        except Exception as e:
            messagebox.showerror(title='Error:', message=e)

        # adjust menu
        self.enable_menuitems([
            ('filemenu', 'save'),
            ('filemenu', 'autoresize'),
            ])

    def save(self, event=None):
        if not self.data['point']:
            return
        try:
            csvfile = filedialog.asksaveasfile(
                filetypes=[('csv', '*.csv')], defaultextension='csv')
            writer = csv.writer(csvfile, quoting=csv.QUOTE_NONNUMERIC)
            writer.writerow(self.data['point'][0].get_csv_header())
            for datapoint in self.data['point'][:self.data['count']]:
                writer.writerow(datapoint.get_csv_data())
        except TypeError as e:
            if 'argument 1 must have a "write" method' in str(e):
                return
            messagebox.showerror(title='Error:', message=e)
        except Exception as e:
            messagebox.showerror(title='Error:', message=e)

    def toggle_connection(self, event=None):
        if self.oximeter.is_connected():
            self.disconnect()
            return
        self.connect()

    def connect(self):
        if not self.testdata:
            port = simpledialog.askstring(
                title="Connect", initialvalue=self.oximeter.port,
                prompt="Virtual serial port of the device:")
            if not port:
                return
            self.oximeter.port = port
            try:
                self.oximeter.connect()
            except serial.serialutil.SerialException as e:
                ports = ""
                for port in list_ports.comports():
                    if port.pid:
                        ports += "{}\n".format(port.device)
                if ports:
                    ports = "\nAvailable USB ports are:\n" + ports
                messagebox.showerror(title='Error:', message=str(e) + ports)
                return
            except Exception as e:
                messagebox.showerror(title='Error:', message=e)
                return

        # adjust menu
        self.disable_menuitems([
            ('devicemenu', 'connect'),
            ('devicemenu', 'stop_realtime'),
            ])
        self.enable_menuitems([
            ('devicemenu', 'disconnect'),
            ('devicemenu', 'start_realtime'),
            ('devicemenu', 'get_storage'),
            ])

    def disconnect(self):
        if not self.testdata:
            try:
                self.oximeter.disconnect()
            except Exception as e:
                messagebox.showerror(title='Error:', message=e)
                return

        # adjust menu
        self.disable_menuitems([
            ('devicemenu', 'disconnect'),
            ('devicemenu', 'start_realtime'),
            ('devicemenu', 'stop_realtime'),
            ('devicemenu', 'get_storage'),
            ])
        self.enable_menuitems([
            ('devicemenu', 'connect'),
            ])

    def toggle_realtime(self, event=None):
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.stop_realtime()
            return
        self.start_realtime()

    def start_realtime(self):
        self.reset('realtime')

        # start data
        self.thread = ThreadedRealtimeData(self.root, self.oximeter, self.data)
        self.thread.start()

        # plot data
        self.root.after(self.plot_refreshrate, self.plot_loop)

        # adjust menu
        self.disable_menuitems([
            ('filemenu', 'load'),
            ('filemenu', 'save'),
            ('filemenu', 'autoresize'),
            ('devicemenu', 'disconnect'),
            ('devicemenu', 'start_realtime'),
            ('devicemenu', 'get_storage'),
            ])
        self.enable_menuitems([
            ('devicemenu', 'stop_realtime'),
            ])

    def stop_realtime(self):
        # stop thread
        self.root.stop_thread = True

        # stop data
        if not self.testdata:
            self.oximeter.send_command(0xa2)  # stop realtime data

        # adjust menu
        self.disable_menuitems([
            ('devicemenu', 'stop_realtime'),
            ])
        self.enable_menuitems([
            ('filemenu', 'load'),
            ('filemenu', 'save'),
            ('filemenu', 'autoresize'),
            ('devicemenu', 'disconnect'),
            ('devicemenu', 'start_realtime'),
            ('devicemenu', 'get_storage'),
            ])

        # plot full data
        self.plot(end=self.data['count'], samplerate=self.plot_samplerate)

    def get_storage(self, event=None):
        self.reset('storage')

        # get starttime
        while True:
            try:
                if not self.starttime:
                    self.starttime = datetime.datetime.now().strftime(
                        self.date_format)
                usertime = simpledialog.askstring(
                    title="Start Time", initialvalue=self.starttime,
                    prompt="Start time:")
                self.starttime = dateparser.parse(usertime)
                break
            except Exception as e:
                if not usertime:
                    self.starttime = False
                    return
                self.starttime = usertime
                messagebox.showerror(title='Error:', message=e)

        # get data
        try:
            if self.data['testdata']:
                datapoints = test_storage(starttime=self.starttime)
            else:
                datapoints = self.oximeter.get_storage_data(
                    starttime=self.starttime)
            for datapoint in datapoints:
                self.data['count'] += 1
                self.data['point'].append(datapoint)
                self.data['time'].append(datapoint.time)
                spO2 = np.nan
                if datapoint.spO2:
                    spO2 = datapoint.spO2
                self.data['spO2'].append(spO2)
                pulse_rate = np.nan
                if datapoint.pulse_rate:
                    pulse_rate = datapoint.pulse_rate
                self.data['pulse_rate'].append(pulse_rate)
        except ValueError as e:
            messagebox.showerror(title='Error:', message=e)
            return

        if not self.data['point']:
            messagebox.showinfo(title='Info:', message='No data found.')
            return

        # plot data
        self.plot(limit=False)

        # adjust menu
        self.enable_menuitems([
            ('filemenu', 'load'),
            ('filemenu', 'save'),
            ('filemenu', 'autoresize'),
            ])

    def reset(self, datatype=None):
        self.data = {
            'datatype': datatype,
            'testdata': self.testdata,
            'count': 0,
            'samplerate': 0,
            'point': [],
        }
        for DataPointClass in [StorageDataPoint, RealtimeDataPoint]:
            for attr in DataPointClass.get_attribute_names():
                self.data[attr] = []

    def plot(self, end=False, samplerate=False, cap=False, limit=True):
        # pick end
        if not end:
            end = len(self.data['time'])

        # calculate steps from samplerate
        step = 1
        if samplerate and self.data['samplerate']:
            step = int(self.data['samplerate'] / samplerate)

        # x axis
        start = 0
        x = self.data['time'][:end:step]
        if cap:
            start = -int(
                (self.plot_xmin_window.total_seconds() + 5) * samplerate)
            x = x[start:]

        # y axis
        y_spO2 = self.data['spO2'][:end:step]
        y_pulse_rate = self.data['pulse_rate'][:end:step]
        y_pulse_waveform = self.data['pulse_waveform'][:end:step]
        y_signal_strength = self.data['signal_strength'][:end:step]
        if cap:
            y_spO2 = y_spO2[start:]
            y_pulse_rate = y_pulse_rate[start:]
            y_pulse_waveform = y_pulse_waveform[start:]
            y_signal_strength = y_signal_strength[start:]

        # clear plots
        self.ax_spO2.clear()
        self.ax_pulse_rate.clear()
        self.ax_other.clear()

        # view limits
        if x:
            xmin = x[0]
            xmax = x[-1]
            if limit:
                xmin = x[-1] - self.plot_xmin_window
                xmax = x[-1] + self.plot_xmax_margin
            self.ax_spO2.set_xlim(xmin, xmax)
            self.ax_pulse_rate.set_xlim(xmin, xmax)
            self.ax_other.set_xlim(xmin, xmax)

        # plot low/high values
        style = {'color': '0.5', 'linestyle': ':', 'linewidth': 1}
        self.ax_spO2.axhline(self.spO2_high, **style)
        self.ax_spO2.axhline(self.spO2_low, **style)
        self.ax_pulse_rate.axhline(self.pulse_rate_high, **style)
        self.ax_pulse_rate.axhline(self.pulse_rate_low, **style)
        self.ax_other.axhline(1.000000001, **style)
        self.ax_other.axhline(0, **style)

        # plot main data
        self.ax_spO2.set_ylabel('SpO2 [%]', color='b')
        self.ax_spO2.plot(x, y_spO2, color='b')
        self.ax_pulse_rate.set_ylabel('Pulse Rate [bpm]', color='r')
        self.ax_pulse_rate.plot(x, y_pulse_rate, color='r')

        # plot other data
        legend = False
        if y_signal_strength:
            legend = True
            y_signal_strength_norm = [min(x, 8) / 8 for x in y_signal_strength]
            self.ax_other.plot(
                x, y_signal_strength_norm,
                label="Signal Strength", color='0.5')
        if y_pulse_waveform:
            legend = True
            y_pulse_waveform_norm = [x / 127 for x in y_pulse_waveform]
            self.ax_other.plot(
                x, y_pulse_waveform_norm,
                label='Pulse Waveform', color='m')
        if legend:
            self.ax_other.legend(loc='lower left')
        self.ax_other.set_ylabel('Other', color='k')
        self.ax_other.set_xlabel('Time')

        # draw
        self.canvas.draw()

    def plot_loop(self):
        # wait for thread to be stopped
        if getattr(self.root, 'stop_thread', False):
            if hasattr(self, 'thread'):
                while self.thread.is_alive():
                    pass
            self.root.stop_thread = False
            return

        # stop loop due to exception in thread
        if getattr(self.root, 'thread_exception', False):

            # stop data
            self.oximeter.send_command(0xa2)  # stop realtime data

            # adjust menu
            self.disable_menuitems([
                ('devicemenu', 'stop_realtime'),
                ])
            self.enable_menuitems([
                ('filemenu', 'load'),
                ('devicemenu', 'disconnect'),
                ('devicemenu', 'start_realtime'),
                ('devicemenu', 'get_storage'),
                ])

            self.root.thread_exception = False
            return

        # plot data
        self.plot(
            end=self.data['count'], samplerate=self.plot_samplerate, cap=True)

        # loop
        self.root.after(self.plot_refreshrate, self.plot_loop)

    def resize_plot(self):
        self.plot(
            end=self.data['count'], samplerate=self.plot_samplerate,
            limit=False)


class ThreadedRealtimeData(threading.Thread):

    def __init__(self, root, oximeter, data):
        threading.Thread.__init__(self)
        self.root = root
        self.oximeter = oximeter
        self.data = data

    def run(self):
        try:

            # get data
            if self.data['testdata']:
                datapoints = test_realtime()
            else:
                datapoints = self.oximeter.get_realtime_data()
            for datapoint in datapoints:

                # gracious thread end
                if getattr(self.root, 'stop_thread', False):
                    break

                # expand data if running out of allocated space
                if len(self.data['time']) == self.data['count']:
                    for key in self.data:
                        if isinstance(self.data[key], list):
                            self.data[key] += [0] * 100000

                # add data
                idx = self.data['count']
                self.data['point'][idx] = datapoint
                self.data['time'][idx] = datapoint.time

                spO2 = np.nan
                if datapoint.spO2:
                    spO2 = datapoint.spO2
                self.data['spO2'][idx] = spO2
                pulse_rate = np.nan
                if datapoint.pulse_rate:
                    pulse_rate = datapoint.pulse_rate
                self.data['pulse_rate'][idx] = pulse_rate
                pulse_waveform = np.nan
                if datapoint.pulse_waveform:
                    pulse_waveform = datapoint.pulse_waveform
                self.data['pulse_waveform'][idx] = pulse_waveform
                self.data['pulse_beep'][idx] = datapoint.pulse_beep
                self.data['bar_graph'][idx] = datapoint.bar_graph
                self.data['pi'][idx] = datapoint.pi
                self.data['signal_strength'][idx] = datapoint.signal_strength
                self.data['probe_error'][idx] = datapoint.probe_error
                self.data['low_spO2'][idx] = datapoint.low_spO2
                self.data[
                    'searching_too_long'][idx] = datapoint.searching_too_long
                self.data['searching_pulse'][idx] = datapoint.searching_pulse
                self.data['spO2_invalid'][idx] = datapoint.spO2_invalid
                self.data[
                    'pulse_rate_invalid'][idx] = datapoint.pulse_rate_invalid
                self.data['pi_valid'][idx] = datapoint.pi_valid
                self.data['pi_invalid'][idx] = datapoint.pi_invalid
                self.data['reserved'][idx] = datapoint.reserved

                # calculate samplerate
                if self.data['count'] > 1:
                    start = self.data['time'][0]
                    end = self.data['time'][self.data['count']]
                    seconds = (end - start).total_seconds()
                    self.data['samplerate'] = self.data['count'] / seconds

                # count datapoint
                self.data['count'] += 1

        except Exception as e:
            self.root.thread_exception = True
            messagebox.showerror(parent=self.root, title='Error:', message=e)


def start_gui(port, testdata=False):
    gui = CMS50DplusGui(port=port, testdata=testdata)
    gui.start()


def print_realtime_data(port, testdata=False):
    print("Saving live data...")
    print("Press CTRL-C / disconnect the device to terminate data collection.")
    if testdata:
        datapoints = test_realtime()
    else:
        oximeter = CMS50Dplus(port)
        datapoints = oximeter.get_realtime_data()
    try:
        for datapoint in datapoints:
            sys.stdout.write(
                "\rSignal: {:>2}"
                " | PulseRate: {:>3}"
                " | PulseWave: {:>3}"
                " | SpO2: {:>2}%"
                " | ProbeError: {:>1}".format(
                    datapoint.signal_strength,
                    datapoint.pulse_rate,
                    datapoint.pulse_waveform,
                    datapoint.spO2,
                    datapoint.probe_error))
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass


def dump_realtime_data(port, filename, testdata=False):
    print("Saving live data...")
    print("Press CTRL-C / disconnect the device to terminate data collection.")
    if testdata:
        datapoints = test_realtime()
    else:
        oximeter = CMS50Dplus(port)
        datapoints = oximeter.get_realtime_data()
    measurements = 0
    try:
        with open(filename, 'w') as csvfile:
            writer = csv.writer(csvfile, quoting=csv.QUOTE_NONNUMERIC)
            writer.writerow(RealtimeDataPoint.get_csv_header())
            for datapoint in datapoints:
                writer.writerow(datapoint.get_csv_data())
                measurements += 1
                sys.stdout.write(
                    "\rGot {0} measurements...".format(measurements))
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass


def dump_storage_data(port, filename, starttime, testdata=False):
    print("Saving recorded data...")
    print("Please wait as the latest session is downloaded...")
    if testdata:
        datapoints = test_storage(starttime=starttime)
    else:
        oximeter = CMS50Dplus(port)
        datapoints = oximeter.get_storage_data(starttime)
    measurements = 0
    try:
        with open(filename, 'w') as csvfile:
            writer = csv.writer(csvfile, quoting=csv.QUOTE_NONNUMERIC)
            writer.writerow(StorageDataPoint.get_csv_header())
            for datapoint in datapoints:
                writer.writerow(datapoint.get_csv_data())
                measurements += 1
                sys.stdout.write(
                    "\rGot {0} measurements...".format(measurements))
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass


def valid_datetime(s):
    try:
        return dateparser.parse(s)
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Contec CMS50D+ v7.0 Data Interface "
                    "(c) 2020 Alexander Blum, (c) 2015 atbrask")
    parser.add_argument(
        "-c", "--cli", action='store_true',
        help="Use CLI mode.")
    parser.add_argument(
        "-p", "--port", default="/dev/ttyUSB0",
        help="Virtual serial port of the device.")
    parser.add_argument(
        "-d", "--datatype", choices=["realtime", "storage"],
        default="realtime", help="Type of data.")
    parser.add_argument(
        "-f", "--filename",
        help="Output CSV file.")
    parser.add_argument(
        "-s", "--starttime", type=valid_datetime,
        help="Start time for storage mode data [any parsable format].")
    parser.add_argument(
        "-t", "--testdata", action='store_true',
        help="Use testdata, do not connect to the device.")
    args = parser.parse_args()

    # gui
    if not args.cli:
        start_gui(args.port, testdata=args.testdata)
        exit()

    # cli
    if args.datatype == 'realtime':
        if not args.filename:
            print_realtime_data(args.port, testdata=args.testdata)
        else:
            dump_realtime_data(
                args.port, args.filename, testdata=args.testdata)
        print("\nDone.")

    if args.datatype == 'storage':
        if not args.starttime:
            args.starttime = datetime.datetime.now()
        if not args.filename:
            args.filename = "{}-{}.csv".format(
                args.datatype, args.starttime.strftime("%Y%m%d-%H%M%S"))
        dump_storage_data(
            args.port, args.filename, args.starttime, testdata=args.testdata)
        print("\nDone.")
