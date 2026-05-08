import re
from pathlib import Path
from collections import defaultdict

import geopandas as gpd
from shapely.ops import unary_union
from shapely.geometry import GeometryCollection

# =========================
# 0) 路径配置
# =========================
BUILTUP_ROOT = Path(r"D:\Thepenger\建成区\处理好的城市-ZYP-JXL-LC-DINOO\裁剪后结果\1")
WATER_ROOT   = Path(r"D:\Thepenger\建成区\处理好的城市-ZYP-JXL-LC-DINOO\水体")

OUT_ROOT     = Path(r"D:\Thepenger\建成区\处理好的城市-ZYP-JXL-LC-DINOO\裁剪后结果\1\剔除水体结果")
OUT_ROOT.mkdir(parents=True, exist_ok=True)

AREA_FIELD = "Area"  # m²，两位小数

# 如果发现个别城市匹配错省，在这里手动指定（可留空）
# 例：CITY_TO_PROVINCE = {"Hefei": "安徽省"}
CITY_TO_PROVINCE = {}


# =========================
# 1) 工具函数
# =========================
def safe_make_valid_gdf(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    gdf = gdf[gdf.geometry.notna()]
    if gdf.empty:
        return gdf

    try:
        from shapely.make_valid import make_valid  # shapely>=2
        gdf["geometry"] = gdf.geometry.apply(lambda g: make_valid(g) if g is not None else None)
    except Exception:
        # 兜底
        gdf["geometry"] = gdf.geometry.buffer(0)

    gdf = gdf[gdf.geometry.notna()]
    gdf = gdf[~gdf.geometry.is_empty]
    return gdf


def clean_geom(geom):
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, GeometryCollection):
        parts = [g for g in geom.geoms if g is not None and not g.is_empty]
        if not parts:
            return None
        return unary_union(parts)
    return geom


def dissolve_union_geom(gdf: gpd.GeoDataFrame):
    if gdf.empty:
        return None
    u = unary_union(list(gdf.geometry))
    if u is None or u.is_empty:
        return None
    return u


def parse_city_year(shp_path: Path):
    """
    从文件名解析城市名和年份：
    Akesu_2000_patched_clip.shp -> ("Akesu", "2000")
    """
    stem = shp_path.stem
    m = re.search(r"_(\d{4})", stem)
    if m:
        year = m.group(1)
        city = stem[:m.start()]
        return city, year
    # 兜底：没有年份就返回 None
    return stem.split("_")[0], None


