"""Temporary IPv4 UTUN/Ethernet bridge for the verified AIC FullMAC transport.

Uses macOS' existing UTUN kernel control, no new kernel extension. Routes
are scoped for self-test; IPv4 /1 routes are added only after bound HTTPS
succeeds. Closing the owning control socket destroys this interface.
"""
import ctypes
import errno
import ipaddress
import os
import re
import select
import socket
import struct
import subprocess
import time
from pathlib import Path
from reports import write_report
from iptest import checksum,dhcp_request,dhcp_renew,parse_dhcp

class PacketFD:
    """Use the UTUN descriptor directly, without Python socket autodetection.

    Python 3.9's socket(fileno=...) probes unsupported metadata for the
    Darwin kernel-control socket. UTUN needs only read/write/select/fcntl.
    This object owns the descriptor, including failure during initialization.
    """
    def __init__(self,fd):
        self.fd=fd
        try:os.set_blocking(fd,False)
        except OSError as error:
            try:self.close()
            except OSError:pass
            raise RuntimeError('Falha ao preparar o descritor UTUN: '+str(error)) from error

    def fileno(self):return self.fd
    def recv(self,size):return os.read(self.fd,size)
    def send(self,data):return os.write(self.fd,data)
    def close(self):
        if self.fd>=0:
            fd=self.fd;self.fd=-1;os.close(fd)

def ipv4_packet(data):
    if len(data)<20 or data[0]>>4!=4:return None
    header=(data[0]&15)*4;size=struct.unpack_from('>H',data,2)[0]
    if header<20 or size<header or size>len(data) or size>1500:return None
    if checksum(data[:header]):return None
    return data[:size]

def finalize_ipv4(data):
    """Complete IP/TCP/UDP checksums before sending raw Ethernet to FullMAC.

    UTUN records carry no hardware-checksum metadata through this bridge.
    Always calculate transport checksums from the final IPv4 pseudo-header.
    """
    if len(data)<20 or data[0]>>4!=4:return None
    header=(data[0]&15)*4;size=struct.unpack_from('>H',data,2)[0]
    if header<20 or size<header or size>len(data) or size>1500:return None
    ip=bytearray(data[:size]);ip[10:12]=bytes(2)
    struct.pack_into('>H',ip,10,checksum(ip[:header]))
    if struct.unpack_from('>H',ip,6)[0]&0x3fff:return bytes(ip)
    protocol=ip[9];payload=bytearray(ip[header:])
    if protocol==6:
        if len(payload)<20 or not 20<=((payload[12]>>4)*4)<=len(payload):return None
        offset=16
    elif protocol==17:
        if len(payload)<8 or struct.unpack_from('>H',payload,4)[0]!=len(payload):return None
        offset=6
    else:return bytes(ip)
    payload[offset:offset+2]=bytes(2)
    pseudo=ip[12:20]+bytes([0,protocol])+struct.pack('>H',len(payload))
    value=checksum(pseudo+payload)
    struct.pack_into('>H',payload,offset,value or (0xffff if protocol==17 else 0))
    return bytes(ip[:header]+payload)

def packet_metadata(ip):
    """Probe headers only; never persist TCP/UDP application payloads."""
    if len(ip)<20:return {'length':len(ip)}
    header=(ip[0]&15)*4
    info={'length':len(ip),'protocol':ip[9],
          'source':str(ipaddress.IPv4Address(ip[12:16])),
          'destination':str(ipaddress.IPv4Address(ip[16:20])),
          'ip_checksum_valid':checksum(ip[:header])==0}
    if struct.unpack_from('>H',ip,6)[0]&0x3fff:return info
    payload=ip[header:]
    if ip[9] in (6,17) and len(payload)>=8:
        info['source_port'],info['destination_port']=struct.unpack_from('>HH',payload)
        pseudo=ip[12:20]+bytes([0,ip[9]])+struct.pack('>H',len(payload))
        info['transport_checksum_valid']=checksum(pseudo+payload)==0 or (ip[9]==17 and payload[6:8]==bytes(2))
        if ip[9]==6 and len(payload)>=20:
            info['tcp_flags']=payload[13]
            info['tcp_sequence'],info['tcp_ack']=struct.unpack_from('>II',payload,4)
            info['tcp_window']=struct.unpack_from('>H',payload,14)[0]
            tcp_header=(payload[12]>>4)*4
            if 20<=tcp_header<=len(payload):
                info['tcp_data_length']=len(payload)-tcp_header
                options=[];cursor=20
                while cursor<tcp_header:
                    kind=payload[cursor];cursor+=1
                    if kind==0:break
                    if kind==1:continue
                    if cursor>=tcp_header:break
                    size=payload[cursor]
                    if size<2 or cursor-1+size>tcp_header:break
                    option={'kind':kind,'length':size}
                    if kind==2 and size==4:option['mss']=struct.unpack_from('>H',payload,cursor+1)[0]
                    elif kind==3 and size==3:option['window_scale']=payload[cursor+1]
                    elif kind==8 and size==10:
                        option['timestamp'],option['timestamp_echo']=struct.unpack_from('>II',payload,cursor+1)
                    options.append(option);cursor+=size-1
                info['tcp_options']=options
    return info

