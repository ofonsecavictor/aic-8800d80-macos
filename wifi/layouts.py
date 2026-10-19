"""Wire layouts from the pinned AIC lmac_msg/lmac_mac headers."""
import ctypes as c
import struct

class Channel(c.LittleEndianStructure):
    _fields_=[('frequency',c.c_uint16),('band',c.c_uint8),('flags',c.c_uint8),('power',c.c_int8)]

class SSID(c.LittleEndianStructure):
    _fields_=[('length',c.c_uint8),('data',c.c_uint8*32)]

class Scan(c.LittleEndianStructure):
    _fields_=[('channels',Channel*42),('ssids',SSID*3),('bssid',c.c_uint16*3),
              ('ies',c.c_uint32),('ie_length',c.c_uint16),('vif',c.c_uint8),
              ('channel_count',c.c_uint8),('ssid_count',c.c_uint8),
              ('no_cck',c.c_bool),('duration',c.c_uint32)]

assert c.sizeof(Channel)==6 and c.sizeof(Scan)==376

CHANNELS_24GHZ=tuple(range(1,14))
CHANNELS_5GHZ=(36,40,44,48,52,56,60,64,100,104,108,112,116,120,124,
                128,132,136,140,144,149,153,157,161,165)
DFS_CHANNELS_5GHZ=frozenset(range(52,65,4))|frozenset(range(100,145,4))
CONNECTABLE_CHANNELS_5GHZ=frozenset(CHANNELS_5GHZ)-DFS_CHANNELS_5GHZ

def channel_to_frequency(channel,band=None):
    if band in (None,0) and channel in CHANNELS_24GHZ:return 2407+5*channel
    if band in (None,1) and channel in CHANNELS_5GHZ:return 5000+5*channel
    return None

def frequency_to_channel(frequency):
    if frequency in tuple(channel_to_frequency(v,0) for v in CHANNELS_24GHZ):
        return (frequency-2407)//5
    if frequency in tuple(channel_to_frequency(v,1) for v in CHANNELS_5GHZ):
        return (frequency-5000)//5
    return None

def frequency_band(frequency):
    channel=frequency_to_channel(frequency)
    if channel is None:return None
    return 0 if frequency<3000 else 1

def connectable_frequency(frequency):
    channel=frequency_to_channel(frequency)
    return channel in CHANNELS_24GHZ or (frequency_band(frequency)==1 and channel in CONNECTABLE_CHANNELS_5GHZ)

def passive_scan(vif,band=None,frequencies=None):
    scan=Scan()
    channels=[]
    if band in (None,0):
        channels.extend((channel_to_frequency(value,0),0,1) for value in CHANNELS_24GHZ)
    if band in (None,1):
        channels.extend((channel_to_frequency(value,1),1,1|(4 if value in DFS_CHANNELS_5GHZ else 0)) for value in CHANNELS_5GHZ)
    if frequencies is not None:
        channels=[item for item in channels if item[0] in frequencies]
        if not channels:raise ValueError('No valid scan channels')
    for i,(frequency,band,flags) in enumerate(channels):
        scan.channels[i].frequency=frequency
        scan.channels[i].band=band
        scan.channels[i].flags=flags # CHAN_NO_IR; DFS channels also carry CHAN_RADAR.
    scan.channel_count=len(channels);scan.vif=vif
    for i in range(3):scan.bssid[i]=0xffff
    scan.duration=200000
    return bytes(scan)

def network(body,include_beacon=False):
    if len(body)<12:return None
    length,framectrl,frequency=struct.unpack_from('<HHH',body)
    if length>len(body)-12 or length<36:return None
    frame=body[12:12+length]
    if framectrl&0x00fc not in (0x80,0x50):return None
    result={'bssid':':'.join('%02x'%v for v in frame[16:22]),'frequency':frequency if 2300<=frequency<=7125 else None,
            'rssi':struct.unpack_from('<b',body,9)[0],'ssid':''}
    cursor=36
    while cursor+2<=len(frame):
        kind,size=frame[cursor:cursor+2];cursor+=2
        if cursor+size>len(frame):return None
        if kind==0:
            if size>32:return None
            result['ssid']=frame[cursor:cursor+size].decode('utf-8',errors='replace')
        elif kind==3 and size==1:
            channel=frame[cursor]
            derived=channel_to_frequency(channel)
            if derived is not None:result['frequency']=derived
        elif kind==61 and size>=1: # HT Operation: primary channel, common on 5 GHz.
            derived=channel_to_frequency(frame[cursor])
            if derived is not None:result['frequency']=derived
        elif kind==48:
            result['rsn']=frame[cursor:cursor+size].hex()
        cursor+=size
    if cursor!=len(frame):return None
    if include_beacon:
        result['_beacon']={'interval':struct.unpack_from('<H',frame,32)[0],
            'capability':struct.unpack_from('<H',frame,34)[0], 'ies':frame[36:]}
    return result

class Connect(c.LittleEndianStructure):
    _fields_=[('ssid',SSID),('bssid',c.c_uint16*3),('channel',Channel),
              ('flags',c.c_uint32),('ethertype',c.c_uint16),('ie_len',c.c_uint16),
              ('listen',c.c_uint16),('dont_wait',c.c_uint8),('auth',c.c_uint8),
              ('uapsd',c.c_uint8),('vif',c.c_uint8),('ies',c.c_uint32*64)]

assert c.sizeof(Connect)==320 and Connect.ies.offset==64

def connect_request(vif,mac,ssid,frequency):
    raw=ssid.encode('utf-8')
    if not 1<=len(raw)<=32 or not connectable_frequency(frequency):
        raise ValueError('Unsupported SSID or channel')
    req=Connect();req.ssid.length=len(raw)
    req.ssid.data[:len(raw)]=raw
    for i,n in enumerate(struct.unpack('<3H',mac)):req.bssid[i]=n
    req.channel.frequency=frequency
    req.channel.band=frequency_band(frequency)
    # CONTROL_PORT_HOST | CONTROL_PORT_NO_ENC | WPA_WPA2_IN_USE.
    req.flags=11;req.ethertype=0x8e88;req.listen=0;req.vif=vif
    # RSN v1, CCMP group/pairwise, PSK AKM, no optional capabilities.
    ie=bytes.fromhex('30140100000fac040100000fac040100000fac020000')
    req.ie_len=len(ie)
    c.memmove(c.addressof(req)+Connect.ies.offset,ie,len(ie))
    return bytes(req)
