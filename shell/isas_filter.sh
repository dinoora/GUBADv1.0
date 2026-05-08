#! /bin/bash

dir_bond="/home/PROJECT/GEE/02_boundaries"
tif_input="/home/PROJECT/GEE/31_ISA/L0"
tif_output="/home/PROJECT/GEE/31_ISA/L1"
dir_bin=/home/PROJECT/GEE/01_code/cpp/build/bin

years=(2000 2005 2010 2015 2020 2025)

pcd=$(pwd)

if [[ "$pcd" =~ "/L1"$ ]]; then
    FLT="$dir_bond/*/*"
else
    FLT="${pcd#*/L1/}"
    
    if [[ $FLT == *"/"* ]]; then
        FLT="$dir_bond/$FLT"
    else
        FLT="$dir_bond/$FLT/*"
    fi
fi

echo -e "\n-- 不透水面过滤 ${FLT} ... "

for dnat in `ls -d ${FLT}/`; do
    cnat=${dnat#*02_boundaries/}
    echo "    - $cnat"
        
    for dcty in `ls ${dnat}*.shp`; do
        city=${dcty%.*}
        city=${city##*/}
        
        if [ ! -e $tif_output/$cnat$city ]; then
            mkdir -p $tif_output/$cnat$city
        fi
        
        label=0
        for yr in ${years[@]}; do
            
            if [ ! -e $tif_output/$cnat$city/$city$yr.tif ]; then
                cp $tif_input/$cnat$city/$city$yr.tif $tif_output/$cnat$city/$city$yr.tif
                let label=1
            fi
            
        done
        
        if [ $label == 0 ]; then
            continue
        fi
        
        $dir_bin/IS_filter \
        $tif_output/$cnat$city/${city}2000.tif \
        $tif_output/$cnat$city/${city}2005.tif \
        $tif_output/$cnat$city/${city}2010.tif \
        $tif_output/$cnat$city/${city}2015.tif \
        $tif_output/$cnat$city/${city}2020.tif \
        $tif_output/$cnat$city/${city}2025.tif
        
    done
    
done



echo " ******************  不透水面过滤处理完成! ******************  "
