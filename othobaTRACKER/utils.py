import re

def clean_tolerance(text):
    if not text:
        return ""
    tol_indicator = r'(?:\((?:[±\u00b1]|\+/-\s*|\+-\s*|[+\-]\s*\d+)\s*\)?|\b(?:[±\u00b1]|\+/-\s*|\+-\s*))'
    t = re.sub(
        r'(\d+(?:\.\d+)?)\s*(kg|gm|gram|g|ml|ltr|liter|l)?\s*' + tol_indicator + r'\s*\d*(?:\.\d+)?\s*(kg|gm|gram|g|ml|ltr|liter|l)?\)?',
        lambda m: f"{m.group(1)} {m.group(2) or m.group(3) or ''}",
        text,
        flags=re.IGNORECASE
    )
    t = re.sub(r'\(?(?:[±\u00b1]|\+/-\s*|\+-\s*)\s*\d+(?:\.\d+)?\s*(?:kg|gm|gram|g|ml|ltr|liter|l)?\)?', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\(?(?:[±\u00b1]|\+/-\s*|\+-\s*)\)?', '', t)
    return t

def parse_promotion(full_text):
    word_num = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
    multiplier = 1.0
    extra_free_weight_gm = 0.0
    extra_free_volume_ml = 0.0

    plus_free = re.search(r'(?:\+|\bplus\b|\bwith\b)\s*(\d+(?:\.\d+)?)\s*(kg|gm|gram|g|ml|ltr|liter|l)\s*(?:free|extra)?\b', full_text, re.IGNORECASE)
    if plus_free:
        f_val = float(plus_free.group(1))
        f_unit = plus_free.group(2).lower()
        if f_unit in ['gm', 'gram', 'g']:
            extra_free_weight_gm += f_val
        elif f_unit == 'kg':
            extra_free_weight_gm += f_val * 1000
        elif f_unit == 'ml':
            extra_free_volume_ml += f_val
        elif f_unit in ['ltr', 'liter', 'l']:
            extra_free_volume_ml += f_val * 1000

    bg_weight = re.search(
        r'\bbuy\s*(\d+|one|two|three|four|five|six)?\s*(?:pcs?|packs?|pads?|bottles?|t\s*brush)?\s*(?:and|&)?\s*get\s*(?:[a-zA-Z\.\-]+\s*){0,3}?(\d+(?:\.\d+)?)\s*(kg|gm|gram|g|ml|ltr|liter|l)\s*(?:[a-zA-Z\.\-]+\s*){0,3}(?:free|extra)\b',
        full_text,
        re.IGNORECASE
    )
    if bg_weight:
        b_str = bg_weight.group(1)
        b_val = float(word_num.get(b_str.lower(), b_str) if b_str else 1)
        f_val = float(bg_weight.group(2))
        f_unit = bg_weight.group(3).lower()
        multiplier = b_val
        if f_unit in ['gm', 'gram', 'g']:
            extra_free_weight_gm += f_val
        elif f_unit == 'kg':
            extra_free_weight_gm += f_val * 1000
        elif f_unit == 'ml':
            extra_free_volume_ml += f_val
        elif f_unit in ['ltr', 'liter', 'l']:
            extra_free_volume_ml += f_val * 1000
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    bg_count = re.search(
        r'\bbuy\s*(\d+|one|two|three|four|five|six)\s*(?:pcs?|packs?|pads?|bottles?|t\s*brush)?\s*(?:and|&)?\s*get\s*(\d+|one|two|three|four|five|six)\s*(?:pcs?|packs?|pads?|bottles?|t\s*brush)?\s*(?:free|combo|item|\b)',
        full_text,
        re.IGNORECASE
    )
    if bg_count:
        b_str = bg_count.group(1).lower()
        g_str = bg_count.group(2).lower()
        b_val = float(word_num.get(b_str, b_str))
        g_val = float(word_num.get(g_str, g_str))
        multiplier = b_val + g_val
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    b_short = re.search(r'\bb(\d+)g(\d+)\b', full_text, re.IGNORECASE)
    if b_short:
        multiplier = float(b_short.group(1)) + float(b_short.group(2))
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    if re.search(r'\bbogo\b', full_text, re.IGNORECASE):
        multiplier = 2.0
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    b_save = re.search(
        r'\bbuy\s*(\d+|one|two|three|four|five|six)\s*(?:pcs?|packs?|pads?|bottles?)?\s*(?:save|only|for|at|\btk\b|\bbdt\b|\btk\.\b|\b\d+\s*tk\b)',
        full_text,
        re.IGNORECASE
    )
    if b_save:
        b_str = b_save.group(1).lower()
        multiplier = float(word_num.get(b_str, b_str))
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    b_save_rev = re.search(
        r'(?:save|only|for|at)\s*(?:tk\b|\bbdt\b|tk\.\b|\b\d+\s*tk\b|\d+)\s*(?:[a-zA-Z0-9\s\.\-]{0,15}?)\(?\s*buy\s*(\d+|one|two|three|four|five|six)',
        full_text,
        re.IGNORECASE
    )
    if b_save_rev:
        b_str = b_save_rev.group(1).lower()
        multiplier = float(word_num.get(b_str, b_str))
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    b_pack = re.search(r'\b(?:pack\s*of|combo\s*of|pack\s*x|combo\s*x)\s*(\d+)\b', full_text, re.IGNORECASE)
    if b_pack:
        multiplier = float(b_pack.group(1))
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    b_combo = re.search(r'combo\s*pack\s*\(?\s*buy\s*(\d+)', full_text, re.IGNORECASE)
    if b_combo:
        multiplier = float(b_combo.group(1))
        return multiplier, extra_free_weight_gm, extra_free_volume_ml

    return max(1.0, multiplier), extra_free_weight_gm, extra_free_volume_ml

def parse_unit(name: str):
    """
    Parses unit information from product names.
    Returns (unit_type, standardized_value)
    Standardizes:
    - Weight -> kg
    - Volume -> L
    - Count -> piece
    """
    if not name:
        return 'piece', 1.0

    name_clean = clean_tolerance(name).lower()
    multiplier, extra_free_weight_gm, extra_free_volume_ml = parse_promotion(name_clean)

    # Patterns for weight/volume/count
    patterns = [
        (r"(\d+(?:\.\d+)?)\s*(kg|kilogram)", 'kg', 1.0),
        (r"(\d+(?:\.\d+)?)\s*(gm|g|gram)", 'kg', 1.0 / 1000.0),
        (r"(\d+(?:\.\d+)?)\s*(ltr|l|liter|litre)", 'L', 1.0),
        (r"(\d+(?:\.\d+)?)\s*(ml|milliliter)", 'L', 1.0 / 1000.0),
        (r"(\d+(?:\.\d+)?)\s*(pcs|pc|each|piece)", 'piece', 1.0)
    ]

    for pat, u_type, factor in patterns:
        match = re.search(pat, name_clean)
        if match:
            val = float(match.group(1))
            if u_type == 'kg':
                if factor == 1.0:
                    total_kg = (val * multiplier) + (extra_free_weight_gm / 1000.0)
                else:
                    total_kg = ((val * multiplier) + extra_free_weight_gm) / 1000.0
                return 'kg', total_kg
            elif u_type == 'L':
                if factor == 1.0:
                    total_l = (val * multiplier) + (extra_free_volume_ml / 1000.0)
                else:
                    total_l = ((val * multiplier) + extra_free_volume_ml) / 1000.0
                return 'L', total_l
            else:
                return 'piece', val * multiplier

    if multiplier > 1:
        return 'piece', multiplier

    # Default if no unit found
    return 'piece', 1.0
