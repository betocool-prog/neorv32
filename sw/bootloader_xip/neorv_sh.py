#!/usr/bin/env python

import serial
import cmd
import struct
import time

class CLI(cmd.Cmd):

    intro = "Command line interpreter for NEORV32 Bootloader"
    prompt = 'neorv_sh>>>'

    def __init__(self):
        
        # Initialise the Command Line Interface
        self.client = Client()
        super().__init__()

    def do_execute(self, arg):
        '''execute
        Start application execution using XIP'''
        self.client.execute()

    def do_flash_write(self, arg):
        '''flash_write addr(hex or int) filename
        Examples:
        - flash_write 0x0 ./main.bin
        - flash_write 0x2000 ../folder_to/main.bin'''
        self.client.flash_write(arg)

    def do_status_byte(self, arg):
        '''status_byte
        Reads flash status byte'''
        self.client.status_byte()

    def do_flash_read(self, arg):
        '''flash_read addr(hex or int) length_in_bytes(hex or int)
        Examples:
        - flash_read 0x2000 128
        - flash_read 1024 0x100'''
        self.client.flash_read(arg)

    def do_status(self, arg):
        '''status
        Returns bootloader status information'''
        self.client.status()

    def do_reset(self, arg):
        '''reset
        Reset bootloader'''
        self.client.reset()

    def do_poke(self, arg):
        '''poke
        Sends a 0x00 character to the serial port'''
        self.client.poke_bl()

    def do_erase_sector(self, arg):
        '''erase_sector addr(hex or int)
        Examples:
        - erase_sector 0x10000
        - erase_sector 1024'''
        self.client.erase_sector(arg)

    def do_exit(self, arg):
        '''exit
        Exits the application'''
        print("")
        return True


class Client:

    POKE = b'\x00'
    EXECUTE = b'\x01'
    FLASH_WRITE = b'\x02'
    FLASH_READ = b'\x03'
    RESET = b'\x04'
    STATUS = b'\x05'
    ERASE_SECTOR = b'\x06'
    STATUS_BYTE = b'\x07'

    SECTORS = 128
    SECTOR_SIZE = 0x10000
    FLASH_SIZE = SECTORS * SECTOR_SIZE

    def __init__(self):
        
        # Initialise Serial port
        try:
            self.ser = serial.Serial(port='/dev/ttyUSB0', baudrate=19200,
                                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                                bytesize=serial.EIGHTBITS, timeout=1)
        except Exception as e:
            print("Could not open serial port{}: ".format(repr(e)))
            exit(1)

        self.poke_bl()

    def to_int(self, text):
        ret_Val = None
        try:
            if text[0:2] == '0x':
                ret_Val = int(text, 16)
            else:
                ret_Val = int(text, 10)
        except Exception as e:
            print("Bad number format, e.g.: use 0x10 or 16")
        
        return ret_Val

    def execute(self):
        self.ser.write(self.EXECUTE)
        reply = self.ser.read()
        print("Reply: {}".format(reply))

    def status_byte(self):
        self.ser.write(self.STATUS_BYTE)
        reply = self.ser.read(1)
        print("Reply: {}".format(reply))

    def flash_write_page(self, addr, data):
        # This function writes 256 bytes or less only!
        self.ser.write(self.FLASH_WRITE)
        self.ser.write(struct.pack("<I", addr))
        self.ser.write(struct.pack("<I", len(data)))
        self.ser.write(data)
        self.ser.read(1)
        
    def flash_write(self, arg):

        arg = arg.split(' ')
        
        if len(arg) != 2:
            print("Start address and file name required!")
            return

        addr = self.to_int(arg[0])
        if addr == None:
            return
        
        # Open file to write
        try:
            fd = open(arg[1], 'rb')
        except Exception as e:
            print("Could not open file: {}".format(repr(e)))
            return
        else:
            data = fd.read()
            fd.close()

        # Confirm data fits into flash
        data_len = len(data)
        if (addr + data_len) > self.FLASH_SIZE:
            print("Data size exceeds memory size!")
            return

        # Check which sectors need to be erased. That depends on the 
        # start address and data length.
        start_sector = addr >> 16
        stop_sector = (addr + data_len) >> 16

        for sector in range(start_sector, stop_sector + 1):
            # Reusing erase sector command... it uses string as input!
            self.erase_sector(sector << 16)
            print("Sector {} erased...".format(sector))

        start = 0
        step = 256 # This is the block of data we're sending in one go!
        stop = step
        while stop <= data_len:
            self.flash_write_page(addr, data[start:stop])
            print("{:.1f}%\r".format(stop * 100 / data_len), end='')
            start = stop
            stop += step
            addr += step

        self.flash_write_page(addr, data[start:])
        
        print("100.0%")            
        print("Finished writing {} bytes...".format(data_len))


    def flash_read(self, arg):

        args = arg.split(' ')
        
        if len(args) != 2:
            print("Need to provide address and length!")
            return
        
        addr = self.to_int(args[0])
        data_len = self.to_int(args[1])

        if None in [addr, data_len]:
            return

        self.ser.write(self.FLASH_READ)
        self.ser.write(struct.pack("<I", addr))
        self.ser.write(struct.pack("<I", data_len))
        reply = self.ser.read(data_len)
        
        # Format the output
        print()
        start = 0
        step = 16 # Change this to print more or less values per line
        stop = step
        addr_text = "0x{:08x}: "
        while stop <= data_len:
            text = addr_text + (stop - start) * "{:02X} "
            print(text.format(addr + start, *(reply[start:stop])))
            start = stop
            stop += step

        if (data_len - start) > 0:
            text = addr_text + (data_len - start) * "{:02X} "
            print(text.format(addr + start, *(reply[start:data_len])))

        print()

    def erase_sector(self, arg):

        addr = None

        if(type(arg) == str):
            addr = self.to_int(arg)
        elif(type(arg) == int):
            addr = arg

        if addr == None:
            return

        self.ser.write(self.ERASE_SECTOR)
        self.ser.write(struct.pack('<I', addr))
        reply = self.ser.read(1)
        print("Reply: {}".format(reply))

    def status(self):
        self.ser.write(self.STATUS)
        reply = self.ser.read(8)
        print("Reply: {}".format(reply))

    def reset(self):
        self.ser.write(self.RESET)
        reply = self.ser.read()
        print("Reply: {}".format(reply))

    def poke_bl(self):
        self.ser.write(self.POKE)
        reply = self.ser.read()
        print("Reply: {}".format(reply))


if __name__ == "__main__":

    neorv_sh = CLI()
    neorv_sh.cmdloop()