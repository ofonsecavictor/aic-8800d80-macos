/* macOS USB transport. Protocol reference: radxa-pkg/aic8800, e9e43ed.
 * This file supplies USB transport only; Python selects the operations.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/usb/IOUSBLib.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef struct {IOUSBInterfaceInterface300 **usb;UInt8 in,out;uint32_t location;} AIC;
static int number(io_service_t s,CFStringRef key){int n=-1;CFTypeRef v=IORegistryEntryCreateCFProperty(s,key,0,0);if(v){if(CFGetTypeID(v)==CFNumberGetTypeID())CFNumberGetValue(v,kCFNumberIntType,&n);CFRelease(v);}return n;}
void aic_close(AIC *a){if(a){if(a->usb){(*a->usb)->USBInterfaceClose(a->usb);(*a->usb)->Release(a->usb);}free(a);}}
AIC *aic_open(void){
 io_iterator_t it=0;if(IOServiceGetMatchingServices(kIOMainPortDefault,IOServiceMatching("IOUSBHostInterface"),&it))return NULL;
 io_service_t s;AIC *a=NULL;
 while((s=IOIteratorNext(it))){
  int target=number(s,CFSTR("idVendor"))==0xa69c && number(s,CFSTR("idProduct"))==0x8d80 && number(s,CFSTR("bInterfaceNumber"))==0;
  if(!target){IOObjectRelease(s);continue;}
  uint32_t location=(uint32_t)number(s,CFSTR("locationID"));
  IOCFPlugInInterface **p=NULL;SInt32 score=0;IOReturn r=IOCreatePlugInInterfaceForService(s,kIOUSBInterfaceUserClientTypeID,kIOCFPlugInInterfaceID,&p,&score);IOObjectRelease(s);if(r||!p)break;
  a=calloc(1,sizeof(*a));if(!a){IODestroyPlugInInterface(p);break;}
  a->location=location;
  HRESULT h=(*p)->QueryInterface(p,CFUUIDGetUUIDBytes(kIOUSBInterfaceInterfaceID300),(LPVOID*)&a->usb);IODestroyPlugInInterface(p);
  if(h||!a->usb){aic_close(a);a=NULL;break;}
  if((*a->usb)->USBInterfaceOpen(a->usb)){(*a->usb)->Release(a->usb);a->usb=NULL;aic_close(a);a=NULL;break;}
  UInt8 count=0;(*a->usb)->GetNumEndpoints(a->usb,&count);
  for(UInt8 n=1;n<=count;n++){UInt8 dir,num,type,interval;UInt16 max;
   if(!(*a->usb)->GetPipeProperties(a->usb,n,&dir,&num,&type,&max,&interval)&&type==kUSBBulk){if(dir==kUSBIn)a->in=n;else if(dir==kUSBOut)a->out=n;}}
  if(!a->in||!a->out){aic_close(a);a=NULL;}break;
 }IOObjectRelease(it);return a;
}
static unsigned get16(const unsigned char *p){return p[0]|((unsigned)p[1]<<8);}
/* Returns IOReturn, or 0 and an independently checked confirmation payload. */
uint32_t aic_rpc(AIC *a,uint16_t id,const void *payload,uint16_t length,void *reply,uint32_t *replyLength){
 if(!a||!payload||!reply||!replyLength||length>1032)return 0xe00002c2;
 if(id!=0x400&&id!=0x402&&id!=0x40b&&id!=0x40d)return 0xe00002c2;
 unsigned char packet[1048]={0};unsigned total=length+16;unsigned header=length+12;
 packet[0]=header&255;packet[1]=(header>>8)&15;packet[2]=0x11;
 packet[8]=id&255;packet[9]=id>>8;packet[10]=1;packet[12]=100;packet[14]=length&255;packet[15]=length>>8;memcpy(packet+16,payload,length);
 IOReturn r=(*a->usb)->WritePipeTO(a->usb,a->out,packet,total,2000,4000);if(r)return r;
 for(unsigned tries=0;tries<6;tries++){
  unsigned char response[4096]={0};UInt32 n=sizeof(response);
  r=(*a->usb)->ReadPipeTO(a->usb,a->in,response,&n,2000,4000);if(r)return r;
  unsigned offset=0;
  while(offset+16<=n){const unsigned char *p=response+offset;unsigned frame=get16(p);unsigned body=get16(p+10);
   if(frame<12||frame+4>n-offset||body>frame-12)return 0xe00002bc;
   if((p[2]&0x7f)==0x11&&get16(p+4)==id+1){if(body>*replyLength)return 0xe00002e8;memcpy(reply,p+16,body);*replyLength=body;return 0;}
   offset+=(frame+4+3)&~3u;
  }
 }return 0xe00002d6;
}
static uint64_t find_device_id(int product,uint32_t location) {
 io_iterator_t it=0;uint64_t entry=0;
 if(IOServiceGetMatchingServices(kIOMainPortDefault,IOServiceMatching("IOUSBHostDevice"),&it))return 0;
 io_service_t s;while((s=IOIteratorNext(it))){
  if(number(s,CFSTR("idVendor"))==0xa69c&&number(s,CFSTR("idProduct"))==product&&(!location||(uint32_t)number(s,CFSTR("locationID"))==location)){IORegistryEntryGetRegistryEntryID(s,&entry);IOObjectRelease(s);break;}
  IOObjectRelease(s);
 }IOObjectRelease(it);return entry;
}
uint64_t aic_loader_id(void){return find_device_id(0x8d80,0);}
uint32_t aic_location(AIC *a){return a?a->location:0;}
uint64_t aic_active_at(uint32_t location){return location?find_device_id(0x8d81,location):0;}
