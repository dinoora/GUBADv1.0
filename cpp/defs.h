#ifndef __COMMON_DEF_H__
#define __COMMON_DEF_H__

#include <stdio.h>
#include <cuda.h>
#include <device_launch_parameters.h>
#include <npp.h>

#define NUM_THREADS 1024
#define NUM_BLOCKS 256

#define J1_0 0x00 // 单像素，不做连接
#define J1_1 0x01 // 单像素，十字连接
#define J1_2 0x02 // 单像素，丫字连接
#define J1_4 0x04 // 单像素，叉字连接
#define J1_8 0x08 // 单像素，区域内连接开关
#define J2_0 0x00 // 双像素，不做连接
#define J2_1 0x10 // 双像素，十字连接
#define J2_2 0x20 // 双像素，丫字连接
#define J2_4 0x40 // 双像素，叉字连接
#define J2_8 0x80 // 双像素，区域内连接开关

#define AR_BUA 0x01
#define AR_NUL 0x00

#endif
