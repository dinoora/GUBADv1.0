# 脚本  获取landsat sentinel数据
# Gao Jian

# import processing

# from osgeo import gdal
import ee

# ee.initialize("gj313313", "gj113594")


def get_DateRange(dayear, ext):
    try:
        dy = int(ext) // 2
        dm = int(ext) % 2
        if dm == 0:
            return [str(dayear - dy) + "-01-01", str(dayear + dy + 1) + "-01-01"]
        else:
            return [str(dayear - dy - 1) + "-06-30", str(dayear + dy + 1) + "-06-30"]
    except:
        print("GETTING DATE RANGE ERRORS, CHECK YOUR SETTINGS!")


def cloudMaskL457(image):
    qa = image.select("QA_PIXEL")
    # If the cloud bit (5) is set and the cloud confidence (7) is high
    # or the cloud shadow bit is set (3), then it's a bad pixel.
    cloud = qa.bitwiseAnd(1 << 5).And(qa.bitwiseAnd(1 << 7)).Or(qa.bitwiseAnd(1 << 3))
    # Remove edge pixels that don't occur in all bands
    mask2 = image.mask().reduce(ee.Reducer.min())
    return image.updateMask(cloud.Not()).updateMask(mask2)


def cloudMaskLS7(image):
    qa = image.select("QA_PIXEL")
    # If the cloud bit (5) is set and the cloud confidence (7) is high
    # or the cloud shadow bit is set (3), then it's a bad pixel.
    cloud = qa.bitwiseAnd(1 << 3).And(qa.bitwiseAnd(1 << 9)).Or(qa.bitwiseAnd(1 << 4))
    # Remove edge pixels that don't occur in all bands
    mask2 = image.mask().reduce(ee.Reducer.min())
    return image.updateMask(cloud.Not()).updateMask(mask2)


def cloudMaskLS8(image):
    qa = image.select("QA_PIXEL")
    # If the cloud bit (3) is set and the cloud confidence (5) is high
    # or the cloud shadow bit is set (2), then it's a bad pixel.
    cloud = qa.bitwiseAnd(1 << 5).And(qa.bitwiseAnd(1 << 7)).Or(qa.bitwiseAnd(1 << 3))
    # Remove edge pixels that don't occur in all bands
    mask2 = image.mask().reduce(ee.Reducer.min())
    return image.updateMask(cloud.Not()).updateMask(mask2)


# **************************automaticed UB index**********************#


def L5_NDBI(img):
    NIR = img.select("SR_B4")
    SWIR = img.select("SR_B5")  # .rename("NDBI")
    NDBI = SWIR.subtract(NIR).divide(SWIR.add(NIR)).rename("NDBI")
    return img.addBands(NDBI)


def L5_NDWI(img):
    G = img.select("SR_B2")  # .rename("NDWI")
    NIR = img.select("SR_B4")
    NDWI = G.subtract(NIR).divide(G.add(NIR)).rename("NDWI")  # 干旱#
    return img.addBands(NDWI)


def L5_NDVI(img):
    R = img.select("SR_B3")
    NIR = img.select("SR_B4")  # .rename("NDVI")
    NDVI = NIR.subtract(R).divide(NIR.add(R)).rename("NDVI")
    return img.addBands(NDVI)


def L8_NDBI(img):
    NIR = img.select("SR_B5")
    SWIR = img.select("SR_B6")  # .rename("NDBI")
    NDBI = SWIR.subtract(NIR).divide(SWIR.add(NIR)).rename("NDBI")
    return img.addBands(NDBI)


def L8_NDWI(img):
    G = img.select("SR_B3")  # .rename("NDWI")
    NIR = img.select("SR_B5")
    NDWI = G.subtract(NIR).divide(G.add(NIR)).rename("NDWI")  # 干旱#
    return img.addBands(NDWI)


def L8_NDVI(img):
    R = img.select("SR_B4")
    NIR = img.select("SR_B5")  # .rename("NDVI")
    NDVI = NIR.subtract(R).divide(NIR.add(R)).rename("NDVI")
    return img.addBands(NDVI)


def GET_DATA_LS5(dayear, ext, my_geometry, mdt=0):
    try:
        daData = get_DateRange(dayear, ext)
        #         print(daData)var images = ee.ImageCollection("LT05/02/TOA")
        dataset = (
            ee.ImageCollection("LANDSAT/LT05/C02/T1_L2")
            .filterDate(daData[0], daData[1])
            .select(["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7", "QA_PIXEL"])
            .map(cloudMaskL457)
            .filterBounds(my_geometry)
        )

        if mdt == 0:
            return dataset.mean().select(["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5"])
        else:
            VWB = (
                dataset.map(L5_NDWI)
                .map(L5_NDVI)
                .map(L5_NDBI)
                .mean()
                .select(["NDVI", "NDWI", "NDBI"])
            )
            return VWB
    except:
        print("GETTING LANDSAT DATA ERRORS, CHECK YOUR SETTINGS!")


