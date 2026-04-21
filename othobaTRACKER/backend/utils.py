import re

def parse_unit(name: str):
    """
    Parses unit information from product names.
    Returns (unit_type, standardized_value)
    Standardizes:
    - Weight -> kg
    - Volume -> L
    - Count -> piece
    """
    name = name.lower()
    # Patterns for weight/volume/count
    patterns = [
        r"(\d+(?:\.\d+)?)\s*(kg|kilogram)",
        r"(\d+(?:\.\d+)?)\s*(gm|g|gram)",
        r"(\d+(?:\.\d+)?)\s*(ltr|l|liter|litre)",
        r"(\d+(?:\.\d+)?)\s*(ml|milliliter)",
        r"(\d+(?:\.\d+)?)\s*(pcs|pc|each|piece)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, name)
        if match:
            value = float(match.group(1))
            unit = match.group(2)
            
            if unit in ['kg', 'kilogram']:
                return 'kg', value
            if unit in ['gm', 'g', 'gram']:
                return 'kg', value / 1000.0
            if unit in ['ltr', 'l', 'liter', 'litre']:
                return 'L', value
            if unit in ['ml', 'milliliter']:
                return 'L', value / 1000.0
            if unit in ['pcs', 'pc', 'each', 'piece']:
                return 'piece', value
                
    # Default if no unit found
    return 'piece', 1.0
