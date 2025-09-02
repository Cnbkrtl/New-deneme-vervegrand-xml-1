#!/usr/bin/env python3
# Fix indentation issues in shopify_sync.py

# Read the file
with open('shopify_sync.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix the problematic section
fixed_lines = []
for i, line in enumerate(lines):
    line_num = i + 1
    
    # Fix line 195-201 area
    if line_num >= 195 and line_num <= 202:
        if line_num == 195:
            fixed_lines.append("            return {\n")
        elif line_num == 196:
            fixed_lines.append("                'success': False,\n")
        elif line_num == 197:
            fixed_lines.append("                'error': str(e),\n")
        elif line_num == 198:
            fixed_lines.append("                'action': 'failed'\n")
        elif line_num == 199:
            fixed_lines.append("            }\n")
        elif line_num == 200:
            fixed_lines.append("\n")
        elif line_num == 201:
            fixed_lines.append("    def update_product(self, product_id, product_data):\n")
        else:
            fixed_lines.append(line)
    else:
        fixed_lines.append(line)

# Write the fixed file
with open('shopify_sync.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("✅ Fixed indentation issues")
