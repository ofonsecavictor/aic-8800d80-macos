#pragma once
/* Packet format from ademasi/aic8800d80-wifi-bt-linux.
 * This transport sends REQUEST SENSE then the vendor F2 command; no firmware is flashed. */
static inline void aicMakeCBW(unsigned char *p, unsigned char command) {
    for (unsigned i = 0; i < 31; ++i) p[i] = 0;
    p[0]=0x55; p[1]=0x53; p[2]=0x42; p[3]=0x43;
    p[4]=0x87; p[5]=0x65; p[6]=0x43; p[7]=0x21;
    if (command==3) {
        p[8]=18; p[12]=0x80; p[14]=6; p[15]=3; p[19]=18;
    } else {p[14]=16; p[15]=0xfd; p[30]=command;}
}
static inline bool aicValidCSW(const unsigned char *p, unsigned size) {
    if (size != 13) return false;
    const unsigned char header[8]={0x55,0x53,0x42,0x53,0x87,0x65,0x43,0x21};
    for (unsigned i=0;i<8;++i) if (p[i]!=header[i]) return false;
    for (unsigned i=8;i<13;++i) if (p[i]!=0) return false;
    return true;
}
