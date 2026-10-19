"""Bounded Ethernet/WCL bridge to AICNativeWiFi; no UTUN or private IP stack."""
import ctypes as c
from collections import deque
import json
from pathlib import Path
import subprocess
import time
from layouts import network,passive_scan,frequency_to_channel
from reports import write_report

HERE=Path(__file__).resolve().parent
NOT_READY=0xe00002d8
NOT_FOUND=0xe00002f0
ABORTED=0xe00002eb

class State(c.Structure):
    _fields_=[('version',c.c_uint32),('powered',c.c_uint32),('associated',c.c_uint32),
        ('channel',c.c_uint32),('rssi',c.c_int32),('ssidLength',c.c_uint32),
        ('mac',c.c_uint8*6),('bssid',c.c_uint8*6),('ssid',c.c_uint8*32)]
class Command(c.Structure):
    _fields_=[('version',c.c_uint32),('type',c.c_uint32),('sequence',c.c_uint32),
        ('ssidLength',c.c_uint32),('ssid',c.c_uint8*32),('bssid',c.c_uint8*6),
        ('mac',c.c_uint8*6),('pmk',c.c_uint8*32),('pmkLength',c.c_uint32),('channel',c.c_uint32)]
class Beacon(c.Structure):
    _fields_=[('version',c.c_uint32),('rssi',c.c_int32),('channel',c.c_uint16),
        ('interval',c.c_uint16),('capability',c.c_uint16),('ieLength',c.c_uint16),
        ('bssid',c.c_uint8*6),('reserved',c.c_uint8*2),('ies',c.c_uint8*2048)]
class Frame(c.Structure):
    _fields_=[('length',c.c_uint32),('data',c.c_uint8*1514)]
assert tuple(c.sizeof(t) for t in (State,Command,Beacon,Frame))==(68,100,2072,1520)

class NativeError(RuntimeError):
    def __init__(self,method,status):
        self.status=status
        super().__init__('AIC nativo, operação %u: %08x'%(method,status))

class Bridge:
    def __init__(self):
        self.lib=c.CDLL(str(HERE/'libaicnative.dylib'))
        self.lib.aic_native_open.argtypes=[c.POINTER(c.c_uint32)]
        self.lib.aic_native_open.restype=c.c_uint32
        self.lib.aic_native_call.argtypes=[c.c_uint32,c.c_uint32,c.c_void_p,c.c_uint32,c.c_void_p,c.POINTER(c.c_uint32)]
        self.lib.aic_native_call.restype=c.c_uint32
        self.lib.aic_native_close.argtypes=[c.c_uint32]
        error=c.c_uint32();self.handle=self.lib.aic_native_open(c.byref(error))
        if not self.handle:raise NativeError(0,error.value)
    def call(self,method,source=None,output=None,empty=False):
        result=output() if output else None
        size=c.c_uint32(c.sizeof(result) if result is not None else 0)
        status=self.lib.aic_native_call(self.handle,method,c.byref(source) if source is not None else None,
            c.sizeof(source) if source is not None else 0,c.byref(result) if result is not None else None,c.byref(size))
        if status:
            if empty and status==NOT_READY:return None
            raise NativeError(method,status)
        if result is not None and size.value!=c.sizeof(result):raise RuntimeError('Resposta nativa AIC truncada.')
        return result
    def command(self):return self.call(0,output=Command,empty=True)
    def read(self):
        frame=self.call(4,output=Frame,empty=True)
        if frame is None:return None
        if not 14<=frame.length<=1514:raise ValueError('Quadro nativo AIC inválido.')
        return bytes(frame.data[:frame.length])
    def write(self,data):
        if not 14<=len(data)<=1514:raise ValueError('Quadro Ethernet AIC inválido.')
        frame=Frame();frame.length=len(data);frame.data[:len(data)]=data;self.call(5,frame)
    def close(self):
        if self.handle:self.lib.aic_native_close(self.handle);self.handle=0

class Transition(RuntimeError):pass

def valid_mac(data):return len(data)==6 and any(data) and not data[0]&1

