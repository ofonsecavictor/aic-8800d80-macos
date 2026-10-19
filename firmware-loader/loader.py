#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# macOS port of initialization logic from radxa-pkg/aic8800 @ e9e43ed79c50483080e9bcdfb08caeeb869d7191.
# Reference files: aicbluetooth.c, aicbluetooth_cmds.c, aic_compat_8800d80.c.
# Original command queue copyright (C) RivieraWaves 2014-2019.
import argparse, ctypes, hashlib, json, pathlib, struct, sys, time, traceback
ROOT=pathlib.Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else pathlib.Path(__file__).resolve().parent
u32=lambda data: struct.unpack('<I',data)[0]
pack=lambda *values: struct.pack('<'+'I'*len(values),*values)
FILES=['fw_patch_table_8800d80_u02.bin','fw_adid_8800d80_u02.bin','fw_patch_8800d80_u02.bin','fw_patch_8800d80_u02_ext0.bin','fmacfw_8800d80_u02.bin']

def parse_table(blob):
    if len(blob)<16 or blob[:16]!=b'AICBT_PT_TAG'.ljust(16,b'\0'):
        raise ValueError('Invalid Bluetooth patch table tag')
    result=[];offset=16
    while offset<len(blob):
        if len(blob)-offset<24: raise ValueError('Truncated table header')
        name=blob[offset:offset+16].rstrip(b'\0').decode('ascii')
        kind,count=struct.unpack_from('<II',blob,offset+16);offset+=24
        if kind>6 or count>256 or offset+8*count>len(blob): raise ValueError('Invalid table length/type')
        values=list(struct.unpack_from('<'+'I'*(count*2),blob,offset));offset+=8*count
        result.append((name,kind,values))
    if not result or result[0][1]!=0 or len(result[0][2])!=12: raise ValueError('Unsupported patch info')
    return result

def prepare(directory):
    manifest=json.loads((ROOT/'firmware-manifest.json').read_text())
    images={}
    for name in FILES:
        blob=(directory/name).read_bytes();meta=manifest['files'][name]
        if len(blob)!=meta['size'] or hashlib.sha256(blob).hexdigest()!=meta['sha256']:
            raise ValueError('Firmware content mismatch: '+name)
        images[name]=blob
    table=parse_table(images[FILES[0]])
    info=table[0][2]
    if info[1]!=0x201940 or info[3]!=0x1e0000 or info[9]!=1 or info[10]!=0 or info[11]!=0x20b43c:
        raise ValueError('Unexpected firmware load addresses')
    # The upstream unpacker truncates the info entry to four base pairs.
    table[0]=(table[0][0],0,info[:8])
    for name,kind,values in table:
        if kind==3:
            if len(values)<18: raise ValueError('Truncated BT config')
            defaults=[1,0xffffffff,0,5,1,1500000,1,0,0x6f2f]
            for i,value in enumerate(defaults):values[2*i+1]=value
        if kind!=6:
            for addr in values[::2]:
                if addr%4 or not (0x100000<=addr<0x300000 or 0x40000000<=addr<0x41000000):
                    raise ValueError('Unexpected patch write address')
    return images,table

class DeviceNotReady(RuntimeError):pass

