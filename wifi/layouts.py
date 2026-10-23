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

# Firmware ABI from lmac_mac.h/lmac_msg.h.  Keep the native alignment: the
# FullMAC firmware consumes this structure directly, including its padding.
class HTCapability(c.LittleEndianStructure):
    _fields_=[('info',c.c_uint16),('ampdu',c.c_uint8),('mcs',c.c_uint8*16),
              ('extended',c.c_uint16),('beamforming',c.c_uint32),
              ('antenna_selection',c.c_uint8)]

class VHTCapability(c.LittleEndianStructure):
    _fields_=[('info',c.c_uint32),('rx_mcs_map',c.c_uint16),
              ('rx_highest',c.c_uint16),('tx_mcs_map',c.c_uint16),
              ('tx_highest',c.c_uint16)]

class HEMCSSupport(c.LittleEndianStructure):
    _fields_=[('rx_mcs_80',c.c_uint16),('tx_mcs_80',c.c_uint16),
              ('rx_mcs_160',c.c_uint16),('tx_mcs_160',c.c_uint16),
              ('rx_mcs_80p80',c.c_uint16),('tx_mcs_80p80',c.c_uint16)]

class HECapability(c.LittleEndianStructure):
    _fields_=[('mac',c.c_uint8*6),('phy',c.c_uint8*11),
              ('mcs',HEMCSSupport),('ppe',c.c_uint8*25)]

class MEConfig(c.LittleEndianStructure):
    _fields_=[('ht',HTCapability),('vht',VHTCapability),('he',HECapability),
              ('tx_lifetime',c.c_uint16),('max_bandwidth',c.c_uint8),
              ('ht_supported',c.c_bool),('vht_supported',c.c_bool),
              ('he_supported',c.c_bool),('he_ul_enabled',c.c_bool),
              ('power_save',c.c_bool),('antenna_diversity',c.c_bool),
              ('dynamic_power_save',c.c_bool)]

assert c.sizeof(HTCapability)==32 and HTCapability.extended.offset==20
assert c.sizeof(VHTCapability)==12
assert c.sizeof(HECapability)==56 and HECapability.mcs.offset==18
assert c.sizeof(MEConfig)==112 and MEConfig.tx_lifetime.offset==100

class MEChannelConfig(c.LittleEndianStructure):
    _fields_=[('channels_2g',Channel*14),('channels_5g',Channel*28),
              ('count_2g',c.c_uint8),('count_5g',c.c_uint8)]

assert c.sizeof(MEChannelConfig)==254

def me_config_request(enable_he=False):
    """Advertise the D80's verified one-stream HT/VHT capabilities.

    Values mirror the upstream AIC defaults for the one-stream D81.  HE may be
    enabled independently so a live compatibility trial remains reversible.
    """
    req=MEConfig()
    req.ht.info=0x0963 # LDPC, 20/40, SGI 20/40, RX STBC, 8K AMSDU.
    req.ht.ampdu=3|(7<<2) # 64K A-MPDU and 16 us minimum MPDU spacing.
    req.ht.mcs[0]=0xff
    req.ht.mcs[4]=0x01 # MCS32 for 40 MHz.
    req.ht.mcs[10]=150 # rx_highest, little-endian u16 at offsets 10..11.
    req.ht.mcs[12]=1 # IEEE80211_HT_MCS_TX_DEFINED.

    req.vht.info=0x03987131
    req.vht.rx_mcs_map=req.vht.tx_mcs_map=0xfffe # MCS 0-9, one stream.
    req.vht.rx_highest=req.vht.tx_highest=390 # 1SS VHT80 MCS9.

    if enable_he:
        req.he.mac[:]=bytes.fromhex('000002000000')
        req.he.phy[:]=bytes.fromhex('06e02b580dc0cf00023000')
        req.he.mcs.rx_mcs_80=req.he.mcs.tx_mcs_80=0xfffe # 1SS, MCS 0-11.
        req.he.mcs.rx_mcs_160=req.he.mcs.tx_mcs_160=0xffff
        req.he.mcs.rx_mcs_80p80=req.he.mcs.tx_mcs_80p80=0xffff
        req.he.ppe[:4]=bytes.fromhex('381cc701')

    req.tx_lifetime=1000
    req.max_bandwidth=2 # PHY_CHNL_BW_80.
    req.ht_supported=True
    req.vht_supported=True
    req.he_supported=enable_he
    req.he_ul_enabled=False
    # This is a mains-powered desktop. Firmware PS added 60-200 ms latency and
    # bursty TCP receive behavior in the live VHT80 trial, so keep it disabled.
    req.power_save=False
    req.antenna_diversity=True
    req.dynamic_power_save=False
    return bytes(req)

