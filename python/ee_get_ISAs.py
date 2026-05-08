#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time
import subprocess
from pathlib import Path
import argparse
import shutil

import numpy as np
import geopandas as gpd
from osgeo import gdal
import ee

import ee_get_dataset


# =====================================================================================

years = ["2000", "2005", "2010", "2015", "2020", "2025"]

# =====================================================================================

dir_shp_l1 = "/home/PROJECT/GEE/31_ISA/L1"
dir_shp_l3 = "/home/PROJECT/GEE/32_BUA_UN/L3"


def getshplist(dir_flt, dir_tif, update=False):
    numt = 0
    shpfiles = []
    dir = dir_flt

    country = dir.rsplit("/", 1)[-1]
    dir2 = dir.rsplit("/", 1)[-2]
    continent = dir2.rsplit("/", 1)[-1]
    # print(dir)
    files = os.listdir(dir)
    for file in files:
        if file.endswith(".shp"):
            city = file.rsplit(".", 1)[0]
            # print(continent+'/'+country+'/'+city)
            disa = dir_tif + "/" + continent + "/" + country
            label = False
            for yr in years:
                if not os.path.exists(disa + "/" + city + "/" + city + yr + ".tif"):
                    numt += 1
                    if label == False:
                        label = True
                        shpfiles.append(dir + "/" + file)

            # 删除待更新的已有文件夹
            if update and label:
                dir1 = dir_shp_l1 + "/" + continent + "/" + country + "/" + city
                dir2 = dir_shp_l3 + "/" + continent + "/" + country + "/" + city
                if os.path.exists(dir1):
                    shutil.rmtree(dir1)
                if os.path.exists(dir2):
                    shutil.rmtree(dir2)

    return shpfiles, numt