class Device:
    def __init__(self):
        self.lib=ctypes.CDLL(str(ROOT/'libaicusb.dylib'))
        self.lib.aic_open.restype=ctypes.c_void_p
        self.lib.aic_close.argtypes=[ctypes.c_void_p]
        self.lib.aic_rpc.argtypes=[ctypes.c_void_p,ctypes.c_uint16,ctypes.c_void_p,ctypes.c_uint16,ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32)]
        self.lib.aic_rpc.restype=ctypes.c_uint32
        self.lib.aic_location.argtypes=[ctypes.c_void_p]
        self.lib.aic_location.restype=ctypes.c_uint32
        self.handle=self.lib.aic_open()
        if not self.handle:raise DeviceNotReady('AIC Wlan a69c:8d80 not accessible')
        self.location=self.lib.aic_location(self.handle)
    def close(self):
        if self.handle:self.lib.aic_close(self.handle);self.handle=None
    def rpc(self,msg,payload):
        result=ctypes.create_string_buffer(2048);size=ctypes.c_uint32(2048)
        r=self.lib.aic_rpc(self.handle,msg,payload,len(payload),result,ctypes.byref(size))
        if r:raise RuntimeError(f'USB RPC {msg:04x}: {r:08x}')
        return result.raw[:size.value]
    def read(self,address):
        data=self.rpc(0x400,pack(address))
        if len(data)!=8 or u32(data[:4])!=address:raise RuntimeError('Memory read confirmation mismatch')
        return u32(data[4:])
    def write(self,address,value):
        data=self.rpc(0x402,pack(address,value))
        if len(data)!=8 or u32(data[:4])!=address:raise RuntimeError(f'Memory write confirmation mismatch at {address:08x}: {data.hex()}')
    def upload(self,address,blob,name):
        print(f'RAM upload {name}: {len(blob)} bytes @ {address:08x}',flush=True)
        for offset in range(0,len(blob),1024):
            chunk=blob[offset:offset+1024]
            confirmation=self.rpc(0x40b,pack(address+offset,len(chunk))+chunk.ljust(1024,b'\0'))
            if len(confirmation)!=4 or u32(confirmation)!=0:raise RuntimeError('Firmware block write rejected')
        if self.read(address)!=u32(blob[:4]) or self.read(address+(len(blob)//4-1)*4)!=u32(blob[(len(blob)//4-1)*4:len(blob)//4*4]):
            raise RuntimeError('Firmware readback mismatch')

def load(device,images,table):
    # Normal mode only: no flash/OTA/test-mode path is implemented.
    for name,address in [(FILES[1],0x201940),(FILES[2],0x1e0000),(FILES[3],0x20b43c)]:
        device.upload(address,images[name],name)
    for name,kind,values in table:
        if kind==6:continue
        print('Apply '+name,flush=True)
        for i in range(0,len(values),2):device.write(values[i],values[i+1])
        if kind==4:time.sleep(.1)
    time.sleep(.1)
    device.upload(0x120000,images[FILES[4]],FILES[4])
    base=device.read(0x120198);patch=device.read(0x1201a0);version=device.read(0x12001c)
    start=device.read(0x1201a4) if version>0x06090100 else 0x1d7000
    print(f'Firmware version={version:08x}, config={base:08x}, patch={patch:08x}, buffer={start:08x}',flush=True)
    for addr in [base,patch,start]:
        if addr%4 or not 0x100000<=addr<0x300000:raise RuntimeError('Firmware pointer outside RAM')
    # Upstream default without USE_5G: RX aggregate count 10, user flags 1.
    entries=[(0xb4,0xf3010000),(0x170,0x0001000a),(0x188,1)]
    for addr,value in [(patch,0x48435450),(patch+8,0x50544348),(patch+4,start),(patch+12,len(entries))]:device.write(addr,value)
    for i,(offset,value) in enumerate(entries):
        device.write(start+i*8,base+offset);device.write(start+i*8+4,value)
    for i in range(4):device.write(patch+48+i*4,0)
    print('Starting RAM firmware; USB re-enumeration must confirm success.',flush=True)
    try:
        reply=device.rpc(0x40d,pack(0x120000,1))
        print('Start confirmation: '+reply.hex(),flush=True)
    except RuntimeError as error:
        print('Start transfer ended: '+str(error)+'; checking USB transition.',flush=True)
    device.lib.aic_active_at.argtypes=[ctypes.c_uint32]
    device.lib.aic_active_at.restype=ctypes.c_uint64
    for _ in range(40):
        if device.lib.aic_active_at(device.location):
            print('CONFIRMED: AIC 8800D80 a69c:8d81 enumerated after RAM firmware start.',flush=True)
            return
        time.sleep(.25)
    raise RuntimeError('Firmware start did not produce the expected USB device')

def main():
    parser=argparse.ArgumentParser(description='Experimental macOS AIC8800D80 U03 RAM firmware loader')
    parser.add_argument('--firmware-dir',type=pathlib.Path)
    parser.add_argument('--load',action='store_true')
    parser.add_argument('--plan',action='store_true')
    parser.add_argument('--watch',action='store_true')
    args=parser.parse_args()
    images=table=None
    if args.load or args.plan or args.watch:
        if not args.firmware_dir:parser.error('--firmware-dir is required')
        images,table=prepare(args.firmware_dir)
        print('All five firmware hashes, table boundaries and load addresses validated.',flush=True)
        if args.plan:
            for name,blob in images.items():print(name,len(blob))
            return
    if args.watch:
        lib=ctypes.CDLL(str(ROOT/'libaicusb.dylib'));lib.aic_loader_id.restype=ctypes.c_uint64
        last=0
        print('Waiting for the verified AIC firmware-loading device.',flush=True)
        while True:
            session=lib.aic_loader_id()
            if session and session!=last:
                last=session
                device=None
                try:
                    device=Device()
                    if device.read(0x40500000)!=0xf3078820:raise RuntimeError('Unknown chip; not loaded')
                    load(device,images,table)
                except DeviceNotReady:
                    # Device enumeration precedes interface readiness. Retry
                    # opening only; failed firmware writes are never retried.
                    last=0
                    print('AIC USB interface not ready; retrying in 3 seconds.',flush=True)
                except Exception:
                    traceback.print_exc()
                    print('Stopped for this USB session; retry requires reconnect.',flush=True)
                finally:
                    if device:device.close()
            if not session:last=0
            time.sleep(3)
    device=Device()
    try:
        value=device.read(0x40500000)
        print(f'Chip register={value:08x}, revision={(value>>16)&255:02x}',flush=True)
        if value!=0xf3078820:raise RuntimeError('Chip revision differs from verified hardware; stopped')
        if args.load:load(device,images,table)
    finally:device.close()
if __name__=='__main__':main()
