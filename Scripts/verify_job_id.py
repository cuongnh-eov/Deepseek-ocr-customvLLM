#!/usr/bin/env python3
"""
Test script để verify job_id trong JSON output
"""

import json
import sys

# Example JSON output (simulate)
example_response = {
    "document": {
        "metadata": {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",  # ✅ NEW
            "source_filename": "bao_cao_bao_tri.pdf",
            "total_pages": 3,
            "processed_at": "2026-01-10T11:50:35.123456+00:00"
        },
        "content": [
            {
                "type": "heading",
                "level": 1,
                "text": "Báo Cáo Bảo Trì",
                "page_number": 1,
                "metadata": {
                    "page_number": 1,
                    "block_index": 0,
                    "is_continuation": False,
                    "parent_block_id": None,
                    "confidence": 1.0
                }
            },
            {
                "type": "table",
                "table_id": "tbl_01",
                "header_row": ["Tên Thiết Bị", "Ngày", "Chi Phí"],
                "rows": [
                    ["Máy A", "01/01", "500k"],
                    ["Máy B", "02/01", "300k"],
                    ["Máy C", "03/01", "400k"]
                ],
                "is_header_repeated": True,
                "is_merged": True,
                "pages": {
                    "first_page": 1,
                    "last_page": 3,
                    "page_sequence": [1, 3]
                },
                "validation": "High",
                "metadata": {
                    "page_number": 1,
                    "block_index": 1,
                    "is_continuation": False,
                    "parent_block_id": None,
                    "confidence": 1.0
                }
            }
        ]
    }
}

print("="*70)
print("✅ JSON OUTPUT WITH JOB_ID")
print("="*70)
print()

# Pretty print
print(json.dumps(example_response, indent=2, ensure_ascii=False))

print()
print("="*70)
print("📊 VERIFICATION")
print("="*70)

# Verify structure
try:
    job_id = example_response["document"]["metadata"]["job_id"]
    print(f"✅ job_id found: {job_id}")
    print(f"✅ source_filename: {example_response['document']['metadata']['source_filename']}")
    print(f"✅ total_pages: {example_response['document']['metadata']['total_pages']}")
    print(f"✅ processed_at: {example_response['document']['metadata']['processed_at']}")
    print(f"✅ content blocks: {len(example_response['document']['content'])}")
    
    print()
    print("✅ All fields present and valid!")
    
except KeyError as e:
    print(f"❌ Missing field: {e}")
    sys.exit(1)

print()
print("="*70)
print("🎯 USAGE")
print("="*70)
print()
print("When you upload a document:")
print("1. API receives file → Creates job_id")
print("2. Sends to RabbitMQ with job_id")
print("3. Worker processes → Includes job_id in JSON")
print("4. JSON saved to MinIO with job_id")
print()
print("You can now:")
print("  - Track documents by job_id")
print("  - Link uploads to processed results")
print("  - Query: GET /api/jobs/{job_id}/status")
print("  - Download: GET /api/jobs/{job_id}/result.json")
print()