def GET_DATA_LS7(dayear, ext, my_geometry, mdt=0):
    try:
        daData = get_DateRange(dayear, ext)
        dataset = (
            ee.ImageCollection("LANDSAT/LE07/C02/T1_L2")
            .filterDate(daData[0], daData[1])
            .select(["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7", "QA_PIXEL"])
            .map(cloudMaskLS7)
            .filterBounds(my_geometry)
        )

        if mdt == 0:
            return dataset.mean().select(["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"])
        else:
            VWB = (
                dataset.map(L5_NDWI)
                .map(L5_NDVI)
                .map(L5_NDBI)
                .mean()
                .select(["NDVI", "NDWI", "NDBI"])
            )

            return VWB

    except Exception as e:
        print(f"ERROR: {e}")
        print("GETTING LANDSAT DATA ERRORS, CHECK YOUR SETTINGS!")


def GET_DATA_LS8(dayear, ext, my_geometry, mdt=0):
    try:
        daData = get_DateRange(dayear, ext)
        dataset = (
            ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
            .filterDate(daData[0], daData[1])
            .select(["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7", "QA_PIXEL"])
            .map(cloudMaskLS8)
            .filterBounds(my_geometry)
        )

        if mdt == 0:
            return dataset.mean().select(["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"])
        else:
            VWB = (
                dataset.map(L8_NDWI)
                .map(L8_NDVI)
                .map(L8_NDBI)
                .mean()
                .select(["NDVI", "NDWI", "NDBI"])
            )

            return VWB

    except Exception as e:
        print(f"ERROR: {e}")
        print("GETTING LANDSAT DATA ERRORS, CHECK YOUR SETTINGS!")


# ===================================================================================================================


def maskS2clouds(image):
    qa = image.select("QA60")
    cloudBitMask = ee.Number(2).pow(10).int()
    cirrusBitMask = ee.Number(2).pow(11).int()
    # Remove edge pixels that don't occur in all bands
    mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))
    return image.updateMask(mask).divide(10000)

def mask_s2_clouds(image):
  qa = image.select('QA60')
  cloud_bit_mask = 1 << 10
  cirrus_bit_mask = 1 << 11
  mask = (
      qa.bitwiseAnd(cloud_bit_mask)
      .eq(0)
      .And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
  )
  return image.updateMask(mask).divide(10000)

def S2_NDBI(img):
    NIR = img.select("B8")
    SWIR = img.select("B11")
    NDBI = SWIR.subtract(NIR).divide(SWIR.add(NIR)).rename("NDBI")
    return img.addBands(NDBI)


def S2_MNDWI(img):
    G = img.select("B3")
    SWIR = img.select("B11")
    MNDWI = G.subtract(SWIR).divide(G.add(SWIR)).rename("MNDWI")
    return img.addBands(MNDWI)


def S2_NDWI(img):
    G = img.select("B3")
    NIR = img.select("B8")
    NDWI = G.subtract(NIR).divide(G.add(NIR)).rename("NDWI")
    return img.addBands(NDWI)


def S2_NDVI(img):
    R = img.select("B4")
    NIR = img.select("B8")
    NDVI = NIR.subtract(R).divide(NIR.add(R)).rename("NDVI")
    return img.addBands(NDVI)


def topow(image):
    return ee.Image(10.0).pow(image.divide(10.0))


def GET_DATA_ST(dayear, ext, my_geometry, mdt=0):
    try:
        daData = get_DateRange(dayear, ext)
        #         print(daData)
        dataset = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterDate(daData[0], daData[1])
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            .map(mask_s2_clouds)
            .select("B2", "B3", "B4", "B8", "B11")
            .filterBounds(my_geometry)
        )

        if mdt == 0:
            return dataset.median()  # .select(['B2', 'B3', 'B4', "B8", "B11"])
        else:
            SAR = (
                ee.ImageCollection("COPERNICUS/S1_GRD")
                .filterDate(daData[0], daData[1])
                .filterMetadata("instrumentMode", "equals", "IW")
                .filterBounds(my_geometry)
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
                .select("VV")
                .map(topow)
                .mean()
                .rename("SAR")
            )

            annualLights = (
                ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG")
                .filter(ee.Filter.date(daData[0], daData[1]))
                .filterBounds(my_geometry)
                .select("avg_rad")
                .mean()
                .rename("lights")
            )

            VWB = (
                dataset.map(S2_NDWI)
                .map(S2_NDVI)
                .map(S2_NDBI)
                .mean()
                .addBands(SAR)
                .addBands(annualLights)
                .select(["NDVI", "NDWI", "NDBI", "SAR", "lights"])
            )

            return VWB
    except Exception as e:
        print(f"ERROR: {e}")
        print("GETTING SENTINEL DATA ERRORS, CHECK YOUR SETTINGS!")
