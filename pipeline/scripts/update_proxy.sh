#!/bin/bash
# 代理更新脚本 — 一键下载最新订阅 + 替换配置 + 重启
# 用法: bash update_proxy.sh

set -e

SUB_URL="https://s.youyun666.site/link/C4AqEXlegnqLE4No?clash=1"
# 配置文件路径
CONFIG_PATH="/opt/clash/config.yaml"
BACKUP_DIR="/opt/clash/backups"
TMP_FILE="/tmp/youyun_sub.yaml"

echo "🔽 下载最新订阅..."
# 先直连，失败则走本地代理
curl -sL --max-time 30 -o "$TMP_FILE" "$SUB_URL" 2>/dev/null || \
curl -sL --max-time 30 -x http://127.0.0.1:7890 -o "$TMP_FILE" "$SUB_URL" 2>/dev/null

if [ ! -s "$TMP_FILE" ]; then
    echo "❌ 下载失败或文件为空"
    exit 1
fi

NODE_COUNT=$(grep -c '"name"' "$TMP_FILE" 2>/dev/null || echo 0)
echo "  节点数: $NODE_COUNT"

if [ "$NODE_COUNT" -lt 10 ]; then
    echo "❌ 节点数太少($NODE_COUNT)，可能订阅异常，放弃更新"
    exit 1
fi

# 备份旧配置
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/config.$(date +%Y%m%d_%H%M%S).yaml"
cp "$CONFIG_PATH" "$BACKUP_FILE"
echo "💾 旧配置已备份: $BACKUP_FILE"

# 替换配置
cp "$TMP_FILE" "$CONFIG_PATH"
echo "✅ 配置已替换"

# 重启 clash
systemctl restart clash
sleep 3

# 验证
HTTP_CODE=$(curl -x http://127.0.0.1:7890 -o /dev/null -w "%{http_code}" -s --max-time 10 https://www.google.com/generate_204)
if [ "$HTTP_CODE" = "204" ]; then
    LATENCY=$(curl -x http://127.0.0.1:7890 -o /dev/null -w "%{time_total}" -s --max-time 10 https://www.google.com/generate_204)
    echo "✅ 代理正常 延迟:${LATENCY}s"

    # 显示节点概况
    echo ""
    echo "📊 节点分布:"
    echo "  🇭🇰 香港: $(grep -c '"hk"' "$TMP_FILE")"
    echo "  🇯🇵 日本: $(grep -c '"jp"' "$TMP_FILE")"
    echo "  🇹🇼 台湾: $(grep -c '"tw"' "$TMP_FILE")"
    echo "  🇸🇬 新加坡: $(grep -c '"sg"' "$TMP_FILE")"

    # 清理10天前的旧备份
    find "$BACKUP_DIR" -name "config.*.yaml" -mtime +10 -delete 2>/dev/null
else
    echo "⚠️ 代理检测异常 (http_code=$HTTP_CODE)，尝试回滚..."
    cp "$BACKUP_FILE" "$CONFIG_PATH"
    systemctl restart clash
    echo "🔄 已回滚到旧配置"
    exit 1
fi
