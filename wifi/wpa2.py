"""Restricted WPA2-PSK/CCMP diagnostic supplicant. Secrets stay in memory.

Only descriptor version 2; no WPA1, SAE, enterprise, TKIP, or rekey service.
AES key unwrap uses macOS CommonCrypto with RFC3394 integrity validation.
"""
import ctypes
import hashlib
import hmac
import os
import struct

RSN_IE=bytes.fromhex('30140100000fac040100000fac040100000fac020000')

def validate_rsn(rsn):
    if len(rsn)<8 or rsn[:6]!=bytes.fromhex('0100000fac04'):
        raise ValueError('Esta rede não usa RSN v1 com grupo CCMP.')
    cursor=6;sets=[]
    for _ in range(2):
        if cursor+2>len(rsn):raise ValueError('Truncated RSN suite count')
        count=struct.unpack_from('<H',rsn,cursor)[0];cursor+=2
        end=cursor+count*4
        if not count or end>len(rsn):raise ValueError('Invalid RSN suite list')
        sets.append([rsn[i:i+4] for i in range(cursor,end,4)]);cursor=end
    if bytes.fromhex('000fac04') not in sets[0] or bytes.fromhex('000fac02') not in sets[1]:
        raise ValueError('Esta versão suporta apenas WPA2 PSK com CCMP.')
    if cursor+2<=len(rsn) and struct.unpack_from('<H',rsn,cursor)[0]&0x40:
        raise ValueError('Esta versão ainda não suporta PMF obrigatório.')

def pmk(password,ssid):
    raw=password.encode('utf-8')
    if len(raw)==64:
        try:return bytes.fromhex(password)
        except ValueError:pass
    if not 8<=len(raw)<=63:raise ValueError('A senha WPA2 deve ter de 8 a 63 bytes.')
    return hashlib.pbkdf2_hmac('sha1',raw,ssid.encode('utf-8'),4096,32)

def derive_ptk(key,station,ap,snonce,anonce):
    if not (len(key)==32 and len(station)==len(ap)==6 and len(snonce)==len(anonce)==32):
        raise ValueError('Invalid PTK inputs')
    context=min(station,ap)+max(station,ap)+min(snonce,anonce)+max(snonce,anonce)
    return b''.join(hmac.new(key,b'Pairwise key expansion\x00'+context+bytes([i]),hashlib.sha1).digest() for i in range(4))[:64]

def parse_key(packet):
    if len(packet)<99 or packet[1]!=3 or packet[4]!=2:
        raise ValueError('Not an RSN EAPOL-Key packet')
    length=struct.unpack_from('>H',packet,2)[0]+4
    if length!=len(packet) or 99+struct.unpack_from('>H',packet,97)[0]!=length:
        raise ValueError('Invalid EAPOL length')
    info=struct.unpack_from('>H',packet,5)[0]
    if info&7!=2 or info&0x0c00:raise ValueError('Unsupported key descriptor or request/error')
    return info,int.from_bytes(packet[9:17],'big'),packet[17:49],packet[99:]

def verify_mic(packet,kck):
    unsigned=packet[:81]+bytes(16)+packet[97:]
    if not hmac.compare_digest(packet[81:97],hmac.new(kck,unsigned,hashlib.sha1).digest()[:16]):
        raise ValueError('MIC inválido: senha incorreta ou mensagem alterada.')

def answer(packet,info,nonce,kck,ies=b''):
    out=bytearray(99+len(ies))
    out[:5]=bytes([packet[0],3])+struct.pack('>H',95+len(ies))+b'\x02'
    struct.pack_into('>H',out,5,info)
    out[9:17]=packet[9:17];out[17:49]=nonce
    struct.pack_into('>H',out,97,len(ies));out[99:]=ies
    out[81:97]=hmac.new(kck,out,hashlib.sha1).digest()[:16]
    return bytes(out)

def unwrap(lib,kek,data):
    lib.wifi_unwrap.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t)]
    lib.wifi_unwrap.restype=ctypes.c_int
    output=ctypes.create_string_buffer(len(data));length=ctypes.c_size_t(len(output))
    status=lib.wifi_unwrap(ctypes.create_string_buffer(kek),ctypes.create_string_buffer(data),len(data),output,ctypes.byref(length))
    if status:raise ValueError('AES unwrap integrity check failed')
    return output.raw[:length.value]