def decode(command):
    """Copy secrets only for the lifetime of one pending association."""
    try:
        if command.version!=1 or command.type not in range(1,8) or command.ssidLength>32:
            raise ValueError('Comando nativo AIC inválido.')
        result={'type':command.type}
        if command.type==4:
            if not command.ssidLength or command.pmkLength!=32 or not valid_mac(bytes(command.bssid)):
                raise ValueError('Credenciais nativas AIC inválidas.')
            result.update(ssid=bytes(command.ssid[:command.ssidLength]).decode('utf-8'),
                key=bytes(command.pmk),bssid=bytes(command.bssid).hex(':'))
        if command.type==6:
            mac=bytes(command.mac)
            if not valid_mac(mac):raise ValueError('Endereço MAC nativo AIC inválido.')
            result['mac']=mac
        return result
    finally:c.memset(c.addressof(command),0,c.sizeof(command))

def beacon_for(item):
    data=item['_beacon'];ies=data['ies'];freq=item['frequency']
    channel=frequency_to_channel(freq)
    if channel is None or len(ies)>2048:
        raise ValueError('Beacon AIC fora dos limites.')
    value=Beacon();value.version=1;value.rssi=item['rssi'];value.channel=channel
    value.interval=data['interval'];value.capability=data['capability'];value.ieLength=len(ies)
    value.bssid[:]=bytes.fromhex(item['bssid'].replace(':',''));value.ies[:len(ies)]=ies
    return value

