# utils.py

import re

def get_apparel_sort_key(size_str):
    """Giyim bedenlerini mantıksal olarak sıralamak için bir anahtar üretir."""
    if not isinstance(size_str, str): return (3, 9999, size_str)
    size_upper = size_str.strip().upper()
    size_order_map = {'XXS': 0, 'XS': 1, 'S': 2, 'M': 3, 'L': 4, 'XL': 5, 'XXL': 6, '2XL': 6, '3XL': 7, 'XXXL': 7, '4XL': 8, 'XXXXL': 8, '5XL': 9, 'XXXXXL': 9, 'TEK EBAT': 100, 'STANDART': 100}
    if size_upper in size_order_map: return (1, size_order_map[size_upper], size_str)
    numbers = re.findall(r'\d+', size_str)
    if numbers: return (2, int(numbers[0]), size_str)
    return (3, 9999, size_str)

def get_variant_size(variant):
    model = variant.get('model', "")
    return (model.get('value', "") if isinstance(model, dict) else str(model)).strip() or None

def get_variant_color(variant):
    return (variant.get('color') or "").strip() or None