def key_data(data,expected_rsn):
    cursor=0;gtk=None;rsn=None
    while cursor+2<=len(data):
        kind,size=data[cursor:cursor+2];cursor+=2
        # RFC3394 padding used by RSN is a vendor tag followed by zeros.
        if kind==221 and size==0 and not any(data[cursor:]):break
        if cursor+size>len(data):raise ValueError('Truncated key-data IE')
        body=data[cursor:cursor+size];cursor+=size
        if kind==48:rsn=body
        if kind==221 and body[:4]==bytes.fromhex('000fac01'):
            if len(body)!=22:raise ValueError('Unsupported GTK size')
            gtk=(body[4]&3,body[6:])
    if rsn is None or not hmac.compare_digest(rsn,expected_rsn):
        raise ValueError('RSN changed between scan and authenticated handshake')
    if gtk is None:raise ValueError('Missing GTK')
    return gtk

class Supplicant:
    def __init__(self,key,station,ap,rsn,lib):
        self.key=key;self.station=station;self.ap=ap;self.rsn=rsn;self.lib=lib
        self.snonce=os.urandom(32);self.anonce=None;self.ptk=None
        self.m1=None;self.m3=None;self.installed=False;self.key_material=None

    def receive(self,packet):
        info,replay,nonce,data=parse_key(packet)
        if info==0x008a:
            if data or not any(nonce):raise ValueError('Invalid M1 nonce or key data')
            if self.installed:raise ValueError('Reauthentication requires a new session')
            if self.m1 is not None:
                if replay<self.m1 or (replay==self.m1 and nonce!=self.anonce):
                    raise ValueError('Stale M1 or conflicting nonce for the same counter')
                # APs may advance Replay Counter when retransmitting M1. Keep
                # SNonce/PTK for the same ANonce; restart before installation
                # only when a newer M1 supplies a genuinely new ANonce.
                if nonce!=self.anonce:
                    self.snonce=os.urandom(32);self.m3=None
            self.m1=replay;self.anonce=nonce
            self.ptk=derive_ptk(self.key,self.station,self.ap,self.snonce,nonce)
            return answer(packet,0x010a,self.snonce,self.ptk[:16],RSN_IE),None
        if info!=0x13ca or self.ptk is None or nonce!=self.anonce or replay<=self.m1:
            raise ValueError('Unexpected handshake state or key flags')
        verify_mic(packet,self.ptk[:16])
        if self.installed:
            previous_replay=int.from_bytes(self.m3[9:17],'big')
            if replay<previous_replay:raise ValueError('Stale M3 replay counter')
            if replay==previous_replay and self.m3!=packet:
                raise ValueError('Conflicting M3 for the same replay counter')
            # Retransmitted M3 may have a NEW counter (therefore a new MIC).
            # Check the authenticated, unwrapped key material, not whole packet
            # equality. Never call KEY_ADD again or reset CCMP packet numbers.
            gtk=key_data(unwrap(self.lib,self.ptk[16:32],data),self.rsn)
            material=self.ptk[32:48]+bytes([gtk[0]])+gtk[1]
            if not hmac.compare_digest(material,self.key_material):
                raise ValueError('M3 alterou as chaves; renegociação ainda não suportada.')
            self.m3=packet
            # Retransmit M4 without reinstalling keys or resetting packet numbers.
            return answer(packet,0x030a,bytes(32),self.ptk[:16]),None
        gtk=key_data(unwrap(self.lib,self.ptk[16:32],data),self.rsn)
        self.key_material=self.ptk[32:48]+bytes([gtk[0]])+gtk[1]
        self.m3=packet
        return answer(packet,0x030a,bytes(32),self.ptk[:16]),(self.ptk[32:48],gtk)

def rx_records(data):
    """Split one USB transfer into bounded AIC RX records."""
    offset=0
    while offset<len(data):
        if len(data)-offset<60:raise ValueError('Truncated AIC RX header')
        size=struct.unpack_from('<H',data,offset)[0]
        end=offset+60+size
        if size<24 or end>len(data):raise ValueError('Truncated AIC MPDU: offset=%u size=%u total=%u header=%s'%(offset,size,len(data),data[offset:offset+16].hex()))
        yield data[offset:end]
        offset=end

