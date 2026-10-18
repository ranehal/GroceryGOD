"""Regression tests for per-unit price normalization (Tk/kg, Tk/L, Tk/piece).

The bug these lock down: a bare pack count was multiplied by the printed weight,
so "Golden Harvest Chicken Spring Roll 14Pcs 300gm" (250 Tk) was advertised as
59.5 Tk/kg (250 / 4.2 kg) instead of 833.33 Tk/kg (250 / 0.3 kg).

Run with pytest (``python -m pytest tests -q``) or directly
(``python tests/test_unit_normalization.py``).
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, 'swapnoTRACKER'))

import aggregator as agg


def check(name, unit, price, want_unit_type, want_normalized):
    got_type, got_norm = agg.parse_unit_and_calculate(name, unit, price)
    assert got_type == want_unit_type, f'{name!r}: unit_type {got_type} != {want_unit_type}'
    assert abs(got_norm - want_normalized) < 0.05, f'{name!r}: {got_norm} != {want_normalized}'


# --- the reported bug: bare pack count is the TOTAL net weight -----------------
def test_pack_count_is_total_weight():
    check('Golden Harvest Chicken Spring Roll 14Pcs 300gm', '300 gm', 250, 'kg', 833.33)
    check('Golden Harvest Mini Chicken Spring Roll 15 pcs 300 gm', '300 gm', 235, 'kg', 783.33)
    check('Golden Harvest Frozen Chicken Samosa 25 pcs 250 gm', '250 gm', 215, 'kg', 860.0)
    check('Golden Harvest Premium Deshi Paratha 20 pcs 1300 gm', '1300 gm', 320, 'kg', 246.15)
    check('Chopstick Ramen Hot Cheese Instant Noodles 8 pack 640 gm', '640 gm', 650, 'kg', 1015.63)
    check('Maxim Mocha Gold Mild Coffee Mix 100 pcs 1.2 kg', '1.2 kg', 3358, 'kg', 2798.33)
    check('RINDA ICY TAMARIND CANDY 300P 1280G', '1280G', 2304, 'kg', 1800.0)
    check('Snickers Share Pack 10pcs 180gm', '180gm', 325, 'kg', 1805.56)
    check('Jhatpot Deshi Paratha 20Pcs 1300gm', '1300gm', 272, 'kg', 209.23)
    check('Bread Pit Hot Dog Bun 4Pcs 200gm', 'N/A', 90, 'kg', 450.0)


def test_parenthesised_piece_count_still_total_weight():
    check('AG Food Vegetable Spring Roll 400gm (10Pcs)', '400gm', 160, 'kg', 400.0)
    check('Kazi Farms Kitchen Chicken Spring Roll (23-25 pcs) 250 gm', '250 gm', 215, 'kg', 860.0)
    check('Paragon Chicken Mini Spring Roll 300gm (18-20Pcs)', '300.0 gm', 211.5, 'kg', 705.0)


# --- explicit multiplication is still honoured --------------------------------
def test_explicit_multiplication():
    check('Pran Mr. Noodles Instant Magic Masala 16x62gm', '62gm', 345, 'kg', 347.78)
    check('Kelloggs Varity Combo Pack 5px24gm', '24gm', 100, 'kg', 833.33)
    check('Toren Rocco White 24 x 20g bars chocolates', '20.0g', 1050, 'kg', 2187.5)
    check('Mr. Noodles Magic Masala 8 Pcs Pack 62gm X 8pcs', '62gm', 128, 'kg', 258.06)
    check('Old Town White Coffee ( 15 X 25g ), 375g', '375.0gm', 1050, 'kg', 2800.0)
    check('Shoklata Sweets Kunafa Chocolate - 10 Pieces x 20g (200g)', '20.0g', 1200, 'kg', 6000.0)
    check('Parachute Naturale Shampoo (5.25 ml X 12 pcs) 63 ml', '5.25 ml', 24, 'liter', 380.95)


def test_per_piece_size_then_pack_total():
    check('Balconi Mix max with tasty cocoa 1 Packet 35 gm 10 pcs 350 gm', '350.0gm', 950, 'kg', 2714.29)


# --- plain sizes are untouched ------------------------------------------------
def test_plain_weight_and_volume():
    check('Paragon Chicken Spring Roll 400gm', '400 gm', 262, 'kg', 655.0)
    check('Odonil Air Freshener Lavender Mist 300ml', '300.0ml', 320, 'liter', 1066.67)
    check('KaziFarms Kitchen Chicken Spring Roll 250gm', '250.0 gm', 230, 'kg', 920.0)
    check('Country Natural Chicken Spring Roll 300gm', '300gm', 199, 'kg', 663.33)


def test_promotions():
    # 250gm + 50gm free = 300gm pack
    check('Coffee 250gm + 50gm Free', '250gm', 300, 'kg', 1000.0)
    # Buy 2 Get 1 Free on a 240gm pack: three packs paid twice
    check('Ifad Eggy Instant Mashed Noodles 4 pcs 240 gm (Buy 2 Get 1 Free)', '240 gm', 180, 'kg', 250.0)


def test_piece_promo_is_not_double_counted():
    # 16 pads listed, "Buy16 Pad Get8 Pad Free" -> 24 pads for 200 Tk
    check('Freedom Heavy Flow Wings 16Pad (Buy16 Pad Get8 Pad Free)', '1 Piece', 200, 'piece', 8.33)
    check('Fresh Anonna Sanitary Napkin Heavy Flow (Buy15Pads Get8Pads Free)', '1 Piece', 180, 'piece', 7.83)


def test_display_unit_matches_normalization():
    assert agg.get_clean_display_unit('Golden Harvest Chicken Spring Roll 14Pcs 300gm', '300 gm') == '300 gm'
    assert agg.get_clean_display_unit('Pran Mr. Noodles Instant Magic Masala 16x62gm', '62gm') == '992 gm'
    assert agg.get_clean_display_unit('Pran Mr. Noodles Instant Magic Masala 16x62gm', '62gm') == '992 gm'


# --- the Shwapno scraper uses the same rules -----------------------------------
def test_swapno_scraper_matches_aggregator():
    import scraper_web
    qty, norm, u_type = scraper_web.normalize_unit('Golden Harvest Chicken Spring Roll 14Pcs 300gm', '250')
    assert u_type == 'kg' and abs(norm - 833.33) < 0.05, (qty, norm, u_type)
    qty, norm, u_type = scraper_web.normalize_unit('Pran Mr. Noodles Instant Magic Masala 16x62gm', '345')
    assert u_type == 'kg' and abs(norm - 347.78) < 0.05, (qty, norm, u_type)
    qty, norm, u_type = scraper_web.normalize_unit('Jhatpot Deshi Paratha 20Pcs 1300gm', '272')
    assert u_type == 'kg' and abs(norm - 209.23) < 0.05, (qty, norm, u_type)
    qty, norm, u_type = scraper_web.normalize_unit('Egg Loose', '12.5')
    assert u_type == 'pc' and abs(norm - 12.5) < 0.05, (qty, norm, u_type)
    qty, norm, u_type = scraper_web.normalize_unit('Colgate Gentle Enamel Tooth Brush (Buy2 Get2 Free)', '360')
    assert u_type == 'pc' and abs(norm - 360) < 0.05, (qty, norm, u_type)


if __name__ == '__main__':
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith('test_') or not callable(fn):
            continue
        try:
            fn()
            print(f'PASS {name}')
        except AssertionError as exc:
            failures += 1
            print(f'FAIL {name}: {exc}')
    print(f'\n{len([k for k in globals() if k.startswith("test_")]) - failures} passed, {failures} failed')
    sys.exit(1 if failures else 0)