def dns_query(address,server,xid,port):
    name=b''.join(bytes([len(label)])+label for label in (b'one',)*4)+b'\x00'
    dns=struct.pack('>6H',xid,0x0100,1,0,0,0)+name+struct.pack('>HH',1,1)
    udp=struct.pack('>4H',port,53,8+len(dns),0)+dns
    ip=struct.pack('>BBHHHBBH4s4s',0x45,0,20+len(udp),0,0,64,17,0,address,server)+udp
    return finalize_ipv4(ip)

def dns_answer(ip,address,server,xid,port):
    ip=ipv4_packet(ip)
    if ip is None:return None
    if ip[9]!=17 or ip[12:16]!=server or ip[16:20]!=address:return None
    header=(ip[0]&15)*4;udp=ip[header:]
    if len(udp)<20:return None
    source,dest,size,check=struct.unpack_from('>4H',udp)
    if source!=53 or dest!=port or size!=len(udp):return None
    if check and checksum(ip[12:20]+bytes([0,17])+struct.pack('>H',size)+udp):return None
    dns=udp[8:];ident,flags=struct.unpack_from('>HH',dns)
    if ident!=xid or not flags&0x8000:return None
    return flags&15

def tcp_probe_packet(address,remote,port,sequence,ack=0,flags=2):
    tcp=struct.pack('>HHIIBBHHH',port,443,sequence,ack,0x50,flags,64240,0,0)
    ip=struct.pack('>BBHHHBBH4s4s',0x45,0,40,0,0,64,6,0,address,remote)+tcp
    return finalize_ipv4(ip)

def tcp_probe_answer(ip,address,remote,port,sequence):
    ip=ipv4_packet(ip)
    if ip is None or ip[9]!=6 or ip[12:16]!=remote or ip[16:20]!=address:return None
    header=(ip[0]&15)*4;tcp=ip[header:]
    if len(tcp)<20 or not 20<=(tcp[12]>>4)*4<=len(tcp):return None
    if struct.unpack_from('>HH',tcp)!=(443,port):return None
    if checksum(ip[12:20]+bytes([0,6])+struct.pack('>H',len(tcp))+tcp):return None
    if struct.unpack_from('>I',tcp,8)[0]!=(sequence+1)&0xffffffff:return None
    if tcp[13]&0x12==0x12:return ('SYN-ACK',struct.unpack_from('>I',tcp,4)[0])
    if tcp[13]&4:return ('RST',struct.unpack_from('>I',tcp,4)[0])
    return None

def arp_answer(frame,mac,address):
    if len(frame)<42 or frame[:6] not in (mac,b'\xff'*6):return None
    if frame[12:22]!=bytes.fromhex('08060001080006040001') or frame[38:42]!=address:return None
    sender=frame[22:28]
    if sender!=frame[6:12] or sender[0]&1 or not any(sender):return None
    return sender+mac+bytes.fromhex('08060001080006040002')+mac+address+sender+frame[28:32]

def ip_to_ethernet(packet,mac,gateway,address):
    ip=finalize_ipv4(packet)
    if ip is None or ip[12:16]!=address:return None
    return gateway+mac+b'\x08\x00'+ip