def ethernet_frames(data):
    """Convert bounded AIC MPDU records to Ethernet, excluding unsupported cases."""
    for record in rx_records(data):
        status=struct.unpack_from('<I',record,36)[0]
        flags=struct.unpack_from('<I',record,48)[0]
        frame=record[60:]
        if not flags&0x40:continue # flags_upload in hw_rxhdr
        fc=struct.unpack_from('<H',frame)[0]
        # Data from AP, no fragmentation or WDS.
        if fc&0x030c!=0x0208 or fc&0x0400 or frame[22]&15:continue
        hdr=24+(2 if fc&0x0080 else 0)+(4 if fc&0x8000 else 0)
        if fc&0x0080 and len(frame)<=24:continue
        amsdu=bool(fc&0x0080 and frame[24]&0x80)
        if fc&0x4000:
            # Only accept CCMP128 successfully decrypted by firmware. Reference
            # rwnx_rxdataind retains the security header and does not trim an
            # assumed MIC tail. IPv4 consumers bound payload by total_length.
            if (status>>2)&7!=3 or status&0x1c0 or not status&0x2000:continue
            hdr+=8
        if amsdu:
            payload=frame[hdr:];cursor=0
            while cursor+14<=len(payload):
                size=struct.unpack_from('>H',payload,cursor+12)[0]
                end=cursor+14+size
                if size<8 or size>2304 or end>len(payload):break
                body=payload[cursor+14:end]
                if body[:6]==bytes.fromhex('aaaa03000000'):
                    yield payload[cursor:cursor+12]+body[6:]
                cursor=(end+3)&~3
            continue
        if len(frame)<hdr+8 or frame[hdr:hdr+6]!=bytes.fromhex('aaaa03000000'):continue
        yield frame[4:10]+frame[16:22]+frame[hdr+6:]

def transmit_frame(ethernet,vif,station,confirmation=0):
    if not 14<=len(ethernet)<=1514 or not 0<=vif<4 or not 0<=station<32:
        raise ValueError('Invalid Ethernet frame or station')
    # hostdesc=28 bytes, FullMAC, MUMIMO disabled, BE queue / TID 0.
    # rwnx_start_xmit calls skb_pull(skb, 14) BEFORE calculating frame_len.
    # Ethernet addresses/type belong in hostdesc; only its payload follows it.
    payload=ethernet[14:]
    desc=struct.pack('<HHI',len(payload),0,confirmation)+ethernet[:14]+struct.pack('<4BH',1,0,vif,station,0)
    body=desc+payload
    if confirmation&0x80000000:body+=bytes((-len(body))%4)
    elif (4+len(body))%512==0:
        # The Linux USB transport terminates a bulk OUT transfer that ends
        # exactly on a max-packet boundary (URB_ZERO_PACKET). Our synchronous
        # userspace pipe has no equivalent flag. A single zero byte is safe
        # trailing padding for this unconfirmed Ethernet descriptor and makes
        # the transfer end with a short packet instead.
        body+=b'\x00'
    return struct.pack('<HBB',4+len(body),1,0)+body

def aggregate_transmit_frames(frames):
    """Encode up to ten standard AIC TX records in the firmware USB format."""
    frames=tuple(frames)
    if not 1<=len(frames)<=10:
        raise ValueError('Invalid AIC USB TX aggregate count')
    aggregate=bytearray()
    for frame in frames:
        if (not isinstance(frame,bytes) or not 32<=len(frame)<=2048 or
                struct.unpack_from('<H',frame)[0]!=len(frame) or
                frame[2:4]!=b'\x01\x00'):
            raise ValueError('Invalid AIC USB TX record')
        # CONFIG_USB_TX_AGGR in the reference prepends two copies of the
        # normal record length, then retains the original <HBB> USB header.
        aggregate+=struct.pack('<HH',len(frame),len(frame))+frame
        aggregate+=bytes((-len(aggregate))%4)
    if len(aggregate)%512==0:
        # IOUSBLib has no URB_ZERO_PACKET flag.  A zero record produces the
        # required short final USB packet and is the firmware's terminator.
        aggregate+=bytes(4)
    return bytes(aggregate)

def key_request(vif,station,key,index=0,pairwise=True):
    if len(key)!=16:raise ValueError('Only CCMP128 is supported')
    return struct.pack('<BB2xB3x32s4B',index,station,16,key,2,vif,0,int(pairwise))