def gee_city_ISA(shpfiles, numt, dir_IS, ext=0, mode=1, ls=0):

    tmax = 3  # gee并行保存最大线程数目设置
    tasks = []
    iii = 0

    for idx, ctyshp in enumerate(shpfiles):
        # print(ctyshp)

        dir, file = os.path.split(ctyshp)
        country = dir.rsplit("/", 1)[-1]
        dir2 = dir.rsplit("/", 1)[-2]
        continent = dir2.rsplit("/", 1)[-1]
        city = file.rsplit(".", 1)[0]

        print("  -- " + continent + " - " + country + " - " + city)

        disa = dir_IS + "/" + continent + "/" + country + "/" + city
        if not os.path.exists(disa):
            # print("no "+disa+" found!")
            os.makedirs(disa)

        fsamples = (
            "/home/PROJECT/GEE/30_samples/"
            + continent
            + "/"
            + country
            + "/sp_"
            + city
            + ".shp"
        )

        gdf = gpd.read_file(fsamples)
        ee_samples = ee.FeatureCollection(gdf.__geo_interface__)

        for yr in years:

            if os.path.exists(disa + "/" + city + yr + ".tif"):
                continue

            try:

                myshp = gpd.read_file(ctyshp)
                my_geometry = ee.Geometry.Rectangle(myshp.total_bounds.tolist())

                outputBucket = "ISA_" + country

                year = int(yr)
                scale = 30

                if yr == "2025":
                    # year = 2024
                    scale = 10

                if year <= 2015 and ls != 0:
                    if ls == 5:
                        VWB = ee_get_dataset.GET_DATA_LS5(year, ext, my_geometry, mode)
                    elif ls == 7:
                        VWB = ee_get_dataset.GET_DATA_LS7(year, ext, my_geometry, mode)
                    elif ls == 8:
                        VWB = ee_get_dataset.GET_DATA_LS8(year, ext, my_geometry, mode)
                else:
                    VWB = ee_get_dataset.GET_DATA_ST(year, ext, my_geometry, mode)

                image = VWB
                # ee.Image(VWB)
                bands = image.bandNames()
                # print(bands.getInfo())

                training = image.select(bands).sampleRegions(
                    collection=ee_samples, properties=["class"], scale=10
                )

                numberOfTrees = 100
                minLeafPopulation = 5  # 稍微调高以防止过拟合和节省内存
                # trained = ee.Classifier.smileCart().train(training, 'class', bands)
                trained = ee.Classifier.smileRandomForest(
                    numberOfTrees=numberOfTrees, minLeafPopulation=minLeafPopulation
                ).train(training, "class", bands)

                #        print(trained.getInfo())

                classified = image.select(bands).classify(trained)
                ISA = classified.reduceNeighborhood(
                    ee.Reducer.mode(), ee.Kernel.square(1.5)
                )

            except Exception as e:
                os.system(
                    'printf " --*--*--*-- Warnning: %s | %s failed! --*--*--*-- \n" '
                    + str(country)
                    + " "
                    + str(city)
                )
                continue

            # print(ISA.getInfo())

            # ===================================================================
            # 数据输出

            savename = city + yr
            task = ee.batch.Export.image.toDrive(
                **{
                    "image": ISA,
                    "crs": "EPSG:4326",
                    "description": savename,
                    "scale": scale,
                    "maxPixels": 10000000000000,
                    "region": my_geometry,
                    "folder": outputBucket,
                }
            )
            task.start()
            iii += 1

            tasks.append(task)

            dt = 3
            if len(tasks) > 0:
                os.system(
                    'printf " [%s/%s] - %s | %s : \t" '
                    + str(idx + 1)
                    + "/"
                    + str(len(shpfiles))
                    + " "
                    + str(country)
                    + " "
                    + str(city)
                    + " "
                    + yr
                )
                tt = 0
                while any([task.active() for task in tasks]):
                    arr = [task.active() for task in tasks]
                    at = np.count_nonzero(arr)
                    tt = tt + 1
                    if tt % 20 == 0:
                        os.system('printf "[%s/%s]" ' + str(tt // 20) + " " + str(at))
                    else:
                        os.system('printf "%s" ' + "-")
                    time.sleep(dt)
                    if at < tmax and iii < numt:
                        # os.system('printf " <<< \n"')
                        break
                os.system('printf " <<< \n"')


def download_city_ISA(shpfiles, dir_IS):

    for ctyshp in shpfiles:
        # print(ctyshp)

        dir, file = os.path.split(ctyshp)
        country = dir.rsplit("/", 1)[-1]
        dir2 = dir.rsplit("/", 1)[-2]
        continent = dir2.rsplit("/", 1)[-1]
        city = file.rsplit(".", 1)[0]

        disa = dir_IS + "/" + continent + "/" + country + "/" + city

        for yr in years:
            if not os.path.exists(disa + "/" + city + yr + ".tif"):

                print(
                    "  downloading "
                    + continent
                    + " - "
                    + country
                    + " - "
                    + city
                    + " - "
                    + yr
                )

                # 构建命令
                command = [
                    "rclone",
                    "move",
                    "gdrive:ISA_" + country,
                    disa,
                    "--include",
                    city + yr + "*.tif",
                ]

                try:
                    # 执行命令并实时打印输出
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )

                    for line in process.stdout:
                        print(line, end="")  # 在终端实时打印 rclone 的进度

                    process.wait()
                    if process.returncode != 0:
                        print(f"\n下载失败,退出码: {process.returncode}")
                        exit()

                except FileNotFoundError:
                    print("错误：未在系统中找到 rclone, 请先安装并添加到环境变量.")
                    exit()

                flist = list(Path(disa).glob(city + yr + "*.tif"))
                if len(flist) > 1:
                    gdal.BuildVRT(disa + "/" + city + "_" + yr + ".vrt", flist)
                    gdal.Translate(
                        disa + "/" + city + yr + ".tif",
                        disa + "/" + city + "_" + yr + ".vrt",
                        format="GTiff",
                        creationOptions=["COMPRESS=LZW"],
                    )
                    os.remove(disa + "/" + city + "_" + yr + ".vrt")
                    # for f in flist:
                    #     os.remove(f)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="GEE提取不透水面脚本")

    parser.add_argument("filter", help="路径过滤")
    parser.add_argument("output", help="ISA输出目录")
    parser.add_argument("-e", "--extend", type=int, default=0, help="时间扩展(年)")
    parser.add_argument("-l", "--landsat", type=int, default=5, help="使用LS-5/7/8数据")
    parser.add_argument("-y", "--yes", action="store_true", help="GEE处理并下载")
    parser.add_argument("-p", "--process", action="store_true", help="仅GEE处理")
    parser.add_argument("-d", "--download", action="store_true", help="仅下载文件")
    parser.add_argument("-u", "--update", action="store_true", help="更新31/L1和32/L3")
    parser.add_argument(
        "-m", "--mode", type=int, default=1, help="模式:0 - 原始波段; 1 - NWB"
    )

    args = parser.parse_args()

    shpfiles, numt = getshplist(args.filter, args.output, args.update)

    if len(shpfiles) == 0:
        exit()

    for idx, ctyshp in enumerate(shpfiles):
        dir, file = os.path.split(ctyshp)
        country = dir.rsplit("/", 1)[-1]
        dir2 = dir.rsplit("/", 1)[-2]
        continent = dir2.rsplit("/", 1)[-1]
        city = file.rsplit(".", 1)[0]
        print(f" - [{idx+1:4d} / {numt:<4d}] {continent} - {country} - {city}")

    print(f" === {len(shpfiles)} cities, {numt} files waiting for processing: ")

    if args.process or args.yes:
        try:
            ee.Initialize()
        except Exception as e:
            ee.Authenticate()
            ee.Initialize(project=os.environ.get("GCLOUD_PROJECT_NAME"))

        gee_city_ISA(shpfiles, numt, args.output, args.extend, args.mode, args.landsat)

    if args.download or args.yes:
        download_city_ISA(shpfiles, args.output)
