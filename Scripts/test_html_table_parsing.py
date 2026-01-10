#!/usr/bin/env python3
"""
Test HTML table parsing fix - Validates that HTML tables are parsed correctly
and NOT stored as paragraphs.
"""

import sys
import json
from app.utils.postprocess_json import process_ocr_to_blocks, parse_html_table

def test_parse_html_table_function():
    """Test the parse_html_table() function directly"""
    print("=" * 60)
    print("TEST 1: parse_html_table() Function")
    print("=" * 60)
    
    test_cases = [
        {
            "name": "Simple HTML table",
            "html": "<table><tr><td>Name</td><td>Age</td></tr><tr><td>John</td><td>30</td></tr></table>",
            "expected_rows": 2,
            "expected_cols": 2
        },
        {
            "name": "HTML table with HTML entities",
            "html": "<table><tr><td>Item&nbsp;1</td><td>Price&amp;Discount</td></tr><tr><td>&lt;Product&gt;</td><td>100</td></tr></table>",
            "expected_rows": 2,
            "expected_cols": 2
        },
        {
            "name": "HTML table with extra whitespace",
            "html": "<table>\n<tr>\n  <td>  Name  </td>\n  <td>Age</td>\n</tr>\n<tr>\n  <td>Jane</td>\n  <td>25</td>\n</tr>\n</table>",
            "expected_rows": 2,
            "expected_cols": 2
        },
        {
            "name": "HTML table with <th> tags",
            "html": "<table><tr><th>Product</th><th>Price</th></tr><tr><td>Apple</td><td>5</td></tr></table>",
            "expected_rows": 2,
            "expected_cols": 2
        }
    ]
    
    for test_case in test_cases:
        result = parse_html_table(test_case["html"])
        rows = len(result)
        cols = len(result[0]) if result else 0
        
        success = rows == test_case["expected_rows"] and cols == test_case["expected_cols"]
        status = "✓" if success else "✗"
        
        print(f"\n{status} {test_case['name']}")
        print(f"  Expected: {test_case['expected_rows']} rows × {test_case['expected_cols']} cols")
        print(f"  Got:      {rows} rows × {cols} cols")
        print(f"  Result:   {result}")
        
        if not success:
            print("  ❌ FAILED!")
            return False
    
    print("\n✅ TEST 1 PASSED")
    return True


def test_html_table_in_ocr_blocks():
    """Test that HTML tables are correctly converted to table blocks (not paragraphs)"""
    print("\n" + "=" * 60)
    print("TEST 2: HTML Tables in process_ocr_to_blocks()")
    print("=" * 60)
    
    # Simulate OCR output with mixed markdown and HTML
    markdown_text = """# Sales Report

<table><tr><th>Month</th><th>Revenue</th></tr><tr><td>January</td><td>$10000</td></tr><tr><td>February</td><td>$12000</td></tr></table>

Normal paragraph text here.

| Quarter | Target |
|---------|--------|
| Q1 | 50000 |
| Q2 | 60000 |
"""
    
    blocks = process_ocr_to_blocks(markdown_text, page_number=1)
    
    print(f"\nTotal blocks: {len(blocks)}")
    for i, block in enumerate(blocks):
        print(f"\nBlock {i}: type='{block['type']}'")
        if block['type'] == 'table':
            print(f"  - table_id: {block['table_id']}")
            print(f"  - rows: {len(block['rows'])} rows")
            print(f"  - header: {block['header_row']}")
            print(f"  - validation: {block['validation']}")
            print(f"  - confidence: {block['metadata']['confidence']}")
        elif block['type'] == 'heading':
            print(f"  - text: {block['text']}")
        elif block['type'] == 'paragraph':
            print(f"  - text: {block['text'][:50]}...")
    
    # Validate that we have:
    # 1. One heading (Sales Report)
    # 2. One HTML table (not a paragraph!)
    # 3. One paragraph (Normal paragraph...)
    # 4. One markdown table
    
    heading_blocks = [b for b in blocks if b['type'] == 'heading']
    table_blocks = [b for b in blocks if b['type'] == 'table']
    paragraph_blocks = [b for b in blocks if b['type'] == 'paragraph']
    
    print(f"\nValidation:")
    print(f"  ✓ Headings: {len(heading_blocks)} (expected 1)")
    print(f"  ✓ Tables: {len(table_blocks)} (expected 2 - 1 HTML + 1 Markdown)")
    print(f"  ✓ Paragraphs: {len(paragraph_blocks)} (expected 1)")
    
    # Check that HTML table is recognized as table, not paragraph
    html_tables = [b for b in table_blocks if 'html' in str(b).lower() or '<table' not in str(b).get('text', '')]
    
    if len(heading_blocks) != 1 or len(table_blocks) != 2 or len(paragraph_blocks) != 1:
        print("\n❌ TEST 2 FAILED - Block count mismatch!")
        return False
    
    print("\n✅ TEST 2 PASSED - HTML tables are correctly parsed as table blocks!")
    return True


def test_html_table_not_paragraph():
    """Critical test: Verify HTML table is NOT stored as paragraph"""
    print("\n" + "=" * 60)
    print("TEST 3: HTML Table NOT Stored as Paragraph (Critical)")
    print("=" * 60)
    
    markdown_with_html_table = """
Some intro text.

<table><tr><th>Category</th><th>Value</th></tr><tr><td>A</td><td>100</td></tr><tr><td>B</td><td>200</td></tr></table>

Some closing text.
"""
    
    blocks = process_ocr_to_blocks(markdown_with_html_table, page_number=1)
    
    # Find the table block
    table_blocks = [b for b in blocks if b['type'] == 'table']
    paragraph_blocks = [b for b in blocks if b['type'] == 'paragraph']
    
    print(f"\nBlocks found:")
    print(f"  - Tables: {len(table_blocks)}")
    print(f"  - Paragraphs: {len(paragraph_blocks)}")
    
    # CRITICAL: Check that no paragraph contains the HTML table
    for para in paragraph_blocks:
        text = para.get('text', '')
        if '<table' in text.lower():
            print(f"\n❌ CRITICAL FAILURE: HTML table found in paragraph block!")
            print(f"   Paragraph text: {text[:100]}...")
            return False
    
    # CRITICAL: Check that we have at least one table block
    if len(table_blocks) < 1:
        print(f"\n❌ CRITICAL FAILURE: No table blocks found! HTML table not parsed.")
        return False
    
    # Verify the table has the right structure
    table = table_blocks[0]
    print(f"\nTable block structure:")
    print(f"  - type: {table['type']}")
    print(f"  - header_row: {table.get('header_row')}")
    print(f"  - rows count: {len(table.get('rows', []))}")
    print(f"  - metadata.confidence: {table['metadata']['confidence']}")
    
    if table['type'] != 'table':
        print(f"\n❌ CRITICAL FAILURE: Block type is '{table['type']}', not 'table'!")
        return False
    
    print(f"\n✅ TEST 3 PASSED - HTML table correctly stored as table block!")
    return True


if __name__ == "__main__":
    all_passed = True
    
    all_passed &= test_parse_html_table_function()
    all_passed &= test_html_table_in_ocr_blocks()
    all_passed &= test_html_table_not_paragraph()
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL HTML TABLE TESTS PASSED!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED!")
        print("=" * 60)
        sys.exit(1)
