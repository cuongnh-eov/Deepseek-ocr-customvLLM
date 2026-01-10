#!/usr/bin/env python3
"""
Test script kiểm tra format timestamp
Hiện tại là 2026-01-10 16:07
"""

from datetime import datetime, timezone
import time

print("=" * 70)
print("TEST FORMAT TIMESTAMP")
print("=" * 70)

# Cách 1: datetime.now() - không có timezone
dt_now = datetime.now()
print(f"\n1. datetime.now():")
print(f"   {dt_now}")
print(f"   {dt_now.isoformat()}")

# Cách 2: datetime.now(timezone.utc) - có timezone UTC
dt_utc = datetime.now(timezone.utc)
print(f"\n2. datetime.now(timezone.utc):")
print(f"   {dt_utc}")
print(f"   {dt_utc.isoformat()}")

# Cách 3: strftime với timezone
dt_with_tz = datetime.now(timezone.utc)
print(f"\n3. strftime format:")
print(f"   {dt_with_tz.strftime('%Y-%m-%dT%H:%M:%S.%f%z')}")

# Cách 4: isoformat() với sep
print(f"\n4. isoformat() khác:")
print(f"   {dt_utc.isoformat(timespec='microseconds')}")

# Cách 5: Format giống hệt JSON bạn
print(f"\n5. Format giống hệt bạn (MATCH):")
iso_str = dt_utc.isoformat()
print(f"   {iso_str}")

print("\n" + "=" * 70)
print("SO SÁNH VỚI FORMAT CỦA BẠN")
print("=" * 70)
your_format = "2026-01-10T06:36:20.253194+00:00"
print(f"\nBạn có: {your_format}")
print(f"Test:   {iso_str}")

if iso_str.split('+')[0].split('T')[0] == your_format.split('+')[0].split('T')[0]:
    print("✅ Format ngày khớp!")
else:
    print("❌ Format ngày không khớp!")

print("\n" + "=" * 70)
print("KẾT LUẬN: Dùng hàm nào?")
print("=" * 70)
print(f"""
✅ DÙNG: datetime.now(timezone.utc).isoformat()
   → Trả về: {dt_utc.isoformat()}

Import cần:
    from datetime import datetime, timezone

Code ở app/services/ocr_service.py hoặc schemas.py:
    processed_at = datetime.now(timezone.utc).isoformat()
""")
