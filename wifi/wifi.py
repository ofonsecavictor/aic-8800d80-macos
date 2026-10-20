#!/usr/bin/python3
"""AIC FullMAC prototype: firmware identity and passive 2.4 GHz scanning."""
import argparse
import ctypes
from pathlib import Path
import struct
import time
import json
import queue
import threading
import subprocess
import os
import fcntl
import stat
from collections import deque
from protocol import command,messages
from layouts import passive_scan,network,connect_request,channel_to_frequency,frequency_to_channel,frequency_band,connectable_frequency
from reports import write_report
from wpa2 import Supplicant,pmk,ethernet_frames,transmit_frame,key_request,parse_key,validate_rsn

HERE=Path(__file__).resolve().parent

class Wifi:
    def __init__(self):
        shared=Path('/Library/Application Support/AIC88M80Driver/.wifi-session.lock')
        lock_path=shared if shared.parent.exists() else HERE/'.wifi-session.lock'
        flags=os.O_RDONLY|os.O_NOFOLLOW
        if os.geteuid()==0 or lock_path.parent==HERE:flags|=os.O_CREAT
        lock_fd=os.open(str(lock_path),flags,0o644)
        self.lock=os.fdopen(lock_fd,'r')
        lock_info=os.fstat(lock_fd)
        if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink!=1:
            raise RuntimeError('Arquivo de controle de sessão AIC inesperado.')
        if os.geteuid()==0:
            os.fchown(self.lock.fileno(),lock_path.parent.stat().st_uid,lock_path.parent.stat().st_gid)
            os.fchmod(self.lock.fileno(),0o644)
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Outro processo AIC já está usando o Wi-Fi. Encerre a sessão anterior.')
        self.lib=lib=ctypes.CDLL(str(HERE/'libaicwifi.dylib'))
        lib.wifi_open.argtypes=[ctypes.POINTER(ctypes.c_uint32)];lib.wifi_open.restype=ctypes.c_void_p
        lib.wifi_close.argtypes=[ctypes.c_void_p]
        lib.wifi_location.argtypes=[ctypes.c_void_p];lib.wifi_location.restype=ctypes.c_uint32
        lib.wifi_registry_id.argtypes=[ctypes.c_void_p];lib.wifi_registry_id.restype=ctypes.c_uint64
        lib.wifi_write.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32];lib.wifi_write.restype=ctypes.c_uint32
        lib.wifi_read.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32)];lib.wifi_read.restype=ctypes.c_uint32
        lib.wifi_read_data.argtypes=lib.wifi_read.argtypes;lib.wifi_read_data.restype=ctypes.c_uint32
        lib.wifi_write_data.argtypes=lib.wifi_write.argtypes;lib.wifi_write_data.restype=ctypes.c_uint32
        error=ctypes.c_uint32();self.handle=lib.wifi_open(ctypes.byref(error))
        if not self.handle and error.value==0xe00002c0:
            print('Aguardando o serviço inicializar o AIC na porta USB...',flush=True)
            deadline=time.monotonic()+15
            while not self.handle and error.value==0xe00002c0 and time.monotonic()<deadline:
                time.sleep(0.5);self.handle=lib.wifi_open(ctypes.byref(error))
        if not self.handle:raise RuntimeError('Cannot open AIC Wi-Fi interface: %08x'%error.value)
        self.events=deque()
        self.test_ip=False
        self.native_connect=False;self.native_stop=threading.Event()
        self.kernel_session=None;self.kernel_poll=None;self.scan_observer=None;self.control_observer=None
        self.radio_observer=None;self.association_observer=None;self.lease_observer=None
        self.scan_requested=threading.Event();self.active_vif=None
        self.connected_scan=False;self.connected_scan_deadline=0;self.connected_results={}
        self.rx_diagnostics={'records':0,'malformed':0,'ethernet_frames':0,'hardware':{},'ether_types':{}}
        self.tx_sequence=0;self.tx_confirmations={}
        self.rx=queue.Queue(maxsize=128);self.control_rx=queue.Queue(maxsize=128)
        self.stop_rx=threading.Event()
        self.reader=threading.Thread(target=self._receive_data,daemon=True);self.reader.start()
        self.control_reader=threading.Thread(target=self._receive_control,daemon=True);self.control_reader.start()
        print('AIC Wi-Fi interface 2 opened at %08x'%lib.wifi_location(self.handle),flush=True)

    def close(self):
        if self.handle:
            self.stop_rx.set();self.reader.join();self.control_reader.join()
            self.lib.wifi_close(self.handle);self.handle=None
        self.lock.close()

    def _receive_data(self):
        # The reference keeps data IN URBs active throughout initialization and
        # scanning, not just while waiting for EAPOL. Drain this independent pipe.
        while not self.stop_rx.is_set():
            data=ctypes.create_string_buffer(65536);length=ctypes.c_uint32(len(data))
            status=self.lib.wifi_read_data(self.handle,data,ctypes.byref(length))
            if status in (0xe00002d6,0xe0004051):continue
            item=RuntimeError('USB data read: %08x'%status) if status else data.raw[:length.value]
            if not status and len(item)>=4 and item[2]&0x7f==0x12:
                for _,body in messages(item):
                    value,index=struct.unpack('<II',body);self.tx_confirmations[index]=value
                continue
            try:self.rx.put_nowait(item)
            except queue.Full:
                try:self.rx.get_nowait()
                except queue.Empty:pass
                self.rx.put_nowait(item)
            if status:return

    def _receive_control(self):
        # ReadPipeTO's short idle timeout still blocks about 0.55 s on this
        # Mac. Only this worker owns control IN; the packet pump never waits
        # on it. Command confirmations and indications retain their order.
        while not self.stop_rx.is_set():
            buffer=ctypes.create_string_buffer(65536);length=ctypes.c_uint32(len(buffer))
            status=self.lib.wifi_read(self.handle,buffer,ctypes.byref(length))
            if status in (0xe00002d6,0xe0004051):continue
            try:
                if status:raise RuntimeError('USB read: %08x'%status)
                result=[]
                for msg,body in messages(buffer.raw[:length.value]):
                    if msg==0x10000:
                        value,index=struct.unpack('<II',body);self.tx_confirmations[index]=value
                    else:result.append((msg,body))
                if not result:continue
                item=result
            except (RuntimeError,ValueError) as error:item=error
            try:self.control_rx.put_nowait(item)
            except queue.Full:
                self.control_rx.get_nowait()
                self.control_rx.put_nowait(RuntimeError('Fila de controle USB AIC excedida.'))
                return
            if isinstance(item,Exception):return

    def read(self,poll=False):
        try:item=self.control_rx.get(timeout=0 if poll else 0.05)
        except queue.Empty:return []
        if isinstance(item,Exception):raise item
        return item

    def receive_native(self):
        # Drain a bounded batch without a synchronous USB control read between
        # data records. Neither an idle control pipe nor a burst may stall TCP.
        if self.active_vif is not None and self.scan_requested.is_set() and not self.connected_scan:
            self.scan_requested.clear()
            frame=command(0x1000,passive_scan(self.active_vif))
            status=self.lib.wifi_write(self.handle,ctypes.create_string_buffer(frame),len(frame))
            if status:print('AIC: busca de redes indisponível: %08x'%status,flush=True)
            else:
                self.connected_scan=True;self.connected_scan_deadline=time.monotonic()+35
                self.connected_results={}
        for _ in range(128):
            events=list(self.events);self.events.clear()
            if not events:events=self.read(poll=True)
            if not events:break
            for msg,body in events:
                if msg==0x1805:
                    raise RuntimeError('AP desconectou a estação AIC: '+body.hex())
                if self.connected_scan and msg==0x1004:
                    item=network(body)
                    if item:self.connected_results[item['bssid']]=item
                elif self.connected_scan and msg==0x1001:
                    results=self.connected_results.copy()
                    ssid=self.current_ssid
                    self.connected_scan=False
                    threading.Thread(target=self.publish_networks,args=(results,ssid),daemon=True).start()
                elif self.connected_scan and msg==0x1009 and body[:1]!=b'\x00':
                    self.connected_scan=False
                    print('AIC: busca com enlace ativo recusada: '+body.hex(),flush=True)
                if self.control_observer:self.control_observer(msg,body)
        if self.connected_scan and time.monotonic()>self.connected_scan_deadline:
            self.connected_scan=False
            print('AIC: busca com enlace ativo expirou.',flush=True)
        frames=[]
        for _ in range(32):
            data=self.data_read(0)
            if not data:break
            frames.extend(ethernet_frames(data))
        return frames

    def request(self,message_id,payload=b'',confirmation=None):
        frame=command(message_id,payload)
        status=self.lib.wifi_write(self.handle,ctypes.create_string_buffer(frame),len(frame))
        if status:raise RuntimeError('USB write %04x: %08x'%(message_id,status))
        expected=message_id+1 if confirmation is None else confirmation
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            answer=None
            for response,body in self.read():
                if response==expected:answer=body
                else:self.events.append((response,body))
            if answer is not None:return answer
        raise RuntimeError('Confirmation %04x timed out'%expected)

    def identity(self):
        body=self.request(4)
        if len(body)!=28:raise RuntimeError('Unexpected version confirmation size')
        vals=struct.unpack('<6IHBx',body)
        self.mac=self.request(0x73,struct.pack('<I',1))[:6]
        if len(self.mac)!=6 or self.mac[0]&1 or not any(self.mac):raise RuntimeError('Invalid hardware MAC')
        self.info={'location':'%08x'%self.lib.wifi_location(self.handle),
             'lmac_version':'%08x'%vals[0],'mac_hw':['%08x'%x for x in vals[1:3]],
             'phy':['%08x'%x for x in vals[3:5]],'features':'%08x'%vals[5],
             'max_stations':vals[6],'max_interfaces':vals[7],
             'mac':':'.join('%02x'%x for x in self.mac)}
        return self.info

    def publish_networks(self,results,configured_ssid,merge_existing=False):
        public=[];known={}
        for item in sorted(results.values(),key=lambda value:value['rssi'],reverse=True):
            if not item.get('ssid'):continue
            frequency=item.get('frequency')
            channel=frequency_to_channel(frequency)
            band=frequency_band(frequency)
            if item['ssid'] not in known:
                if os.geteuid()==0 and not getattr(self,'research_probe',False):
                    try:
                        saved=subprocess.run([str(HERE/'aic-wifi-credential'),'--read',item['ssid']],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
                        known[item['ssid']]=saved.returncode==0
                    except subprocess.TimeoutExpired:known[item['ssid']]=False
                else:known[item['ssid']]=False
            public.append({'ssid':item['ssid'],'rssi':item['rssi'],'channel':channel,
                           'band':'5 GHz' if band==1 else ('2.4 GHz' if band==0 else None),
                           'band_id':band,'known':known[item['ssid']],
                           'connectable':connectable_frequency(frequency),
                           'secured':bool(item.get('rsn'))})
        if merge_existing:
            try:
                previous=json.loads((HERE/'redes-disponiveis.json').read_text())
                fresh={(item['ssid'],item['band_id']) for item in public}
                public.extend(item for item in previous.get('networks',[])
                    if (item.get('ssid'),item.get('band_id')) not in fresh)
                public.sort(key=lambda item:item.get('rssi',-100),reverse=True)
            except (OSError,ValueError,TypeError):pass
        write_report(HERE/'redes-disponiveis.json',
            {'updated_unix':time.time(),'configured_ssid':configured_ssid or '',
             'configured_band':getattr(self,'target_band',None),'networks':public},mode=0o644)

    def scan(self,probe_ssid=None,auth_key=None,*,scan_frequencies=None,publish_results=True):
        if self.info['lmac_version']!='06090101':raise RuntimeError('Untested firmware revision')
        if scan_frequencies is not None:
            if probe_ssid is not None or not scan_frequencies or len(scan_frequencies)>42 or any(
                    frequency_to_channel(value) is None for value in scan_frequencies):
                raise ValueError('Invalid native scan frequency plan')
            scan_frequencies=tuple(dict.fromkeys(scan_frequencies))
        vif=None;scanning=False
        try:
            self.initialize_radio()
            if getattr(self,'radio_observer',None):self.radio_observer(True,None,self.mac)
            self.request(0)
            self.request(2,bytes(64)+struct.pack('<IH2x',300,20))
            # CONFIG_COEX reference rwnx_open: BT on, coexistence NULL CTS on.
            self.request(0x65,struct.pack('<5B3x2I',1,0,1,0,0,0,0))
            body=self.request(6,struct.pack('<Bx6sBx',0,self.mac,0))
            if len(body)<2 or body[0]!=0:raise RuntimeError('Wi-Fi station creation failed: '+body.hex())
            vif=body[1]
            band=getattr(self,'target_band',None) if probe_ssid is not None else None
            cached=[]
            if probe_ssid is not None and self.scan_observer is None:
                try:
                    previous=json.loads((HERE/'redes-disponiveis.json').read_text())
                    for item in previous.get('networks',[]):
                        if item.get('ssid')!=probe_ssid or item.get('band_id')!=band:continue
                        frequency=channel_to_frequency(item.get('channel'),band)
                        if frequency and connectable_frequency(frequency) and frequency not in cached:
                            cached.append(frequency)
                except (OSError,ValueError,TypeError):pass
            plans=[scan_frequencies] if scan_frequencies is not None else (
                [cached[:3],None] if cached else [None])
            results={};target=None;fast=False
            for frequencies in plans:
                if self.native_stop.is_set():raise KeyboardInterrupt
                print('Wi-Fi station %u scanning %s.'%(vif,
                    'cached channels '+str(frequencies) if frequencies else 'selected band'),flush=True)
                ack=self.request(0x1000,passive_scan(vif,band,frequencies),confirmation=0x1009)
                if ack[:1]!=b'\x00':raise RuntimeError('Scan refused: '+ack.hex())
                scanning=True
                current={};done=False;scan_status=None
                deadline=time.monotonic()+(max(8,min(30,2+len(frequencies)*.7))
                                           if frequencies else 30)
                while not done and time.monotonic()<deadline:
                    if self.native_stop.is_set():raise KeyboardInterrupt
                    if self.kernel_poll:self.kernel_poll()
                    events=list(self.events);self.events.clear()
                    if not events:events=self.read()
                    for msg,body in events:
                        if msg==0x1004:
                            item=network(body,include_beacon=self.scan_observer is not None)
                            if item:
                                if self.scan_observer:self.scan_observer(item)
                                current[item['bssid']]=item
                        elif msg==0x1001:
                            print('Scan completion: '+body.hex(),flush=True)
                            scan_status=body;done=True
                if not done:raise RuntimeError('Scan completion timed out')
                if not scan_status or scan_status[0]!=0:
                    raise RuntimeError('Scan completion failed: '+(scan_status or b'').hex())
                scanning=False
                results=current
                if probe_ssid is None:break
                target=next((v for v in sorted(results.values(),key=lambda v:v['rssi'],reverse=True)
                    if v['ssid']==probe_ssid
                    and (band is None or frequency_band(v.get('frequency'))==band)
                    and (not getattr(self,'target_bssid',None) or v['bssid']==self.target_bssid)),None)
                if target is not None:
                    fast=frequencies is not None
                    break
            if self.control_observer:self.control_observer(0x1001,scan_status)
            if publish_results:
                self.publish_networks(results,probe_ssid,merge_existing=fast)
            if probe_ssid is not None:
                if target is None:raise RuntimeError('Selected network not found')
                self.probe(vif,target,auth_key)
            return sorted(({k:v for k,v in item.items() if not k.startswith('_')} for item in results.values()),key=lambda v:v['rssi'],reverse=True)
        finally:
            if vif is not None:
                if scanning:
                    try:self.request(0x100a)
                    except RuntimeError:pass
                self.request(8,bytes([vif]))
                self.request(0) # Reference rwnx_close: reset Wi-Fi MAC after last VIF.
            if getattr(self,'radio_observer',None):self.radio_observer(False,None,self.mac)

    def initialize_radio(self):
        # Linux does RF initialization on USB probe, not each interface open.
        # Registry ID plus boot time distinguishes reconnects and reboots.
        state={'boot':subprocess.check_output(['/usr/sbin/sysctl','-n','kern.boottime'],text=True).strip(),
               'registry_id':self.lib.wifi_registry_id(self.handle),'firmware':self.info['lmac_version']}
        path=HERE/'radio-state.json'
        try:previous=json.loads(path.read_text())
        except (OSError,ValueError):previous=None
        if previous==state:
            print('Wi-Fi: rádio já inicializado nesta conexão USB; sem repetir calibração.',flush=True)
            return
        body=self.request(0x7b,bytes([1,0,32,0]))
        print('Wi-Fi stack started: '+body.hex(),flush=True)
        self.request(0x77,(HERE/'power-default.bin').read_bytes())
        body=self.request(0x69,struct.pack('<5IBB2x',0x0f8f,0x0f0f,0x0c34c008,0,0x264203,0,0))
        if len(body)!=16:raise RuntimeError('Unexpected RF calibration result')
        print('Wi-Fi RF calibration confirmed (Bluetooth calibration disabled).',flush=True)
        write_report(path,state)

    def data_read(self,timeout=1):
        try:item=self.rx.get(timeout=timeout)
        except queue.Empty:return b''
        if isinstance(item,Exception):raise item
        self.rx_diagnostics['records']+=1
        if len(item)>=84:
            declared=struct.unpack_from('<H',item)[0]
            if 24<=declared<=len(item)-60:
                status=struct.unpack_from('<I',item,36)[0];flags=struct.unpack_from('<I',item,48)[0]
                fc=struct.unpack_from('<H',item,60)[0]
                key='decryption_%u_upload_%u_reorder_%u_protected_%u'%((status>>2)&7,bool(flags&64),bool(flags&32),bool(fc&0x4000))
                counters=self.rx_diagnostics['hardware'];counters[key]=counters.get(key,0)+1
        try:decoded=list(ethernet_frames(item))
        except ValueError:
            # As in the Linux reference, discard an invalid RX record rather
            # than interpreting bytes beyond its declared bounds.
            self.rx_diagnostics['malformed']+=1;return b''
        self.rx_diagnostics['ethernet_frames']+=len(decoded)
        for frame in decoded:
            key=frame[12:14].hex();counters=self.rx_diagnostics['ether_types']
            if key not in counters and len(counters)>=16:key='other'
            counters[key]=counters.get(key,0)+1
        return item

    def data_write(self,ethernet,vif,station,label='EAPOL',quiet=False,require_confirmation=True):
        index=self.tx_sequence
        if require_confirmation:self.tx_sequence+=1
        frame=transmit_frame(ethernet,vif,station,(0x80000000|index) if require_confirmation else 0)
        status=self.lib.wifi_write_data(self.handle,ctypes.create_string_buffer(frame),len(frame))
        if status:raise RuntimeError('USB data write: %08x'%status)
        if not require_confirmation:return True # Submitted to USB; no radio ACK claim.
        deadline=time.monotonic()+3
        while index not in self.tx_confirmations and time.monotonic()<deadline:
            self.events.extend(self.read())
        value=self.tx_confirmations.pop(index,None)
        if value is None:
            if quiet:return False
            raise RuntimeError('Firmware não confirmou a transmissão '+label+'.')
        if not quiet:print('TX %s: status=%08x, ACK do roteador=%s'%(label,value,'sim' if value&8 else 'não'),flush=True)
        if value&9!=9:
            if quiet:return False # Normal packet loss; the IP transport may retry.
            raise RuntimeError('Roteador não confirmou o pacote %s: %08x'%(label,value))
        return True

    def authenticate(self,vif,station,target,key,initial):
        ap=bytes.fromhex(target['bssid'].replace(':',''))
        supplicant=Supplicant(key,self.mac,ap,bytes.fromhex(target['rsn']),self.lib)
        deadline=time.monotonic()+25;pending=initial;installed=[]
        try:
            while time.monotonic()<deadline:
                if getattr(self,'kernel_poll',None):self.kernel_poll()
                data=pending or self.data_read();pending=None
                for ethernet in ethernet_frames(data):
                    if ethernet[:6]!=self.mac or ethernet[6:12]!=ap or ethernet[12:14]!=b'\x88\x8e':continue
                    response,keys=supplicant.receive(ethernet[14:])
                    info,replay,_,_=parse_key(ethernet[14:])
                    print('WPA2 RX: %s, contador=%u'%('M1' if info==0x8a else 'M3',replay),flush=True)
                    # Reference wpa_supplicant_process_3_of_4: send M4 before
                    # enabling PTK TX, then install PTK/GTK and open the port.
                    self.data_write(ap+self.mac+b'\x88\x8e'+response,vif,station)
                    if keys is not None:
                        pairwise,(index,group)=keys
                        for payload in (key_request(vif,station,pairwise),key_request(vif,255,group,index,False)):
                            body=self.request(0x24,payload)
                            if len(body)!=2 or body[0]:raise RuntimeError('Firmware refused encryption key')
                            installed.append(body[1])
                        supplicant.installed=True
                    if keys is not None:
                        self.request(0x1404,bytes([station,1]))
                        print('WPA2: MIC validado; chaves CCMP aceitas; porta de dados aberta.',flush=True)
                        if getattr(self,'radio_observer',None):self.radio_observer(True,target,self.mac)
                        if getattr(self,'association_observer',None):self.association_observer(vif,station,target)
                        result={'ssid':target['ssid'],'bssid':target['bssid'],'authentication':'WPA2-PSK-CCMP',
                                'ap_mic_verified':True,'firmware_keys_installed':True,
                                'session_closed_after_test':True,'macos_network_interface':False}
                        if self.test_ip or self.native_connect or getattr(self,'kernel_session',None):
                            def service_eapol(frame):
                                if frame[:6]!=self.mac or frame[6:12]!=ap:return
                                response,extra=supplicant.receive(frame[14:])
                                if extra is not None:raise RuntimeError('Unexpected reinstallation of encryption keys')
                                _,counter,_,_=parse_key(frame[14:])
                                print('WPA2: M3 repetida, contador=%u; reenviando M4 sem reinstalar chaves.'%counter,flush=True)
                                self.data_write(ap+self.mac+b'\x88\x8e'+response,vif,station)
                            if getattr(self,'kernel_session',None):
                                self.kernel_session(vif,station,target,service_eapol)
                                result['macos_network_interface']=True
                                return result
                            from iptest import test_link
                            lease_callback=None
                            if getattr(self,'lease_observer',None):
                                lease_callback=lambda lease,ip_result,send,receive,eapol:self.lease_observer(
                                    vif,station,lease,ip_result,send,receive,eapol)
                            result['ip_test']=test_link(
                                lambda frame:self.data_write(frame,vif,station,'dados',quiet=True),
                                lambda:list(ethernet_frames(self.data_read())),self.mac,service_eapol,
                                on_lease=lease_callback,
                                **({'keep_lease':True} if self.native_connect else {}))
                            if self.native_connect:
                                from native import connect
                                self.active_vif=vif;self.current_ssid=target['ssid']
                                result['ip_test']['_ssid']=target['ssid']
                                result['ip_test']['_band']=1 if target['frequency']>=5000 else 0
                                result['ip_test']['_transport_diagnostics']=self.rx_diagnostics
                                try:
                                    result['native_session']=connect(self.lib,
                                        lambda frame:self.data_write(frame,vif,station,'dados',quiet=True,require_confirmation=False),
                                        self.receive_native,
                                        self.mac,result['ip_test'],service_eapol,self.native_stop)
                                finally:
                                    self.active_vif=None;self.connected_scan=False
                                    result['ip_test'].pop('_lease',None)
                                    result['ip_test'].pop('_transport_diagnostics',None)
                                    result['ip_test'].pop('_ssid',None)
                                    result['ip_test'].pop('_band',None)
                        else:time.sleep(1)
                        return result
            raise RuntimeError('Autenticação expirou. Confira a senha e a proximidade do roteador.')
        finally:
            for index in reversed(installed):
                try:self.request(0x26,bytes([index]))
                except RuntimeError:pass

    def probe(self,vif,target,auth_key=None):
        rsn=bytes.fromhex(target.get('rsn',''))
        validate_rsn(rsn)
        print('Selected network: '+json.dumps({k:v for k,v in target.items() if not k.startswith('_')},ensure_ascii=True),flush=True)
        try:
            while not self.rx.empty():self.rx.get_nowait()
            body=self.request(0x1800,connect_request(vif,bytes.fromhex(target['bssid'].replace(':','')),target['ssid'],target['frequency']))
            print('Association request confirmation: '+body.hex(),flush=True)
            if body!=b'\x00':raise RuntimeError('Association request rejected')
            deadline=time.monotonic()+15;associated=False;station=None
            while time.monotonic()<deadline:
                if self.kernel_poll:self.kernel_poll()
                events=list(self.events);self.events.clear()
                if not events and not associated:events=self.read()
                for msg,body in events:
                    if msg==0x1802:
                        print('Association indication: '+body[:20].hex(),flush=True)
                        if len(body)<12 or body[:2]!=b'\x00\x00':raise RuntimeError('Association failed')
                        associated=True
                        station=body[10]
                    elif msg==0x1805:raise RuntimeError('Disconnected before authentication: '+body.hex())
                if associated:
                    data=self.data_read()
                    for eth in ethernet_frames(data):
                        if eth[12:14]!=b'\x88\x8e':continue
                        info,replay,_,_=parse_key(eth[14:])
                        if info!=0x8a:continue
                        print('EAPOL M1 recebido do roteador.',flush=True)
                        if auth_key is not None:
                            result=self.authenticate(vif,station,target,auth_key,data)
                            write_report(HERE/('resultado-ip.json' if self.test_ip else 'resultado-autenticacao.json'),result)
                            print(json.dumps(result,indent=2,ensure_ascii=False),flush=True)
                        else:
                            # Exercise data OUT with a normal EAPOL-Start, no credentials.
                            ap=bytes.fromhex(target['bssid'].replace(':',''))
                            self.data_write(ap+self.mac+b'\x88\x8e\x02\x01\x00\x00',vif,station)
                            print('EAPOL-Start enviado pelo AIC (sem senha).',flush=True)
                        return
            raise RuntimeError('Association/data receive timed out')
        finally:
            self.request(0x1803,struct.pack('<HBx',3,vif))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--scan',action='store_true');p.add_argument('--probe-ssid');p.add_argument('--authenticate',action='store_true');p.add_argument('--dhcp',action='store_true');p.add_argument('--connect',action='store_true');args=p.parse_args()
    if args.connect:
        if os.geteuid()!=0:p.error('--connect exige sudo para criar a interface virtual.')
        args.authenticate=True
    if args.dhcp and not args.authenticate:p.error('--dhcp exige --authenticate')
    key=None
    if args.authenticate:
        import getpass,sys
        if not args.probe_ssid or not sys.stdin.isatty():p.error('Autenticação exige SSID e Terminal interativo.')
        print('Teste WPA2 da rede '+args.probe_ssid+'. A senha não será gravada.')
        key=pmk(getpass.getpass('Senha do Wi-Fi: '),args.probe_ssid)
    w=None
    try:
        w=Wifi()
        w.test_ip=args.dhcp
        w.native_connect=args.connect
        if args.connect:
            import signal
            for signum in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):
                signal.signal(signum,lambda *_:w.native_stop.set())
        print(json.dumps(w.identity(),indent=2),flush=True)
        if args.scan or args.probe_ssid:print(json.dumps(w.scan(args.probe_ssid,key),indent=2,ensure_ascii=True))
    except (RuntimeError,ValueError,OSError) as error:
        print('Teste interrompido: '+str(error),flush=True)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print('Sessão AIC encerrada.',flush=True)
    finally:
        if w:w.close()
