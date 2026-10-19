/* AIC8800D80 FullMAC USB transport, reference radxa e9e43ed.
 * Opens only the verified Wi-Fi interface; never resets the composite device.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/usb/IOUSBLib.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <CommonCrypto/CommonSymmetricKeywrap.h>
typedef struct {IOUSBInterfaceInterface300 **usb;UInt8 dataIn,dataOut,msgIn,msgOut;uint32_t location;uint64_t registryID;} Wifi;
static int number(io_service_t s,CFStringRef k){int n=-1;CFTypeRef v=IORegistryEntryCreateCFProperty(s,k,0,0);if(v){if(CFGetTypeID(v)==CFNumberGetTypeID())CFNumberGetValue(v,kCFNumberIntType,&n);CFRelease(v);}return n;}
static int stringIs(io_service_t s,CFStringRef k,CFStringRef expected){CFTypeRef v=IORegistryEntryCreateCFProperty(s,k,0,0);int ok=v&&CFGetTypeID(v)==CFStringGetTypeID()&&CFEqual(v,expected);if(v)CFRelease(v);return ok;}
void wifi_close(Wifi *w){if(w){if(w->usb){(*w->usb)->USBInterfaceClose(w->usb);(*w->usb)->Release(w->usb);}free(w);}}
Wifi *wifi_open(uint32_t *error){
 io_iterator_t it=0;io_service_t s;Wifi *w=NULL;*error=0xe00002c0;
 IOReturn r=IOServiceGetMatchingServices(kIOMainPortDefault,IOServiceMatching("IOUSBHostInterface"),&it);if(r){*error=r;return NULL;}
 while((s=IOIteratorNext(it))){
  int target=number(s,CFSTR("idVendor"))==0xa69c&&number(s,CFSTR("idProduct"))==0x8d81&&number(s,CFSTR("bInterfaceNumber"))==2&&number(s,CFSTR("bInterfaceClass"))==255&&stringIs(s,CFSTR("USB Serial Number"),CFSTR("20220103"))&&stringIs(s,CFSTR("USB Product Name"),CFSTR("AIC 8800D80"));
  if(!target){IOObjectRelease(s);continue;}
  uint32_t location=(uint32_t)number(s,CFSTR("locationID"));
  uint64_t registryID=0;IORegistryEntryGetRegistryEntryID(s,&registryID);
  IOCFPlugInInterface **plugin=NULL;SInt32 score=0;r=IOCreatePlugInInterfaceForService(s,kIOUSBInterfaceUserClientTypeID,kIOCFPlugInInterfaceID,&plugin,&score);IOObjectRelease(s);
  if(r||!plugin){*error=r?r:0xe00002bc;break;}
  w=calloc(1,sizeof(*w));if(!w){IODestroyPlugInInterface(plugin);*error=0xe00002bd;break;}w->location=location;w->registryID=registryID;
  HRESULT h=(*plugin)->QueryInterface(plugin,CFUUIDGetUUIDBytes(kIOUSBInterfaceInterfaceID300),(LPVOID*)&w->usb);IODestroyPlugInInterface(plugin);
  if(h||!w->usb){*error=(uint32_t)h;wifi_close(w);w=NULL;break;}
  r=(*w->usb)->USBInterfaceOpen(w->usb);
  if(r){*error=r;(*w->usb)->Release(w->usb);w->usb=NULL;wifi_close(w);w=NULL;break;}
  UInt8 count=0;(*w->usb)->GetNumEndpoints(w->usb,&count);
  unsigned ins=0,outs=0;
  for(UInt8 p=1;p<=count;p++){UInt8 direction,number,type,interval;UInt16 size;
   if((*w->usb)->GetPipeProperties(w->usb,p,&direction,&number,&type,&size,&interval)||type!=kUSBBulk)continue;
   if(direction==kUSBIn){if(!ins++)w->dataIn=p;else w->msgIn=p;}
   else {if(!outs++)w->dataOut=p;else w->msgOut=p;}
  }
  if(ins!=2||outs!=2||!w->msgIn||!w->msgOut){*error=0xe00002bc;wifi_close(w);w=NULL;}else *error=0;
  break;
 }IOObjectRelease(it);return w;
}
uint32_t wifi_location(Wifi *w){return w?w->location:0;}
uint64_t wifi_registry_id(Wifi *w){return w?w->registryID:0;}
uint32_t wifi_write(Wifi *w,const void *data,uint32_t length){
 if(!w||!data||length<16||length>2048)return 0xe00002c2;
 const unsigned char *p=data;unsigned id=p[8]|((unsigned)p[9]<<8);
 /* Reference-derived FullMAC messages; never resets the USB device. */
 unsigned expected=0xffff;
 switch(id){case 0:case 4:expected=0;break;case 2:expected=72;break;
 case 6:expected=10;break;case 8:expected=1;break;case 14:expected=4;break;case 0x65:expected=16;break;case 0x69:expected=24;break;
 case 0x73:case 0x7b:expected=4;break;case 0x77:expected=95;break;
 case 70:expected=20;break; /* MM_REMAIN_ON_CHANNEL_REQ, research branch only. */
 case 0x1411:expected=14;break; /* ME_CONFIG_MONITOR_REQ, research branch only. */
 case 0x24:expected=44;break;case 0x26:expected=1;break;case 0x1404:expected=2;break;
 case 0x1000:expected=376;break;case 0x1800:expected=320;break;case 0x1803:expected=4;break;}
 if(expected==0xffff||length!=expected+16||p[14]!=(expected&255)||p[15]!=(expected>>8))return 0xe00002c2;
 return (*w->usb)->WritePipeTO(w->usb,w->msgOut,(void *)data,length,1000,2000);
}
uint32_t wifi_read(Wifi *w,void *data,uint32_t *length){
 if(!w||!data||!length||*length>65536)return 0xe00002c2;
 return (*w->usb)->ReadPipeTO(w->usb,w->msgIn,data,(UInt32 *)length,1000,2000);
}
uint32_t wifi_read_data(Wifi *w,void *data,uint32_t *length){
 if(!w||!data||!length||*length>65536)return 0xe00002c2;
 return (*w->usb)->ReadPipeTO(w->usb,w->dataIn,data,(UInt32 *)length,250,500);
}
uint32_t wifi_validate_data_frame(const void *data,uint32_t length){
 if(!data||length<32||length>2048)return 0xe00002c2;
 const uint8_t *p=data;
 if((p[0]|((unsigned)p[1]<<8))!=length||p[2]!=1||p[3]!=0)return 0xe00002c2;
 unsigned payload=p[4]|((unsigned)p[5]<<8);
 if(payload>length-32||length-32-payload>3||p[28]>3)return 0xe00002c2;
 unsigned flags=p[30]|((unsigned)p[31]<<8);
 if(flags==8){
  /* Research-only 802.11 action TX: bounded, confirmed, unprotected. */
  if(payload<25||payload>512||p[26]!=3||p[27]!=255||p[29]!=255||!(p[11]&0x80))return 0xe00002c2;
  for(unsigned i=12;i<26;i++)if(p[i])return 0xe00002c2;
  unsigned fc=p[32]|((unsigned)p[33]<<8);
  if((fc&0xff)!=0xd0||(fc&0x4000))return 0xe00002c2;
  if(p[56]!=4&&p[56]!=127)return 0xe00002c2; /* No robust categories without PMF. */
 }else{
  /* Ethernet header lives in hostdesc; data area contains only payload. */
  if(flags||p[29]>31)return 0xe00002c2;
 }
 for(unsigned i=32+payload;i<length;i++)if(p[i])return 0xe00002c2;
 return 0;
}
uint32_t wifi_write_data(Wifi *w,const void *data,uint32_t length){
 if(!w)return 0xe00002c2;
 uint32_t status=wifi_validate_data_frame(data,length);
 if(status)return status;
 return (*w->usb)->WritePipeTO(w->usb,w->dataOut,(void *)data,length,1000,2000);
}
int wifi_unwrap(const uint8_t *key,const uint8_t *data,size_t size,uint8_t *output,size_t *outputSize){
 if(!key||!data||!output||!outputSize||size<24||size>2048||size%8)return -1;
 return CCSymmetricKeyUnwrap(kCCWRAPAES,CCrfc3394_iv,CCrfc3394_ivLen,key,16,data,size,output,outputSize);
}
