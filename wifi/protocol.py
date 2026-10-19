"""Bounded encoding/decoding for AIC USB FullMAC command frames."""
import struct


def command(message_id, payload=b''):
    if not 0 <= message_id <= 0xffff or len(payload)>2032:
        raise ValueError('invalid message or size')
    task=message_id>>10
    return struct.pack('<HBBIHHHH',12+len(payload),0x11,0,0,
                       message_id,task,100,len(payload))+payload


def messages(data):
    offset=0
    while offset<len(data):
        if len(data)-offset<4:
            if any(data[offset:]):
                raise ValueError('truncated USB header')
            return
        size,kind=struct.unpack_from('<HB',data,offset)
        end=offset+size+4
        if size==0 and not any(data[offset:]):
            return
        if end>len(data):
            raise ValueError('invalid USB frame length')
        if kind&0x7f==0x11:
            if size<12:raise ValueError('truncated command response header')
            msg,destination,source,length,pattern=struct.unpack_from('<HHHHI',data,offset+4)
            if length>size-12:
                raise ValueError('invalid message payload length')
            # These are dummy/stamp fields of the shared-memory IPC layout.
            # The USB firmware leaves them uninitialized; the Linux USB path
            # dispatches using only id and bounded param_len as well.
            yield msg,data[offset+16:offset+16+length]
        elif kind&0x7f==0x12:
            if size!=8:raise ValueError('invalid TX confirmation size')
            yield 0x10000,data[offset+4:end]
        offset=(end+3)&~3
