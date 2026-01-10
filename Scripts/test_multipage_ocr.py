"""
Test script để verify MultiPageOCRProcessor
"""

import sys
import json
sys.path.insert(0, '/home/cuongnh/cuong/Deepseek-ocr-customvLLM')

from app.utils.table_continuity_detector import TableContinuityDetector
from app.utils.postprocess_multipage import MultiPageOCRProcessor


def test_header_repetition_detection():
    """Test phát hiện header lặp lại"""
    print("\n" + "="*60)
    print("TEST 1: Header Repetition Detection")
    print("="*60)
    
    detector = TableContinuityDetector()
    
    # Test case 1: Header không lặp
    rows1 = [
        ["Tên Thiết Bị", "Ngày", "Chi Phí"],
        ["Máy A", "01/01", "500k"],
        ["Máy B", "02/01", "300k"]
    ]
    header_idx, is_repeated = detector.detect_header_repetition(rows1)
    print(f"✓ Test 1.1 (Header không lặp): is_repeated={is_repeated} (Expected: False)")
    assert not is_repeated, "FAIL: Header không lặp but detected as repeated"
    
    # Test case 2: Header lặp (dòng 1 = dòng 2)
    rows2 = [
        ["Tên Thiết Bị", "Ngày", "Chi Phí"],
        ["Tên Thiết Bị", "Ngày", "Chi Phí"],
        ["Máy A", "01/01", "500k"]
    ]
    header_idx, is_repeated = detector.detect_header_repetition(rows2)
    print(f"✓ Test 1.2 (Header lặp exact): is_repeated={is_repeated} (Expected: True)")
    assert is_repeated, "FAIL: Header lặp but not detected"
    
    print("\n✅ TEST 1 PASSED\n")


def test_table_continuation():
    """Test phát hiện tiếp tục bảng"""
    print("="*60)
    print("TEST 2: Table Continuation Detection")
    print("="*60)
    
    detector = TableContinuityDetector()
    
    # Trang 1
    header1 = ["Tên Thiết Bị", "Ngày", "Chi Phí"]
    sig1 = detector.extract_header_signature(header1)
    print(f"✓ Page 1 header signature: {sig1}")
    
    # Trang 2 - Header giống
    header2 = ["Tên Thiết Bị", "Ngày", "Chi Phí"]
    is_cont = detector.is_table_continuation(header2, sig1, "tbl_01")
    print(f"✓ Test 2.1 (Header giống): is_continuation={is_cont} (Expected: True)")
    assert is_cont, "FAIL: Same header not detected as continuation"
    
    # Trang 3 - Header khác
    header3 = ["Người", "Ngày", "Ghi Chú"]
    is_cont = detector.is_table_continuation(header3, sig1, "tbl_01")
    print(f"✓ Test 2.2 (Header khác): is_continuation={is_cont} (Expected: False)")
    assert not is_cont, "FAIL: Different header detected as continuation"
    
    # Trang 4 - Header có "Total" (footer)
    header4 = ["Tổng Chi Phí", "Ngày", "Chi Phí"]
    is_cont = detector.is_table_continuation(header4, sig1, "tbl_01")
    print(f"✓ Test 2.3 (Footer detection): is_continuation={is_cont} (Expected: False)")
    assert not is_cont, "FAIL: Footer detected as continuation"
    
    print("\n✅ TEST 2 PASSED\n")