CHANNELS_24GHZ=tuple(range(1,14))
CHANNELS_5GHZ=(36,40,44,48,52,56,60,64,100,104,108,112,116,120,124,
                128,132,136,140,144,149,153,157,161,165)
# Must match the passive-only channel set advertised by AICInfraInterface.
NATIVE_PASSIVE_CHANNELS_24GHZ=tuple(range(1,12))
NATIVE_PASSIVE_CHANNELS_5GHZ=(36,40,44,48)
DFS_CHANNELS_5GHZ=frozenset(range(52,65,4))|frozenset(range(100,145,4))
CONNECTABLE_CHANNELS_5GHZ=frozenset(CHANNELS_5GHZ)-DFS_CHANNELS_5GHZ

def me_channel_config_request():
    """Build the regulatory channel table required after ME_CONFIG_REQ."""
    req=MEChannelConfig()
    channels_2g=[(2407+5*channel,0,0,20) for channel in range(1,14)]
    channels_2g.append((2484,0,2,20)) # Channel 14 is disabled in Brazil.
    channels_5g=[(5000+5*channel,1,
                  1|4 if channel in DFS_CHANNELS_5GHZ else 0,23)
                 for channel in CHANNELS_5GHZ]
    for destination,values in ((req.channels_2g,channels_2g),
                               (req.channels_5g,channels_5g)):
        for index,(frequency,band,flags,power) in enumerate(values):
            destination[index].frequency=frequency
            destination[index].band=band
            destination[index].flags=flags
            destination[index].power=power
    req.count_2g=len(channels_2g);req.count_5g=len(channels_5g)
    return bytes(req)

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
            if size>=2:
                secondary=frame[cursor+1]&3
                result['_ht_width_mhz']=40 if frame[cursor+1]&4 and secondary in (1,3) else 20
                result['_ht_secondary']='above' if secondary==1 else ('below' if secondary==3 else 'none')
        elif kind==192 and size>=3: # VHT Operation
            width,center0,center1=frame[cursor:cursor+3]
            result['_vht_operation']={'width_code':width,
                                      'center_segment_0':center0,
                                      'center_segment_1':center1}
        elif kind==48:
            result['rsn']=frame[cursor:cursor+size].hex()
        cursor+=size
    if cursor!=len(frame):return None
    if include_beacon:
        result['_beacon']={'interval':struct.unpack_from('<H',frame,32)[0],
            'capability':struct.unpack_from('<H',frame,34)[0], 'ies':frame[36:],
            'frame':frame if (frame[0]&0xfc)==0x80 else None}
    return result

def association_diagnostics(body):
    """Extract negotiated channel and selected capability IEs from SM_CONNECT_IND."""
    if len(body)<836:return None
    request_length,response_length=struct.unpack_from('<HH',body,14)
    if request_length+response_length>800:return None
    request=body[20:20+request_length]
    response=body[20+request_length:20+request_length+response_length]

    def selected_ies(raw):
        result={};cursor=0
        while cursor+2<=len(raw):
            kind,size=raw[cursor:cursor+2];cursor+=2
            if cursor+size>len(raw):return None
            if kind in (45,61,191,192,199):result[kind]=raw[cursor:cursor+size].hex()
            cursor+=size
        return result if cursor==len(raw) else None

    request_ies=selected_ies(request);response_ies=selected_ies(response)
    if request_ies is None or response_ies is None:return None
    return {'width_code':body[826],
            'primary_frequency':struct.unpack_from('<H',body,824)[0],
            'center_frequency_1':struct.unpack_from('<I',body,828)[0],
            'center_frequency_2':struct.unpack_from('<I',body,832)[0],
            'request_ht_capability':request_ies.get(45),
            'request_vht_capability':request_ies.get(191),
            'request_operating_mode':request_ies.get(199),
            'response_ht_operation':response_ies.get(61),
            'response_vht_operation':response_ies.get(192)}

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
    if frequency>=5000:
        # VHT Operating Mode Notification: 80 MHz, one RX spatial stream.
        # The BE220 advertises a revised 160 MHz layout; firmware 0x06090101
        # otherwise falls back to HT40 even though this D81 supports VHT80.
        ie+=bytes.fromhex('c70102')
    req.ie_len=len(ie)
    c.memmove(c.addressof(req)+Connect.ies.offset,ie,len(ie))
    return bytes(req)