class Manager:
    def __init__(self,wifi,bridge,stop,config,key):
        self.w=wifi;self.bridge=bridge;self.stop=stop;self.config=dict(config)
        self.pending=deque();self.current=None;self.vif=None;self.scanning=False;self.scan_deadline=0
        self.join_action=None
        self.state=State();self.state.version=1;self.state.mac[:]=wifi.mac
        self.state.powered=bool(config.get('enabled',False))
        if self.state.powered:self.pending.append({'type':4,'ssid':config['ssid'],'key':key,'bssid':None})
        wifi.kernel_poll=self.poll;wifi.scan_observer=self.beacon;wifi.control_observer=self.control
        wifi.kernel_session=self.connected
    def publish(self):
        deadline=time.monotonic()+10
        while not self.stop.is_set():
            try:self.bridge.call(1,self.state);return
            except NativeError as error:
                if error.status!=NOT_READY or time.monotonic()>deadline:raise
                self.stop.wait(.1)
        raise Transition()
    def save_power(self,enabled):
        self.config['enabled']=enabled
        write_report(HERE/'profile.json',self.config)
    def collect(self):
        for _ in range(8):
            command=self.bridge.command()
            if command is None:break
            action=decode(command)
            if action['type']==1 and self.state.powered and not any(a['type']==2 for a in self.pending):
                continue # An already-on notification must not cancel association.
            if len(self.pending)>=16:raise RuntimeError('Fila nativa AIC excedida.')
            self.pending.append(action)
    def poll(self):
        self.collect()
        if self.stop.is_set():raise Transition()
        if not self.current:return
        # Scans may continue on an associated VIF; transitions wait for orderly
        # supplicant/key/VIF teardown. No composite USB reset touches Bluetooth.
        if self.current=='connected':
            while self.pending and self.pending[0]['type'] in (3,7):
                action=self.pending.popleft()
                if action['type']==3 and not self.scanning:
                    self.scanning=True;self.scan_deadline=time.monotonic()+35
                    self.w.request(0x1000,passive_scan(self.vif),confirmation=0x1009)
                elif action['type']==7 and self.scanning:
                    self.w.request(0x100a);self.scanning=False
                    self.bridge.call(3,c.c_uint32(ABORTED))
            if self.scanning and time.monotonic()>self.scan_deadline:
                self.w.request(0x100a);self.scanning=False;self.bridge.call(3,c.c_uint32(ABORTED))
        if self.pending and not (self.current=='join' and all(a['type']==3 for a in self.pending)):
            raise Transition()
    def beacon(self,item):self.bridge.call(2,beacon_for(item))
    def control(self,message,body):
        if message==0x1004:
            item=network(body,include_beacon=True)
            if item:self.beacon(item)
        elif message==0x1001:
            self.scanning=False;self.bridge.call(3,c.c_uint32(0))
    def down(self):
        self.state.associated=0;self.state.channel=0;self.state.ssidLength=0
        self.state.bssid[:]=bytes(6);self.state.ssid[:]=bytes(32);self.publish()
    def connected(self,vif,station,target,service_eapol):
        self.current='connected';self.vif=vif
        raw=target['ssid'].encode('utf-8')
        self.state.ssidLength=len(raw);self.state.ssid[:]=bytes(32);self.state.ssid[:len(raw)]=raw
        self.state.bssid[:]=bytes.fromhex(target['bssid'].replace(':',''))
        self.state.channel=frequency_to_channel(target['frequency']);self.state.rssi=target['rssi']
        # WCL queries BSS_INFO synchronously during the association notification.
        self.publish();self.beacon(target);self.state.associated=1;self.publish()
        if self.join_action:
            # The native password sheet supplies a PMK, never a plaintext password.
            # Save only after the AP's MIC and firmware key installation succeeded.
            result=subprocess.run([str(HERE/'aic-wifi-credential'),'--store',target['ssid']],
                input=self.join_action['key'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
            if result.returncode:raise RuntimeError('Não foi possível guardar a rede no Chaves do Sistema.')
            self.config.update(ssid=target['ssid'],enabled=True,credential='System Keychain')
            write_report(HERE/'profile.json',self.config)
        print('AIC: enlace Ethernet nativo autenticado; DHCP e DNS ficam a cargo do macOS.',flush=True)
        while not self.stop.is_set():
            self.poll()
            for frame in self.w.receive_native():
                if frame[12:14]==b'\x88\x8e':service_eapol(frame)
                elif len(frame)<=1514:self.bridge.write(frame)
            for _ in range(32):
                frame=self.bridge.read()
                if frame is None:break
                if frame[12:14]==b'\x88\x8e':continue # FullMAC supplicant owns the controlled port.
                self.w.data_write(frame,vif,station,'dados',quiet=True,require_confirmation=False)
            self.stop.wait(.002)
    def run(self):
        try:
            self.publish()
            while not self.stop.is_set():
                self.collect()
                if not self.pending:self.stop.wait(.05);continue
                action=self.pending.popleft();kind=action['type']
                if kind in (1,2):
                    self.state.powered=int(kind==1);self.save_power(kind==1);self.down();continue
                if kind==5:self.down();continue
                if kind==6:
                    self.w.mac=action['mac'];self.state.mac[:]=action['mac'];self.publish();continue
                if kind==7:
                    self.bridge.call(3,c.c_uint32(ABORTED));continue
                if not self.state.powered:
                    if kind==4:self.bridge.call(6,c.c_uint32(1))
                    continue
                try:
                    self.current='scan' if kind==3 else 'join'
                    self.join_action=action if kind==4 else None
                    self.scanning=True;self.w.target_bssid=action.get('bssid')
                    self.w.scan(action.get('ssid') if kind==4 else None,action.get('key'))
                except Transition:
                    if self.scanning:
                        self.scanning=False;self.bridge.call(3,c.c_uint32(ABORTED))
                except (ValueError,RuntimeError) as error:
                    # USB errors must reach the service reconnect loop.
                    if 'USB' in str(error) or isinstance(error,NativeError):raise
                    print('AIC nativo: '+str(error),flush=True)
                    self.bridge.call(6 if kind==4 else 3,c.c_uint32(1))
                finally:
                    self.current=None;self.vif=None;self.join_action=None
                    action.pop('key',None)
                    if not self.stop.is_set():self.down()
        finally:
            self.pending.clear();self.w.kernel_poll=None
            self.w.kernel_session=None;self.w.scan_observer=None;self.w.control_observer=None
            self.bridge.close()