def test_multipage_processor():
    """Test MultiPageOCRProcessor"""
    print("="*60)
    print("TEST 3: MultiPageOCRProcessor - Table Merge")
    print("="*60)
    
    processor = MultiPageOCRProcessor()
    
    # Simulate 3-page document
    pages_data = [
        {
            "page_number": 1,
            "blocks": [
                {
                    "type": "heading",
                    "level": 1,
                    "text": "Báo Cáo Bảo Trì",
                    "metadata": {"page_number": 1, "block_index": 0}
                },
                {
                    "type": "paragraph",
                    "text": "Báo cáo này liệt kê các thiết bị được bảo trì",
                    "metadata": {"page_number": 1, "block_index": 1}
                },
                {
                    "type": "table",
                    "table_id": "tbl_01",
                    "header_row": ["Tên", "Ngày", "Chi Phí"],
                    "rows": [
                        ["Máy A", "01/01", "500k"],
                        ["Máy B", "02/01", "300k"]
                    ],
                    "is_header_repeated": False,
                    "is_merged": False,
                    "page_number": 1,
                    "validation": "High",
                    "metadata": {"page_number": 1, "block_index": 2}
                }
            ]
        },
        {
            "page_number": 2,
            "blocks": [
                {
                    "type": "table",
                    "table_id": "tbl_01",
                    "header_row": ["Tên", "Ngày", "Chi Phí"],
                    "rows": [
                        # Header lặp đã bị trim bởi process_ocr_to_blocks
                        ["Máy C", "03/01", "400k"],
                        ["Máy D", "04/01", "600k"]
                    ],
                    "is_header_repeated": True,
                    "is_merged": False,
                    "page_number": 2,
                    "validation": "High",
                    "metadata": {"page_number": 2, "block_index": 0}
                }
            ]
        },
        {
            "page_number": 3,
            "blocks": [
                {
                    "type": "table",
                    "table_id": "tbl_01",
                    "header_row": ["Tên", "Ngày", "Chi Phí"],
                    "rows": [
                        # Header lặp đã bị trim bởi process_ocr_to_blocks
                        ["Máy E", "05/01", "800k"]
                    ],
                    "is_header_repeated": True,
                    "is_merged": False,
                    "page_number": 3,
                    "validation": "High",
                    "metadata": {"page_number": 3, "block_index": 0}
                },
                {
                    "type": "paragraph",
                    "text": "Tổng Chi Phí: 3,300,000",
                    "metadata": {"page_number": 3, "block_index": 1}
                }
            ]
        }
    ]
    
    # Process
    merged = processor.process_pages(pages_data)
    blocks = merged["document"]["content"]
    
    print(f"✓ Total blocks after merge: {len(blocks)} (Expected: 4)")
    assert len(blocks) == 4, f"FAIL: Expected 4 blocks, got {len(blocks)}"
    
    # Check merged table
    table_block = next((b for b in blocks if b["type"] == "table"), None)
    assert table_block is not None, "FAIL: Table block not found"
    
    print(f"✓ Table is_merged: {table_block.get('is_merged')} (Expected: True)")
    assert table_block.get("is_merged"), "FAIL: Table not marked as merged"
    
    print(f"✓ Table rows count: {len(table_block['rows'])} (Expected: 5)")
    assert len(table_block["rows"]) == 5, f"FAIL: Expected 5 rows, got {len(table_block['rows'])}"
    
    print(f"✓ Table page range: {table_block.get('pages')} (Expected: pages 1-3)")
    assert table_block.get("pages")["first_page"] == 1, "FAIL: First page should be 1"
    assert table_block.get("pages")["last_page"] == 3, "FAIL: Last page should be 3"
    
    print(f"✓ Table header_row: {table_block.get('header_row')}")
    assert table_block.get("header_row") == ["Tên", "Ngày", "Chi Phí"], "FAIL: Header row incorrect"
    
    # Save result
    result_file = "/tmp/merged_document.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"\n✓ Merged document saved to: {result_file}")
    
    print("\n✅ TEST 3 PASSED\n")


def test_section_extraction():
    """Test extract_by_section"""
    print("="*60)
    print("TEST 4: Section Extraction")
    print("="*60)
    
    processor = MultiPageOCRProcessor()
    
    blocks = [
        {"type": "heading", "text": "Phần 1", "page_number": 1},
        {"type": "paragraph", "text": "Content 1", "page_number": 1},
        {"type": "paragraph", "text": "Content 2", "page_number": 1},
        {"type": "heading", "text": "Phần 2", "page_number": 2},
        {"type": "paragraph", "text": "Content 3", "page_number": 2},
        {"type": "table", "rows": [], "page_number": 2},
    ]
    
    sections = processor.extract_by_section(blocks)
    
    print(f"✓ Number of sections: {len(sections)} (Expected: 2)")
    assert len(sections) == 2, f"FAIL: Expected 2 sections, got {len(sections)}"
    
    print(f"✓ Section 'Phần 1' has {len(sections['Phần 1'])} blocks")
    print(f"✓ Section 'Phần 2' has {len(sections['Phần 2'])} blocks")
    
    print("\n✅ TEST 4 PASSED\n")


if __name__ == "__main__":
    try:
        test_header_repetition_detection()
        test_table_continuation()
        test_multipage_processor()
        test_section_extraction()
        
        print("="*60)
        print("🎉 ALL TESTS PASSED!")
        print("="*60)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
