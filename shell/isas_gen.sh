#! /bin/bash

dir_bond="/home/PROJECT/GEE/02_boundaries"
dir_python="/home/PROJECT/GEE/31_ISA/L0"
tif_dir="/home/PROJECT/GEE/31_ISA/L0"
tif_dir_l1="/home/PROJECT/GEE/31_ISA/L1"

pcd=$(pwd)

if [[ "$pcd" =~ "/L0"$ ]]; then
    FLT="$dir_bond/*/*"
else
    FLT="${pcd#*/L0/}"
    
    if [[ $FLT == *"/"* ]]; then
        FLT="$dir_bond/$FLT"
    else
        FLT="$dir_bond/$FLT/*"
    fi
fi

# 默认设置为不跳过确认 (false)

args="$FLT $tif_dir"
L1L3_UPDATE=false

while getopts "hypde:um:7" opt; do
    case $opt in
        h)
            echo "用法: $0 [选项]"
            echo "选项:"
            echo "  -y    gee处理并下载文件时"
            echo "  -p    仅处理数据不下载数据 (未设置-y时有效,否则被覆盖)"
            echo "  -d    不处理数据仅下载数据 (未设置-y时有效,否则被覆盖)"
            echo "  -e N  时间扩展(N年,默认为0,前后各N/2年)"
            echo "  -m M  模式:0 - 原始波段; 1 - NWB, 默认值"
            echo "  -l L  15年之前使用Landsat数据，默认LS-5"
            echo "  -h    显示帮助信息"
            exit 0
        ;;
        p) args="$args -p" ;;
        d) args="$args -d" ;;
        y) args="$args -y" ;;
        e) args="$args -e $OPTARG" ;;
        m) args="$args -m $OPTARG" ;;
        l) args="$args -l $OPTARG" ;;
        \?) echo "无效选项: -$OPTARG" >&2; exit 1 ;;
    esac
done

# ---------------------------------------------------------
# 3. 主程序执行
# ---------------------------------------------------------

# echo "准备开始任务..."
echo -e "\n-- 不透水面提取 ${FLT} ..."

python3 $dir_python/ee_get_ISAs.py $args

echo " ******************  不透水面提取处理完成! ******************  "


(cd $tif_dir_l1${pcd##*L0} && bash $tif_dir_l1/isas_filter.sh)



