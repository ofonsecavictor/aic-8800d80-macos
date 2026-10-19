"""Bounded DHCP/ARP diagnostic over AIC Ethernet, no host routes or sockets.

DHCP wire formats: RFC2131/2132. This is a short test, not a lease daemon.
"""
import ipaddress
import secrets
import struct
import time

BROADCAST=b'\xff'*6
ZERO=b'\x00'*4

def checksum(data):
    data+=bytes(len(data)%2)
    value=sum(struct.unpack('>%uH'%(len(data)//2),data))
    while value>>16:value=(value&65535)+(value>>16)
    return (~value)&65535

def option(kind,data):return bytes([kind,len(data)])+data

def ipv4_udp(mac,body,source=ZERO,destination=b'\xff'*4):
    udp=struct.pack('>4H',68,67,8+len(body),0)+body
    header=bytearray(struct.pack('>BBHHHBBH4s4s',0x45,0,20+len(udp),0,0,64,17,0,source,destination))
    struct.pack_into('>H',header,10,checksum(header))
    return BROADCAST+mac+b'\x08\x00'+header+udp

def dhcp_request(mac,xid,kind,address=ZERO,server=None,lease_seconds=120):
    if len(mac)!=6 or len(address)!=4 or kind not in (1,3,7):raise ValueError('Invalid DHCP client request')
    boot=bytearray(236)
    struct.pack_into('>4BIHH',boot,0,1,1,6,0,xid,0,0x8000 if kind!=7 else 0)
    boot[28:34]=mac
    if kind==7:boot[12:16]=address
    opts=b'\x63\x82\x53\x63'+option(53,bytes([kind]))+option(61,b'\x01'+mac)
    if kind!=7:
        opts+=option(55,bytes([1,3,6,51,54]))+option(51,struct.pack('>I',lease_seconds))
    if kind==3:opts+=option(50,address)
    if server is not None:
        if len(server)!=4:raise ValueError('Invalid DHCP server')
        opts+=option(54,server)
    payload=bytes(boot)+opts+b'\xff'
    payload+=bytes(max(0,300-len(payload)))
    return ipv4_udp(mac,payload,source=address if kind==7 else ZERO,
                    destination=server if kind==7 and server is not None else b'\xff'*4)

def dhcp_renew(mac,xid,lease):
    boot=bytearray(236)
    struct.pack_into('>4BIHH',boot,0,1,1,6,0,xid,0,0)
    boot[12:16]=lease['address'];boot[28:34]=mac
    # RENEWING: ciaddr set; do not include requested-IP/server-ID options.
    opts=bytes.fromhex('63825363')+option(53,b'\x03')+option(61,b'\x01'+mac)+option(51,struct.pack('>I',3600))+b'\xff'
    body=bytes(boot)+opts;body+=bytes(max(0,300-len(body)))
    packet=ipv4_udp(mac,body,source=lease['address'],destination=lease['server'])
    return lease['server_mac']+packet[6:]

def parse_dhcp(frame,mac,xid):
    if len(frame)<42 or frame[:6] not in (mac,BROADCAST) or frame[12:14]!=b'\x08\x00':return None
    ip=frame[14:]
    hdr=(ip[0]&15)*4
    total=struct.unpack_from('>H',ip,2)[0]
    if ip[0]>>4!=4 or hdr<20 or total>len(ip) or total<hdr+8 or ip[9]!=17:return None
    if checksum(ip[:hdr]) or struct.unpack_from('>H',ip,6)[0]&0x3fff:return None
    udp=ip[hdr:total];source,dest,length,check=struct.unpack_from('>4H',udp)
    if (source,dest)!=(67,68) or length<248 or length>len(udp):return None
    udp=udp[:length]
    if check and checksum(ip[12:20]+bytes([0,17])+struct.pack('>H',length)+udp):return None
    boot=udp[8:]
    if boot[:3]!=b'\x02\x01\x06' or struct.unpack_from('>I',boot,4)[0]!=xid or boot[28:34]!=mac:return None
    if boot[236:240]!=b'\x63\x82\x53\x63':return None
    opts={};cursor=240;ended=False
    while cursor<len(boot):
        kind=boot[cursor];cursor+=1
        if kind==255:ended=True;break
        if kind==0:continue
        if cursor>=len(boot):return None
        size=boot[cursor];cursor+=1
        if cursor+size>len(boot) or kind in opts:return None
        opts[kind]=boot[cursor:cursor+size];cursor+=size
    if not ended or len(opts.get(53,b''))!=1:return None
    result={'kind':opts[53][0],'address':boot[16:20],'server_mac':frame[6:12]}
    for kind,name in ((54,'server'),(1,'mask'),(3,'routers'),(6,'dns')):
        if kind in opts:
            value=opts[kind]
            if not value or len(value)%4 or kind in (1,54) and len(value)!=4:return None
            result[name]=value
    if 51 in opts:
        if len(opts[51])!=4:return None
        result['lease_seconds']=struct.unpack('>I',opts[51])[0]
    return result

def arp_request(mac,address,gateway):
    return BROADCAST+mac+b'\x08\x06'+struct.pack('>HHBBH',1,0x800,6,4,1)+mac+address+bytes(6)+gateway

def arp_reply(frame,mac,address,gateway):
    if len(frame)<42 or frame[:6]!=mac or frame[12:22]!=bytes.fromhex('08060001080006040002'):return None
    if frame[28:32]!=gateway or frame[32:38]!=mac or frame[38:42]!=address:return None
    if frame[6:12]!=frame[22:28] or frame[22]&1 or not any(frame[22:28]):return None
    return frame[22:28]

def test_link(send,receive,mac,service_eapol,keep_lease=False,on_lease=None):
    xid=secrets.randbits(32);offer=None;lease=None;stage='discover';tries=0
    deadline=time.monotonic()+30;next_send=0;handed_off=False
    try:
        while time.monotonic()<deadline:
            if time.monotonic()>=next_send:
                if tries>=4:raise RuntimeError('DHCP: sem resposta válida na etapa '+stage)
                requested_lease=3600 if keep_lease else 120
                frame=dhcp_request(mac,xid,1,lease_seconds=requested_lease) if offer is None else dhcp_request(mac,xid,3,offer['address'],offer['server'],requested_lease)
                print('DHCP TX: '+('DISCOVER' if offer is None else 'REQUEST'),flush=True)
                send(frame);next_send=time.monotonic()+4;tries+=1
            for frame in receive():
                if frame[12:14]==b'\x88\x8e':service_eapol(frame);continue
                answer=parse_dhcp(frame,mac,xid)
                if answer is None:continue
                if answer['kind']==2 and offer is None and 'server' in answer:
                    address=ipaddress.IPv4Address(answer['address'])
                    if address.is_unspecified or address.is_multicast or answer['address']==b'\xff'*4:continue
                    offer=answer;stage='request';tries=0;next_send=0
                    print('DHCP OFFER: '+str(address),flush=True)
                elif answer['kind']==6 and offer and answer.get('server')==offer['server']:
                    raise RuntimeError('DHCP: servidor recusou o endereço solicitado.')
                elif answer['kind']==5 and offer and answer.get('server')==offer['server'] and answer['address']==offer['address']:
                    lease=answer;lease['obtained_monotonic']=time.monotonic();break
            if lease:break
        if not lease:raise RuntimeError('DHCP: tempo limite sem concessão de IP.')
        result={'address':str(ipaddress.IPv4Address(lease['address'])),
                'server':str(ipaddress.IPv4Address(lease['server'])),'dhcp_ack':True}
        for field in ('mask','routers','dns'):
            if field in lease:
                result[field]=[str(ipaddress.IPv4Address(lease[field][i:i+4])) for i in range(0,len(lease[field]),4)]
        print('DHCP ACK: '+result['address'],flush=True)
        if lease.get('routers'):
            gateway=lease['routers'][:4];found=None
            for _ in range(2):
                send(arp_request(mac,lease['address'],gateway));limit=time.monotonic()+3
                while time.monotonic()<limit and found is None:
                    for frame in receive():
                        if frame[12:14]==b'\x88\x8e':service_eapol(frame);continue
                        found=arp_reply(frame,mac,lease['address'],gateway)
                        if found:break
                if found:break
            result['gateway_arp_reply']=bool(found)
            if found:result['gateway_mac']=found.hex(':')
            print('ARP do gateway: '+('recebido' if found else 'sem resposta'),flush=True)
        if on_lease is not None:
            on_lease(lease,result,send,receive,service_eapol)
        if keep_lease:
            result['_lease']=lease;handed_off=True
        return result
    finally:
        if lease and not handed_off:
            # Release only this diagnostic lease; no host interface uses it.
            try:
                release=dhcp_request(mac,xid,7,lease['address'],lease['server'])
                send(lease['server_mac']+release[6:])
            except RuntimeError:pass
