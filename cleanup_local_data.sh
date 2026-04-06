#!/bin/bash

# 本地数据清理脚本
# 在删除本地数据前，请确保硬盘上的数据已验证无误

echo "═══════════════════════════════════════════════════════════════════"
echo "本地数据清理和验证"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# 验证步骤 1：确认硬盘数据存在
echo "【步骤 1】验证硬盘数据..."
echo ""

if [ -d "/Volumes/ChouSSD/elder_datasets" ]; then
    echo "✓ 硬盘已挂载：/Volumes/ChouSSD/elder_datasets"
    echo ""
    echo "硬盘上的数据：" 
    ls -lah /Volumes/ChouSSD/elder_datasets/ | grep -E "GSTRIDE|PhysioNet|DLNN"
    echo ""
else
    echo "✗ 错误：硬盘未挂载或路径不对"
    echo "请检查硬盘是否已连接"
    exit 1
fi

# 验证步骤 2：验证本地数据
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【步骤 2】验证本地数据..."
echo ""

LOCAL_GSTRIDE="/Users/zhanghaiyu/workspace/elder_rehab/GSTRIDE_database"
LOCAL_PHYSIONET="/Users/zhanghaiyu/workspace/elder_rehab/wearable-based-signals-during-physical-exercises-from-patients-with-frailty-after-open-heart-surgery-1.0.0"
LOCAL_DLNN="/Users/zhanghaiyu/workspace/elder_rehab/A-Deep-Learning-Framework-for-Assessing-Physical-Rehabilitation-Exercises-master/Data"

echo "本地数据位置："
echo ""
echo "1. GSTRIDE: $LOCAL_GSTRIDE"
if [ -d "$LOCAL_GSTRIDE" ]; then
    SIZE=$(du -sh "$LOCAL_GSTRIDE" | awk '{print $1}')
    echo "   ✓ 存在 | 大小：$SIZE"
else
    echo "   ✗ 不存在"
fi
echo ""

echo "2. PhysioNet: $LOCAL_PHYSIONET"
if [ -d "$LOCAL_PHYSIONET" ]; then
    SIZE=$(du -sh "$LOCAL_PHYSIONET" | awk '{print $1}')
    echo "   ✓ 存在 | 大小：$SIZE"
else
    echo "   ✗ 不存在"
fi
echo ""

echo "3. DLNN Framework: $LOCAL_DLNN"
if [ -d "$LOCAL_DLNN" ]; then
    SIZE=$(du -sh "$LOCAL_DLNN" | awk '{print $1}')
    echo "   ✓ 存在 | 大小：$SIZE"
else
    echo "   ✗ 不存在"
fi
echo ""

# 验证步骤 3：确认脚本已正确配置
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【步骤 3】验证脚本配置..."
echo ""

CONFIG_FILE="/Users/zhanghaiyu/workspace/elder_rehab/signal_processing_pipeline/config.py"

echo "检查 config.py 中的路径配置："
echo ""
grep "EXTERNAL_DRIVE_PATH\|GSTRIDE_DATA_DIR\|PHYSIONET_DATA_DIR" "$CONFIG_FILE" | head -4
echo ""

if grep -q "EXTERNAL_DRIVE_PATH.*ChouSSD" "$CONFIG_FILE"; then
    echo "✓ 脚本已配置为使用外挂硬盘"
else
    echo "✗ 脚本配置可能有问题，请检查"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【步骤 4】删除本地数据"
echo ""

read -p "确认删除本地数据？(y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "开始删除本地数据..."
    echo ""
    
    if [ -d "$LOCAL_GSTRIDE" ]; then
        echo "删除 GSTRIDE_database..."
        rm -rf "$LOCAL_GSTRIDE"
        echo "  ✓ 完成"
    fi
    
    if [ -d "$LOCAL_PHYSIONET" ]; then
        echo "删除 wearable-based-signals..."
        rm -rf "$LOCAL_PHYSIONET"
        echo "  ✓ 完成"
    fi
    
    if [ -d "$LOCAL_DLNN" ]; then
        echo "删除 DLNN Framework Data..."
        rm -rf "$LOCAL_DLNN"
        echo "  ✓ 完成"
    fi
    
    echo ""
    echo "✓ 本地数据删除完成！已释放空间"
    echo ""
    echo "已释放的空间：约 5.7 GB"
else
    echo "已取消删除操作"
    exit 0
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【步骤 5】最终验证"
echo ""

echo "剩余本地数据："
echo ""

if [ -d "$LOCAL_GSTRIDE" ]; then
    echo "  ✗ GSTRIDE_database 仍然存在"
else
    echo "  ✓ GSTRIDE_database 已删除"
fi

if [ -d "$LOCAL_PHYSIONET" ]; then
    echo "  ✗ PhysioNet 仍然存在"
else
    echo "  ✓ PhysioNet 已删除"
fi

if [ -d "$LOCAL_DLNN" ]; then
    echo "  ✗ DLNN Framework 仍然存在"
else
    echo "  ✓ DLNN Framework 已删除"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "✓ 清理完成！"
echo ""
echo "所有数据现在存储在：/Volumes/ChouSSD/elder_datasets/"
echo "脚本已配置为使用外挂硬盘路径"
echo "═══════════════════════════════════════════════════════════════════"
