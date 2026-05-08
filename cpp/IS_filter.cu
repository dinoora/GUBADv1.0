/**
 * @author Gao Jian
 * @email gaoj@njupt.edu.cn
 * @create date 2021-06-03 10:38:05
 * @desc 连接破碎的小块
 */

#include "defs.h"

// PAVA (Pool Adjacent Violators Algorithm，池相邻违规者算法) 是实现 保序回归 (Isotonic Regression) 最经典、最常用的算法。

#define NN 20
// --- CUDA Kernel: 批量保序回归 ---
// grid/block 维度设计：
// 每个线程处理一行数据 (一条时间序列)
// inputs: [rows * cols]
// outputs: [rows * cols]
// workspace_weights: [rows * cols] (辅助显存，用于存储栈中的权重)
// workspace_indices: [rows * cols] (辅助显存，用于模拟栈顶位置，可选优化)
__global__ void isotonic_batch_kernel(unsigned char *gdata, int *gnw,
                                      int *gnh, double *ggeot, int *gpos, int nd)
{
  // 参考第一个数据的坐标，其他数据以最近投影位置对齐
  unsigned nz = gnw[0] * gnh[0];
  unsigned increment = blockDim.x * gridDim.x;
  unsigned nits = nz / increment + 1;
  unsigned idx = blockDim.x * blockIdx.x + threadIdx.x;

  float soutput[NN];   // 滤波结果存储
  float sweight[NN];   // 栈中权重存储
  unsigned sindex[NN]; // 栈中索引存储
  for (unsigned nit = 0; nit < nits; nit++, idx += increment)
  {
    if (idx >= nz)
      break;

    // if (idx == 0)
    //   printf("Index: %d, %d, %d, %d\n", increment, blockDim.x, gridDim.x, nits);

    // if (idx / gnw[0] > 300)
    //   printf("(%d,%d)%c", idx % gnw[0], idx / gnw[0], idx % 10 ? ' ' : '\n');

    // if (idx != 113 * gnw[0] + 280)
    //   break;

    // printf("Index: %d\n", idx);

    // 不同数据中的坐标索引计算和提取数据，越界则跳过
    int ix = idx % gnw[0], iy = idx / gnw[0];
    double xi = ggeot[0] + (ix + 0.5) * ggeot[1];
    double yi = ggeot[3] + (iy + 0.5) * ggeot[5];
    sindex[0] = iy * gnw[0] + ix;
    int valid = 1;
    for (int i = 1; i < nd; i++)
    {
      double xp = (xi - ggeot[i * 6]) / ggeot[i * 6 + 1];
      double yp = (yi - ggeot[i * 6 + 3]) / ggeot[i * 6 + 5];
      int ixp = (int)(xp);
      int iyp = (int)(yp);

      if (ixp < 0 || iyp < 0 || ixp >= gnw[i] || iyp >= gnh[i])
      {
        valid = 0;
        break;
      }
      sindex[i] = iyp * gnw[i] + ixp;
    }

    if (!valid)
      continue;

    int top = -1;

    // --- PAVA 算法主循环 ---
    for (int i = 0; i < nd; ++i)
    {
      // 1. 获取新元素
      float curr_val = (gdata + gpos[i])[sindex[i]];
      float curr_weight = 1.0f;
      if (!i)
        curr_weight *= 2.0f; // 第一个数据权重加倍

      // 2. 回溯合并 (Pool)
      // 当栈不为空，且前一个块的值 >= 当前块的值时
      while (top >= 0)
      {
        float prev_val = soutput[top];

        if (prev_val < curr_val)
        {
          break; // 满足单调性，停止回溯
        }

        float prev_weight = sweight[top];

        // 合并：计算加权平均
        // 公式: (v1*w1 + v2*w2) / (w1+w2)
        curr_val = (prev_val * prev_weight + curr_val * curr_weight) / (prev_weight + curr_weight);
        curr_weight = prev_weight + curr_weight;

        // 弹出栈顶
        top--;
      }

      // 3. 入栈 (Push)
      top++;
      soutput[top] = curr_val;
      sweight[top] = curr_weight;
    }

    // --- 重建输出序列 (Unroll) ---

    int write_idx = nd - 1; // 从数组最末尾开始写
    for (int stack_idx = top; stack_idx >= 0; --stack_idx)
    {
      float val = soutput[stack_idx];
      int count = (int)sweight[stack_idx]; // 权重即数量

      // 填充 count 个 val
      for (int k = 0; k < count; ++k)
      {
        int id = write_idx--;
        gdata[gpos[id] + sindex[id]] = val > 0.5 ? 1 : 0;

        // printf("(%f %d)", val, gdata[gpos[id] + sindex[id]]);
      }
      // printf("\n");
    }
  }
}

void filter_IS(unsigned char **pdata, int *nw, int *nh, double *geot, int nd)
{
  int *pos = new int[nd];

  pos[0] = 0;
  int sum = nw[0] * nh[0];
  for (int i = 0; i < nd; i++)
  {
    pos[i] = pos[i - 1] + nw[i - 1] * nh[i - 1];
    sum += nw[i] * nh[i];

    // printf("Data %d: size (%d, %d), pos %d\n", i, nw[i], nh[i], pos[i]);
  }

  unsigned char *gdata;
  int *gnw, *gnh, *gpos;
  // float* goutput, *gweight;
  double *ggeot;
  cudaMalloc((void **)&gnw, nd * sizeof(int));
  cudaMalloc((void **)&gnh, nd * sizeof(int));
  cudaMalloc((void **)&gpos, nd * sizeof(int));
  cudaMalloc((void **)&ggeot, 6 * nd * sizeof(double));
  cudaMalloc((void **)&gdata, sum * sizeof(unsigned char));
  cudaMemcpy(gnw, nw, nd * sizeof(int), cudaMemcpyHostToDevice);
  cudaMemcpy(gnh, nh, nd * sizeof(int), cudaMemcpyHostToDevice);
  cudaMemcpy(gpos, pos, nd * sizeof(int), cudaMemcpyHostToDevice);
  cudaMemcpy(ggeot, geot, 6 * nd * sizeof(double), cudaMemcpyHostToDevice);
  for (unsigned i = 0; i < nd; i++)
  {
    unsigned nz = nw[i] * nh[i] * sizeof(unsigned char);
    cudaMemcpy(gdata + pos[i], pdata[i], nz, cudaMemcpyHostToDevice);
  }

  // printf("Launching isotonic batch kernel...\n");

  isotonic_batch_kernel<<<NUM_BLOCKS, NUM_THREADS>>>(gdata, gnw, gnh, ggeot, gpos, nd);

  for (unsigned i = 0; i < nd; i++)
  {
    unsigned nz = nw[i] * nh[i] * sizeof(unsigned char);
    cudaMemcpy(pdata[i], gdata + pos[i], nz, cudaMemcpyDeviceToHost);
  }
  cudaFree(gnw);
  cudaFree(gnh);
  cudaFree(ggeot);
  cudaFree(gdata);
  delete[] pos;
}