def recompute_area_m2(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    你的建成区 CRS 是 UTM（米），geometry.area -> m²
    """
    gdf = gdf.copy()
    gdf[AREA_FIELD] = gdf.geometry.area.round(2)
    return gdf


# =========================
# 2) 读取并缓存“省级水体面” unions（统一存 WGS84）
# =========================
def load_province_water_unions():
    """
    返回：
      prov_waters = {
        "安徽省": {"geom_wgs84": <shapely geom>, "bbox": (minx,miny,maxx,maxy)}
        ...
      }
    只读取 "*水系面数据*.shp"
    """
    prov_waters = {}

    # 每个省一个子文件夹
    for prov_dir in WATER_ROOT.iterdir():
        if not prov_dir.is_dir():
            continue

        prov_name = prov_dir.name

        # 找“水系面数据”
        candidates = list(prov_dir.glob("*水系面数据*.shp"))
        if not candidates:
            # 也许命名略不同，再宽松一点
            candidates = list(prov_dir.glob("*.shp"))

        # 只保留包含 “面” 或 “水系面” 的
        candidates = [p for p in candidates if ("面" in p.name)]

        if not candidates:
            print(f"[WARN] 省 {prov_name} 未找到水系面 shp，跳过")
            continue

        # 默认取第一个最匹配的
        water_shp = candidates[0]

        try:
            w = gpd.read_file(str(water_shp))
            if w.empty:
                print(f"[WARN] {prov_name} 水体为空：{water_shp.name}，跳过")
                continue
            if w.crs is None:
                print(f"[WARN] {prov_name} 水体无 CRS：{water_shp}，跳过")
                continue

            w = safe_make_valid_gdf(w)
            if w.empty:
                print(f"[WARN] {prov_name} 水体修复后为空，跳过")
                continue

            # 存为 WGS84，便于匹配省
            w84 = w.to_crs("EPSG:4326")
            geom = dissolve_union_geom(w84)
            if geom is None or geom.is_empty:
                print(f"[WARN] {prov_name} dissolve 后为空，跳过")
                continue

            prov_waters[prov_name] = {
                "geom_wgs84": geom,
                "bbox": geom.bounds,  # (minx,miny,maxx,maxy)
                "src_shp": str(water_shp),
            }
            print(f"[OK] 读取省水体：{prov_name} <- {water_shp.name}")

        except Exception as e:
            print(f"[ERROR] 读取省水体失败：{prov_name} -> {water_shp} -> {e}")

    if not prov_waters:
        raise RuntimeError("未成功读取任何省水体数据，请检查 WATER_ROOT 路径与文件命名。")

    return prov_waters


def point_in_bbox(pt, bbox):
    minx, miny, maxx, maxy = bbox
    return (minx <= pt.x <= maxx) and (miny <= pt.y <= maxy)


def match_province_for_city(city: str, city_centroid_wgs84, prov_waters):
    """
    省匹配策略：
    1) 若 CITY_TO_PROVINCE 手工指定，直接用
    2) 否则：优先选择 centroid 落在省水体 bbox 内的省（可能多个取最近距离）
    3) 否则：取 centroid 到各省水体 geom 的最近距离最小者
    """
    if city in CITY_TO_PROVINCE:
        return CITY_TO_PROVINCE[city]

    # bbox 过滤
    bbox_hits = []
    for prov, info in prov_waters.items():
        if point_in_bbox(city_centroid_wgs84, info["bbox"]):
            bbox_hits.append(prov)

    if bbox_hits:
        # 在 bbox_hits 中选最近的水体
        best_prov = None
        best_dist = None
        for prov in bbox_hits:
            d = city_centroid_wgs84.distance(prov_waters[prov]["geom_wgs84"])
            if best_dist is None or d < best_dist:
                best_dist = d
                best_prov = prov
        return best_prov

    # 全局最近
    best_prov = None
    best_dist = None
    for prov, info in prov_waters.items():
        d = city_centroid_wgs84.distance(info["geom_wgs84"])
        if best_dist is None or d < best_dist:
            best_dist = d
            best_prov = prov
    return best_prov


# =========================
# 3) 主流程：遍历建成区，剔除水体，重算 Area，输出
# =========================
def main():
    prov_waters = load_province_water_unions()

    shp_list = list(BUILTUP_ROOT.rglob("*.shp"))
    if not shp_list:
        raise RuntimeError(f"未找到建成区 shp：{BUILTUP_ROOT}")

    print(f"\n发现建成区 shp 数量：{len(shp_list)}\n")

    stats = defaultdict(int)

    for shp_path in shp_list:
        city, year = parse_city_year(shp_path)
        if year is None:
            # 你要求输出 城市_年份.shp，这种没年份的我直接跳过
            print(f"[SKIP] 无法解析年份：{shp_path}")
            stats["skip_no_year"] += 1
            continue

        try:
            gdf = gpd.read_file(str(shp_path))
            if gdf.empty:
                stats["empty_input"] += 1
                continue
            if gdf.crs is None:
                print(f"[SKIP] 无 CRS（无法正确剔水/算面积）：{shp_path}")
                stats["skip_no_crs"] += 1
                continue

            gdf = safe_make_valid_gdf(gdf)
            if gdf.empty:
                stats["empty_after_valid"] += 1
                continue

            # 用城市几何 union 的 centroid 做省匹配（WGS84）
            gdf84 = gdf.to_crs("EPSG:4326")
            city_union_84 = dissolve_union_geom(gdf84)
            if city_union_84 is None or city_union_84.is_empty:
                stats["empty_city_union"] += 1
                continue
            centroid84 = city_union_84.centroid

            prov = match_province_for_city(city, centroid84, prov_waters)
            if prov is None:
                print(f"[SKIP] 未能匹配省：{city} {year} -> {shp_path}")
                stats["skip_no_province"] += 1
                continue

            water_geom_84 = prov_waters[prov]["geom_wgs84"]
            # 投影水体到建成区 CRS（UTM），再做 difference
            water_geom_in_utm = gpd.GeoSeries([water_geom_84], crs="EPSG:4326").to_crs(gdf.crs).iloc[0]

            # 差集剔水
            out = gdf.copy()
            out["geometry"] = out.geometry.apply(lambda geom: clean_geom(geom.difference(water_geom_in_utm)) if geom is not None else None)
            out = out[out.geometry.notna()]
            out = out[~out.geometry.is_empty]

            if out.empty:
                print(f"[EMPTY] {city}_{year} 剔水后为空（省={prov}），不输出")
                stats["empty_output"] += 1
                continue

            # 重算面积（m²，两位小数）
            out = recompute_area_m2(out)

            # 输出：每个城市一个文件夹；文件名 城市_年份.shp
            city_dir = OUT_ROOT / city
            city_dir.mkdir(parents=True, exist_ok=True)
            out_path = city_dir / f"{city}_{year}.shp"

            out.to_file(str(out_path), driver="ESRI Shapefile", encoding="utf-8")
            print(f"[OK] {city}_{year} | 省匹配={prov} | 输出={out_path}")
            stats["ok"] += 1

        except Exception as e:
            print(f"[ERROR] 处理失败：{shp_path} -> {e}")
            stats["error"] += 1

    print("\n======================")
    for k in sorted(stats.keys()):
        print(f"{k}: {stats[k]}")
    print(f"输出目录: {OUT_ROOT}")
    print("======================\n")


if __name__ == "__main__":
    main()
