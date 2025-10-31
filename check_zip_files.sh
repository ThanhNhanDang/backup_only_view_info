#!/bin/bash
# tail -f /var/log/zip_cleanup.log
# Cấu hình
DIR_PATH="."  # Thay đổi đường dẫn thực tế
PREFIX="0313_1"
KEEP_COUNT=7
LOG_FILE="/var/log/zip_cleanup.log"

# Ghi log
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "========== BẮT ĐẦU CLEANUP =========="

# Đếm số file hiện tại
CURRENT_COUNT=$(ls -1 ${DIR_PATH}/${PREFIX}*.zip 2>/dev/null | wc -l)
log "Số file hiện tại: $CURRENT_COUNT"

if [ $CURRENT_COUNT -le $KEEP_COUNT ]; then
    log "OK: Giữ nguyên $CURRENT_COUNT file"
    exit 0
fi

# Tính số file cần xóa
DELETE_COUNT=$((CURRENT_COUNT - KEEP_COUNT))
log "Cần xóa $DELETE_COUNT file cũ nhất"

# Xóa các file cũ nhất
ls -1t ${DIR_PATH}/${PREFIX}*.zip 2>/dev/null | tail -n $DELETE_COUNT | while read file; do
    log "Đang xóa: $file"
    rm -f "$file" 2>&1 | tee -a "$LOG_FILE"
    if [ $? -eq 0 ]; then
        log "✓ Đã xóa thành công: $file"
    else
        log "✗ Lỗi khi xóa: $file"
    fi
done

# Kiểm tra lại
NEW_COUNT=$(ls -1 ${DIR_PATH}/${PREFIX}*.zip 2>/dev/null | wc -l)
log "Hoàn tất: Còn lại $NEW_COUNT file"
log "========== KẾT THÚC CLEANUP =========="