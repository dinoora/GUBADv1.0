import os
import json
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
import warnings
import logging
from datetime import datetime
import hashlib
import shutil
import re

warnings.filterwarnings('ignore')


class PatchProcessor:
    def __init__(self, patch_kml_root, constraint_result_root, final_patch_root):
        self.patch_kml_root = patch_kml_root
        self.constraint_result_root = constraint_result_root
        self.final_patch_root = final_patch_root

        os.makedirs(self.final_patch_root, exist_ok=True)
        self.setup_logging()

        # 用于统计面积减少的城市和年份
        self.area_decrease_records = []

    # ----------------------------------------------------------
    # 日志系统
    # ----------------------------------------------------------
    def setup_logging(self):
        log_file = os.path.join(self.final_patch_root, "patch_processing.log")
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    # ----------------------------------------------------------
    # KML 文件识别
    # ----------------------------------------------------------
    def get_kml_files(self):
        """获取所有KML补裁文件"""
        kml_files = {}
        for f in os.listdir(self.patch_kml_root):
            if f.endswith(".kml"):
                city, year, mode = self.parse_city_year_mode(f)
                if city:
                    key = (city, year)
                    if key not in kml_files:
                        kml_files[key] = {"bu": None, "cai": None}
                    kml_files[key][mode] = f
        return kml_files

    def parse_city_year_mode(self, filename):
        """
        解析KML文件名格式：
        Anqing_2000_bu.kml 或 Anqing_2000_cai.kml
        或 cityname_year_mode.kml
        """
        name = os.path.splitext(filename)[0]
        parts = name.split("_")

        if len(parts) < 3:
            return None, None, None

        # 最后两部分是年份和模式
        mode = parts[-1]  # bu 或 cai
        year = parts[-2]

        # 城市名可能是多个下划线连接的部分
        city = "_".join(parts[:-2])

        if not year.isdigit():
            return None, None, None

        return city, int(year), mode

    # ----------------------------------------------------------
    # 查找约束结果文件
    # ----------------------------------------------------------
    def find_all_constraint_files(self):
        """递归查找所有约束结果shp文件"""
        constraint_files = []

        # 遍历根目录
        for root, dirs, files in os.walk(self.constraint_result_root):
            for file in files:
                if file.endswith(".shp") and "_constraint" in file:
                    full_path = os.path.join(root, file)
                    # 解析城市和年份
                    city, year = self.parse_constraint_filename(file)
                    if city and year:
                        constraint_files.append({
                            "path": full_path,
                            "city": city,
                            "year": year,
                            "filename": file
                        })

        return constraint_files

    def parse_constraint_filename(self, filename):
        """解析约束结果文件名格式：city_year_constraint.shp"""
        name = os.path.splitext(filename)[0]
        parts = name.split("_")

        if len(parts) < 3:
            return None, None

        # 最后一部分是"constraint"
        if parts[-1] != "constraint":
            return None, None

        year = parts[-2]
        city = "_".join(parts[:-2])

        if not year.isdigit():
            return None, None

        return city, int(year)

    # ----------------------------------------------------------
    # KML → 多边形
    # ----------------------------------------------------------
    def extract_polygons_from_geometry(self, geom):
        if geom.is_empty:
            return []

        if isinstance(geom, GeometryCollection):
            polys = []
            for g in geom.geoms:
                polys.extend(self.extract_polygons_from_geometry(g))
            return polys

        if isinstance(geom, MultiPolygon):
            return list(geom.geoms)

        if isinstance(geom, Polygon):
            return [geom]

        return []

    def kml_to_gdf(self, path):
        try:
            gdf = gpd.read_file(path)
            if len(gdf) == 0:
                return None

            if gdf.crs is None:
                gdf = gdf.set_crs(epsg=4326)

            polys = []
            for _, row in gdf.iterrows():
                polys.extend(self.extract_polygons_from_geometry(row.geometry))

            if len(polys) == 0:
                return None

            geom = polys[0] if len(polys) == 1 else MultiPolygon(polys)
            out = gpd.GeoDataFrame(geometry=[geom], crs=gdf.crs)
            out["geometry"] = out.buffer(0)
            return out

        except Exception as e:
            self.logger.error(f"读取KML文件失败 {path}: {str(e)}")
            return None

    # ----------------------------------------------------------
    # 清理属性表，只保留Area字段
    # ----------------------------------------------------------
    def cleanup_attributes(self, gdf):
        """清理属性表，只保留Area字段"""
        # 删除除geometry外的所有列
        for col in list(gdf.columns):
            if col != "geometry":
                gdf = gdf.drop(columns=[col])

        # 计算面积并添加Area字段
        if "geometry" in gdf.columns:
            # 确保使用正确的CRS计算面积
            if gdf.crs and gdf.crs.is_projected:
                # 如果已经是投影坐标系，直接计算面积
                gdf["Area"] = gdf["geometry"].area
            else:
                # 如果是地理坐标系（如WGS84），需要转换到投影坐标系
                # 这里使用UTM投影（需要根据实际情况调整）
                try:
                    # 首先估算中心点以确定UTM带
                    centroid = gdf.unary_union.centroid
                    lon, lat = centroid.x, centroid.y

                    # 计算UTM带
                    utm_zone = int((lon + 180) // 6) + 1
                    epsg_code = 32600 + utm_zone if lat >= 0 else 32700 + utm_zone

                    # 转换到UTM投影并计算面积
                    gdf_proj = gdf.to_crs(epsg=epsg_code)
                    gdf["Area"] = gdf_proj["geometry"].area
                except:
                    # 如果转换失败，使用近似计算（只适用于小范围）
                    gdf["Area"] = gdf["geometry"].area * 111319.488 * 111319.488

        return gdf

    # ----------------------------------------------------------
    # 补洞 union
    # ----------------------------------------------------------
    def apply_patch(self, base, patch):
        base_geom = base.unary_union
        patch_geom = patch.unary_union
        merged = base_geom.union(patch_geom)
        return gpd.GeoDataFrame(geometry=[merged], crs=base.crs)

    # ----------------------------------------------------------
    # 裁剪 difference
    # ----------------------------------------------------------
    def apply_clip(self, base, clip):
        base_geom = base.unary_union
        clip_geom = clip.unary_union
        clipped = base_geom.difference(clip_geom)
        return gpd.GeoDataFrame(geometry=[clipped], crs=base.crs)

    # ----------------------------------------------------------
    # 复制并重命名约束结果文件（没有补裁文件时）
    # ----------------------------------------------------------
    def copy_and_rename_constraint(self, constraint_info):
        """复制约束结果文件到目标目录并重命名"""
        src_path = constraint_info["path"]
        city = constraint_info["city"]
        year = constraint_info["year"]

        # 目标目录和路径
        out_dir = os.path.join(self.final_patch_root, city)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{city}_{year}_patched.shp")

        # 读取源文件
        try:
            gdf = gpd.read_file(src_path)

            # 确保几何有效
            gdf["geometry"] = gdf.buffer(0)

            # 清理属性表并计算面积
            gdf = self.cleanup_attributes(gdf)

            # 保存到新位置
            gdf.to_file(out_path, encoding="utf-8")

            # 复制相关文件（.dbf, .shx, .prj等）
            base_name = os.path.splitext(src_path)[0]
            for ext in ['.dbf', '.shx', '.prj', '.cpg', '.xml', '.sbn', '.sbx']:
                src_file = base_name + ext
                if os.path.exists(src_file):
                    dst_file = os.path.join(out_dir, f"{city}_{year}_patched{ext}")
                    shutil.copy2(src_file, dst_file)

            self.logger.info(f"复制并重命名: {city} {year} -> {out_path}")
            self.logger.info(f"最终面积: {gdf['Area'].iloc[0]:.2f} m²")

            return True

        except Exception as e:
            self.logger.error(f"复制文件失败 {src_path}: {str(e)}")
            return False

    # ----------------------------------------------------------
    # 主流程：对一个城市 + 年份处理
    # ----------------------------------------------------------
    def process_city_year(self, constraint_info, kml_files):
        """处理单个城市年份的约束结果"""
        city = constraint_info["city"]
        year = constraint_info["year"]
        constraint_path = constraint_info["path"]

        self.logger.info(f"开始处理: {city} {year}")

        # 检查是否有对应的补裁文件
        key = (city, year)
        has_bu = key in kml_files and kml_files[key]["bu"] is not None
        has_cai = key in kml_files and kml_files[key]["cai"] is not None

        # 如果没有补裁文件，直接复制
        if not has_bu and not has_cai:
            self.logger.info(f"没有补裁文件，直接复制: {city} {year}")
            return self.copy_and_rename_constraint(constraint_info)

        # 读取基线数据
        try:
            base = gpd.read_file(constraint_path)
            base["geometry"] = base.buffer(0)
        except Exception as e:
            self.logger.error(f"读取基线数据失败 {constraint_path}: {str(e)}")
            return False

        # --------------------------------------------------
        # 1) 先补洞
        # --------------------------------------------------
        if has_bu:
            bu_file = kml_files[key]["bu"]
            bu_path = os.path.join(self.patch_kml_root, bu_file)
            bu_gdf = self.kml_to_gdf(bu_path)

            if bu_gdf is not None:
                bu_gdf = bu_gdf.to_crs(base.crs)
                base = self.apply_patch(base, bu_gdf)
                self.logger.info(f"应用补洞: {bu_file}")

        # --------------------------------------------------
        # 2) 再裁剪
        # --------------------------------------------------
        if has_cai:
            cai_file = kml_files[key]["cai"]
            cai_path = os.path.join(self.patch_kml_root, cai_file)
            cai_gdf = self.kml_to_gdf(cai_path)

            if cai_gdf is not None:
                cai_gdf = cai_gdf.to_crs(base.crs)
                base = self.apply_clip(base, cai_gdf)
                self.logger.info(f"应用裁剪: {cai_file}")

        # --------------------------------------------------
        # 清理属性表并计算面积
        # --------------------------------------------------
        result = self.cleanup_attributes(base)

        # 如果有多个要素，合并为一个
        if len(result) > 1:
            merged_geom = result.unary_union
            result = gpd.GeoDataFrame(geometry=[merged_geom], crs=base.crs)
            result = self.cleanup_attributes(result)

        final_area = result["Area"].iloc[0] if "Area" in result.columns else 0
        self.logger.info(f"最终面积: {final_area:.2f} m²")

        # --------------------------------------------------
        # 保存
        # --------------------------------------------------
        out_dir = os.path.join(self.final_patch_root, city)
        os.makedirs(out_dir, exist_ok=True)

        out_path = os.path.join(out_dir, f"{city}_{year}_patched.shp")
        result.to_file(out_path, encoding="utf-8")

        return True

    # ----------------------------------------------------------
    # 检查面积减少的城市和年份
    # ----------------------------------------------------------
    def check_area_decrease(self):
        """检查每个城市6期数据中面积比前一期小的年份"""
        self.logger.info("开始检查面积减少的城市和年份...")

        # 创建专门的日志文件记录面积减少的情况
        decrease_log_file = os.path.join(self.final_patch_root, "area_decrease_cities.log")
        decrease_logger = logging.getLogger("area_decrease")
        decrease_logger.setLevel(logging.INFO)
        decrease_handler = logging.FileHandler(decrease_log_file, encoding='utf-8')
        decrease_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        decrease_logger.addHandler(decrease_handler)
        decrease_logger.propagate = False

        # 标题
        decrease_logger.info("=" * 60)
        decrease_logger.info("面积比前一期减少的城市和年份")
        decrease_logger.info("=" * 60)

        # 获取所有城市目录
        city_dirs = [d for d in os.listdir(self.final_patch_root)
                     if os.path.isdir(os.path.join(self.final_patch_root, d))]

        # 定义需要检查的年份
        target_years = [2000, 2005, 2010, 2015, 2020, 2025]

        total_decrease_cases = 0

        for city in sorted(city_dirs):
            city_path = os.path.join(self.final_patch_root, city)

            # 查找该城市的所有patched文件
            patched_files = []
            for file in os.listdir(city_path):
                if file.endswith("_patched.shp"):
                    # 解析文件名获取年份
                    match = re.search(rf"{city}_(\d{{4}})_patched\.shp", file)
                    if match:
                        year = int(match.group(1))
                        patched_files.append((year, file))

            # 按年份排序
            patched_files.sort(key=lambda x: x[0])

            # 只保留目标年份的文件
            target_files = [(year, file) for year, file in patched_files if year in target_years]

            if len(target_files) < 2:
                self.logger.info(f"城市 {city} 不足2期数据，跳过检查")
                continue

            # 记录城市各年份面积
            city_areas = {}

            # 读取每个文件并获取面积
            for year, filename in target_files:
                file_path = os.path.join(city_path, filename)
                try:
                    gdf = gpd.read_file(file_path)
                    if "Area" in gdf.columns:
                        area = gdf["Area"].sum()
                        city_areas[year] = area
                        self.logger.info(f"城市 {city} {year}年面积: {area:.2f} m²")
                    else:
                        self.logger.warning(f"城市 {city} {year}年文件没有Area字段: {filename}")
                        # 如果没有Area字段，重新计算
                        gdf["geometry"] = gdf.buffer(0)
                        if gdf.crs and gdf.crs.is_projected:
                            area = gdf["geometry"].area.sum()
                        else:
                            # 近似计算
                            area = gdf["geometry"].area.sum() * 111319.488 * 111319.488
                        city_areas[year] = area
                except Exception as e:
                    self.logger.error(f"读取文件失败 {file_path}: {str(e)}")

            # 按年份排序
            sorted_years = sorted(city_areas.keys())

            # 检查面积减少的情况
            city_decrease_cases = []

            for i in range(1, len(sorted_years)):
                prev_year = sorted_years[i - 1]
                curr_year = sorted_years[i]

                prev_area = city_areas[prev_year]
                curr_area = city_areas[curr_year]

                if curr_area < prev_area:
                    decrease_percent = (prev_area - curr_area) / prev_area * 100
                    decrease_info = {
                        "city": city,
                        "year": curr_year,
                        "prev_year": prev_year,
                        "curr_area": curr_area,
                        "prev_area": prev_area,
                        "decrease_percent": decrease_percent
                    }
                    city_decrease_cases.append(decrease_info)

                    # 添加到总记录
                    self.area_decrease_records.append(decrease_info)

                    total_decrease_cases += 1

            # 记录该城市的面积减少情况
            if city_decrease_cases:
                self.logger.info(f"城市 {city} 发现 {len(city_decrease_cases)} 处面积减少")
                decrease_logger.info(f"\n城市: {city}")

                for case in city_decrease_cases:
                    log_msg = f"  {case['year']}年面积 ({case['curr_area']:.2f} m²) 比 {case['prev_year']}年面积 ({case['prev_area']:.2f} m²) 减少 {case['decrease_percent']:.2f}%"
                    self.logger.info(log_msg)
                    decrease_logger.info(log_msg)

                    # 记录shp文件名
                    shp_filename = f"{city}_{case['year']}_patched.shp"
                    decrease_logger.info(f"  对应文件: {shp_filename}")

        # 总结
        if total_decrease_cases > 0:
            summary = f"\n总结: 共发现 {total_decrease_cases} 处面积减少的情况"
            self.logger.info(summary)
            decrease_logger.info("\n" + "=" * 60)
            decrease_logger.info(summary)
            decrease_logger.info(f"详细信息已保存至: {decrease_log_file}")

            # 输出所有面积减少的城市和年份列表
            decrease_logger.info("\n所有面积减少的城市和年份列表:")
            decrease_logger.info("-" * 40)
            for i, record in enumerate(self.area_decrease_records, 1):
                decrease_logger.info(
                    f"{i:2d}. {record['city']} {record['year']}年 (比{record['prev_year']}年减少{record['decrease_percent']:.1f}%)")
        else:
            summary = "未发现面积减少的情况"
            self.logger.info(summary)
            decrease_logger.info("\n" + "=" * 60)
            decrease_logger.info(summary)

        # 移除临时handler避免重复日志
        decrease_logger.removeHandler(decrease_handler)
        decrease_handler.close()

        return total_decrease_cases

    # ----------------------------------------------------------
    # 主处理流程
    # ----------------------------------------------------------
    def process_all(self):
        """主处理函数"""
        self.logger.info("开始处理所有约束结果文件...")

        # 获取所有KML补裁文件
        kml_files = self.get_kml_files()
        self.logger.info(f"找到 {len(kml_files)} 组KML补裁文件")

        # 获取所有约束结果文件
        constraint_files = self.find_all_constraint_files()
        self.logger.info(f"找到 {len(constraint_files)} 个约束结果文件")

        # 处理每个约束结果文件
        processed_count = 0
        for constraint_info in constraint_files:
            success = self.process_city_year(constraint_info, kml_files)
            if success:
                processed_count += 1

        self.logger.info(f"处理完成！成功处理 {processed_count}/{len(constraint_files)} 个文件")

        # 检查面积减少情况
        self.logger.info("=" * 60)
        self.check_area_decrease()

        return processed_count


# --------------------------------------------------------------
# 主入口
# --------------------------------------------------------------
def main():
    patch_kml_root = r"D:\Thepenger\建成区\处理好的城市-ZYP-JXL-LC-DINOO\裁掉文件"
    constraint_result_root = r"D:\Thepenger\建成区\检查\刘畅结果\LC第三次重做\建成区约束后结果"
    final_patch_root = r"D:\Thepenger\建成区\检查\刘畅结果\LC第三次重做\补洞后数据"

    processor = PatchProcessor(patch_kml_root, constraint_result_root, final_patch_root)
    processed_count = processor.process_all()

    print(f"处理完成！共处理 {processed_count} 个文件")
    print(f"结果保存在: {final_patch_root}")

    if processor.area_decrease_records:
        print(f"发现 {len(processor.area_decrease_records)} 处面积减少的情况")
        print(f"详细信息请查看: {os.path.join(final_patch_root, 'area_decrease_cities.log')}")


if __name__ == "__main__":
    main()