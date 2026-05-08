/**
 * @author Gao Jian
 * @email gaoj@njupt.edu.cn
 * @create date 2021-06-03 10:23:40
 * @desc
 */

#define cimg_use_tiff

#include <CImg.h>
#include <cuda_runtime.h>
#include <gdal.h>
#include <iostream>

using namespace std;
using namespace cimg_library;

void filter_IS(unsigned char **pdata, int *nw, int *nh, double *geot, int nd);
void PrintDeviceInfo();

int main(int argc, char **argv)
{

  // 输入最少3个tif数据文件，按照时间顺序
  if (argc < 4)
  {
    printf("Usage: %s <input_tif1> <input_tif2> <input_tif3> [<input_tif4> ...] \n",
           argv[0]);

    return -1;
  }

  {
    printf("========== IS Filter. ==========\n");

    for (int i = 1; i < argc; i++)
    {
      printf(" [%d] - %s\n", i, argv[i]);
    }
  }

  // =========================================================================
  int nfiles = argc - 1;
  GDALAllRegister();
  GDALDatasetH hDataset[nfiles];
  GDALRasterBandH hBand[nfiles];
  int *nw = new int[nfiles];
  int *nh = new int[nfiles];
  double *geot = new double[6 * (nfiles)];
  unsigned char **pdata = new unsigned char *[nfiles];

  for (int i = 0; i < nfiles; i++)
  {
    hDataset[i] = GDALOpen(argv[i + 1], GA_Update);
    hBand[i] = GDALGetRasterBand(hDataset[i], 1);
  }

  CPLErr error;
  for (int i = 0; i < nfiles; i++)
  {
    nw[i] = GDALGetRasterXSize(hDataset[i]);
    nh[i] = GDALGetRasterYSize(hDataset[i]);
    pdata[i] = new unsigned char[nw[i] * nh[i]];
    GDALGetGeoTransform(hDataset[i], &geot[6 * i]);
    error =
        GDALRasterIO(hBand[i], GF_Read, 0, 0, nw[i], nh[i],
                     pdata[i], nw[i], nh[i], GDT_Byte, 0, 0);

    // printf("Loaded file %d: size (%d, %d)\n", i + 1, nw[i], nh[i]);
  }

  filter_IS(pdata, nw, nh, geot, nfiles);

  // =========================================================================

  for (int i = 0; i < nfiles; i++)
  {
    error =
        GDALRasterIO(hBand[i], GF_Write, 0, 0, nw[i], nh[i],
                     pdata[i], nw[i], nh[i], GDT_Byte, 0, 0);
    GDALClose(hDataset[i]);
  }

  delete[] nw;
  delete[] nh;
  delete[] geot;
  for (int i = 0; i < nfiles; ++i)
  {
    delete[] pdata[i];
  }
  delete[] pdata;

  // =========================================================================

  // if (verbose)
  printf("========================= <<<< Finished. >>>> "
         "=========================\n");

  return 0;
}