class Session:
    def __init__(self,lib,send,receive,mac,ip_result,service_eapol,stop):
        self.send=send;self.receive=receive;self.mac=mac;self.info=ip_result
        self.service_eapol=service_eapol;self.stop=stop;self.socket=None;self.routes=[]
        self.counts={'ipv4_tx':0,'ipv4_rx':0,'arp_replies':0,'tx_no_ack':0}
        self.probe_headers=[];self.probe_started=time.monotonic()
        self.dns_probe=None;self.dns_result=None;self.dns_results={}
        self.tcp_probe=None;self.tcp_result=None
        self.address=ipaddress.IPv4Address(ip_result['address']).packed
        self.gateway=bytes.fromhex(ip_result['gateway_mac'].replace(':',''))
        self.lib=lib;self.name=None;self.https_ok=False;self.network_state=None
        self.lease=ip_result['_lease'];self.renew_xid=None;self.renew_next=0
        self.update_expiration()

    def update_expiration(self):
        duration=self.lease.get('lease_seconds',120)
        if duration<30:raise RuntimeError('Concessão DHCP curta demais para manter a interface.')
        acquired=self.lease.get('obtained_monotonic',time.monotonic())
        self.expires=acquired+duration-5
        self.renew_at=acquired+duration/2

    def command(self,args):
        result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        if result.returncode:raise RuntimeError('Comando de rede falhou: '+result.stdout.strip())
        return result.stdout

    def open(self):
        if os.geteuid()!=0:raise RuntimeError('Criar a interface de rede exige executar com sudo.')
        current=self.command(['/sbin/ifconfig','-a'])
        if re.search(r'^\s+inet '+re.escape(self.info['address'])+r'\s',current,re.M):
            raise RuntimeError('O IP concedido já está configurado em outra interface do Mac.')
        self.lib.aic_utun_open.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.POINTER(ctypes.c_int)]
        self.lib.aic_utun_open.restype=ctypes.c_int
        name=ctypes.create_string_buffer(32);error=ctypes.c_int()
        fd=self.lib.aic_utun_open(name,len(name),ctypes.byref(error))
        if fd<0:raise RuntimeError('UTUN: '+os.strerror(error.value))
        self.socket=PacketFD(fd)
        self.name=name.value.decode('ascii')
        if not re.fullmatch(r'utun[0-9]+',self.name):raise RuntimeError('Nome de interface UTUN inesperado')
        # Distinct point-to-point peer: do not create a host route for the LAN
        # gateway, which might already be used by the user's other adapter.
        peer='169.254.%u.%u'%(1+os.urandom(1)[0]%253,1+os.urandom(1)[0]%253)
        self.peer=peer
        self.command(['/sbin/ifconfig',self.name,'inet',self.info['address'],peer,'netmask','255.255.255.255','mtu','1500','up'])
        self.route(['-inet','-ifscope',self.name,'default','-interface',self.name])
        print('Interface macOS criada: '+self.name+' / '+self.info['address'],flush=True)

    def route(self,args):
        self.command(['/sbin/route','-n','add']+args);self.routes.append(args)

    def publish_network(self):
        publish=self.lib.aic_network_publish
        publish.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.POINTER(ctypes.c_int)]
        publish.restype=ctypes.c_void_p
        self.lib.aic_network_close.argtypes=[ctypes.c_void_p]
        error=ctypes.c_int()
        self.network_state=publish(self.name.encode(),self.info['address'].encode(),self.peer.encode(),ctypes.byref(error))
        if not self.network_state:
            raise RuntimeError('Falha ao publicar rede/DNS AIC no macOS: %u'%error.value)
        print('DNS e disponibilidade de rede AIC publicados no macOS.',flush=True)

    def step(self):
        now=time.monotonic()
        if now>=self.expires:raise RuntimeError('Concessão DHCP expirou; encerrando a interface para liberar o IP.')
        if now>=self.renew_at and now>=self.renew_next:
            if self.renew_xid is None:self.renew_xid=secrets_xid()
            self.send(dhcp_renew(self.mac,self.renew_xid,self.lease))
            self.renew_next=now+5
        for frame in self.receive():
            if len(frame)<14:continue
            if frame[12:14]==b'\x88\x8e':self.service_eapol(frame);continue
            if self.renew_xid is not None:
                reply=parse_dhcp(frame,self.mac,self.renew_xid)
                if reply and reply.get('server')==self.lease['server']:
                    if reply['kind']==6:raise RuntimeError('Servidor DHCP revogou o IP da sessão AIC.')
                    if reply['kind']==5 and reply['address']==self.address:
                        reply['obtained_monotonic']=time.monotonic()
                        self.lease=reply;self.info['_lease']=reply
                        self.renew_xid=None;self.update_expiration()
                        print('IP AIC renovado pelo servidor DHCP.',flush=True)
                        continue
            answer=arp_answer(frame,self.mac,self.address)
            if answer is not None:
                self.send(answer);self.counts['arp_replies']+=1;continue
            if frame[:6]!=self.mac or frame[12:14]!=b'\x08\x00':continue
            ip=ipv4_packet(frame[14:])
            if ip is None or ip[16:20]!=self.address:continue
            self.record_packet('RX',ip)
            if self.tcp_probe:
                answer=tcp_probe_answer(ip,self.address,*self.tcp_probe)
                if answer is not None:self.tcp_result=answer;continue
            if self.dns_probe:
                answer=dns_answer(ip,self.address,*self.dns_probe)
                if answer is not None:
                    self.dns_result=answer;continue
            try:
                self.socket.send(struct.pack('>I',socket.AF_INET)+ip)
                self.counts['ipv4_rx']+=1
            except BlockingIOError:pass
        readable,_,_=select.select([self.socket],[],[],0.01)
        if readable:
            for _ in range(32):
                try:packet=self.socket.recv(65536)
                except BlockingIOError:break
                if len(packet)<4 or packet[:4]!=struct.pack('>I',socket.AF_INET):continue
                ethernet=ip_to_ethernet(packet[4:],self.mac,self.gateway,self.address)
                if ethernet is not None:
                    self.record_packet('TX',packet[4:],ethernet[14:])
                    if self.send(ethernet) is False:self.counts['tx_no_ack']+=1
                    else:self.counts['ipv4_tx']+=1

    def record_packet(self,direction,ip,final=None):
        if self.https_ok or len(self.probe_headers)>=96:return
        info=packet_metadata(ip);info['direction']=direction
        info['elapsed_ms']=round((time.monotonic()-self.probe_started)*1000,1)
        if final is not None:
            info['checksum_completed']=ip[:len(final)]!=final
            info['final_transport_checksum_valid']=packet_metadata(final).get('transport_checksum_valid')
        self.probe_headers.append(info)

    def check_https(self):
        # Explicit IP + bound interface: the test cannot fall back to another
        # adapter or depend on its DNS/proxy configuration.
        args=['/usr/bin/curl','-q','-4','--silent','--show-error','--fail','--noproxy','*',
              '--interface',self.name,'--resolve','one.one.one.one:443:1.1.1.1',
              '--connect-timeout','12','--max-time','35','--output','/dev/null',
              '--write-out','%{http_code}','https://one.one.one.one/cdn-cgi/trace']
        process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            while process.poll() is None:
                if self.stop.is_set():raise KeyboardInterrupt
                self.step()
            out,error=process.communicate()
            if process.returncode or out.strip()!='200':
                raise RuntimeError('HTTPS pela interface AIC não passou: '+(error.strip() or out.strip()))
            if not self.counts['ipv4_rx'] or not self.counts['ipv4_tx']:
                raise RuntimeError('HTTPS sem confirmação de tráfego no AIC')
            self.https_ok=True
            print('HTTPS pelo AIC: confirmado (interface vinculada, certificado TLS validado).',flush=True)
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=5)

    def check_dns_server(self,server,label):
        xid=secrets_xid()&65535;port=45000+(secrets_xid()%15000)
        self.dns_probe=(server,xid,port)
        packet=dns_query(self.address,server,xid,port)
        try:
            for _ in range(2):
                if self.stop.is_set():raise KeyboardInterrupt
                self.send(self.gateway+self.mac+b'\x08\x00'+packet)
                deadline=time.monotonic()+3
                while self.dns_result is None and time.monotonic()<deadline:self.step()
                if self.dns_result is not None:break
            self.dns_results[str(ipaddress.IPv4Address(server))]=self.dns_result
            print(label+': '+('resposta recebida (código %u)'%self.dns_result if self.dns_result is not None else 'sem resposta'),flush=True)
        finally:self.dns_probe=None

    def check_dns(self):
        server=self.lease.get('dns',self.lease['server'])[:4]
        self.check_dns_server(server,'DNS direto pelo AIC')
        local_result=self.dns_result;self.dns_result=None
        self.check_dns_server(bytes([1,1,1,1]),'DNS externo 1.1.1.1 pelo AIC')
        self.dns_result=local_result

    def check_raw_tcp(self):
        remote=bytes([1,1,1,1]);port=60000+(secrets_xid()%5000);seq=secrets_xid()
        self.tcp_probe=(remote,port,seq)
        try:
            for _ in range(2):
                if self.stop.is_set():raise KeyboardInterrupt
                ip=tcp_probe_packet(self.address,remote,port,seq)
                self.record_packet('TX direto',ip)
                self.send(self.gateway+self.mac+b'\x08\x00'+ip)
                deadline=time.monotonic()+2
                while self.tcp_result is None and time.monotonic()<deadline:self.step()
                if self.tcp_result is not None:break
            print('TCP direto pelo AIC, sem UTUN: '+(self.tcp_result[0] if self.tcp_result else 'sem resposta'),flush=True)
            if self.tcp_result and self.tcp_result[0]=='SYN-ACK':
                reset=tcp_probe_packet(self.address,remote,port,(seq+1)&0xffffffff,(self.tcp_result[1]+1)&0xffffffff,0x14)
                self.send(self.gateway+self.mac+b'\x08\x00'+reset)
        finally:self.tcp_probe=None

    def run(self):
        # Development probes could delay normal connection by up to 35 seconds.
        # Bring up the route immediately after DHCP/ARP succeeds.
        self.open()
        self.route(['-inet','-net','0.0.0.0/1','-interface',self.name])
        self.route(['-inet','-net','128.0.0.0/1','-interface',self.name])
        self.publish_network()
        self.status(True)
        print('Conexão IPv4 pelo AIC ativa.',flush=True)
        while not self.stop.is_set():self.step()
        return {'interface':self.name,'https_bound_test':True,'ipv4_session':True,'counters':self.counts}

    def status(self,active):
        here=Path(__file__).resolve().parent
        info={'active':active,'interface':self.name,'address':self.info['address'],
              'mode':'UTUN IPv4','ssid':self.info.get('_ssid',''),
              'band':self.info.get('_band'),'counters':self.counts,
              'https_bound_test':self.https_ok,'probe_headers':self.probe_headers,
              'macos_network_published':bool(self.network_state),
              'dns_direct_result':self.dns_result,
              'dns_servers_results':self.dns_results,
              'tcp_direct_result':self.tcp_result[0] if self.tcp_result else None,
              'transport_rx':self.info.get('_transport_diagnostics',{})}
        try:
            write_report(here/'estado-conexao.json',info)
        except OSError:pass

    def close(self):
        if self.network_state:
            self.lib.aic_network_close(self.network_state);self.network_state=None
        # Exact routes have an interface gateway owned by this control socket.
        for args in reversed(self.routes):
            subprocess.run(['/sbin/route','-n','delete']+args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.routes=[]
        if self.socket:self.socket.close();self.socket=None
        self.status(False)

def connect(lib,send,receive,mac,ip_result,service_eapol,stop):
    session=None
    try:
        if not ip_result.get('gateway_arp_reply') or not ip_result.get('gateway_mac'):
            raise RuntimeError('Sem confirmação ARP do gateway; não será criada uma rota de internet.')
        session=Session(lib,send,receive,mac,ip_result,service_eapol,stop)
        return session.run()
    finally:
        if session:session.close()
        lease=ip_result.get('_lease')
        if lease:
            try:
                release=dhcp_request(mac,secrets_xid(),7,lease['address'],lease['server'])
                send(lease['server_mac']+release[6:])
            except RuntimeError:pass

def secrets_xid():
    return int.from_bytes(os.urandom(4),'big')
