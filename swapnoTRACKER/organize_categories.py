import json

# Hierarchical mapping based on user request
hierarchy = {
    "Food": [
        "https://www.shwapno.com/food",
        {
            "Fruits and Vegetables": [
                "https://www.shwapno.com/fruits-and-vegetables",
                "https://www.shwapno.com/fresh-fruits",
                "https://www.shwapno.com/fresh-vegetables",
                "https://www.shwapno.com/dry-fruits",
                "https://www.shwapno.com/dry-vegetables"
            ]
        },
        {
            "Meat and Fish": [
                "https://www.shwapno.com/meat-and-fish",
                {
                    "Fish": [
                        "https://www.shwapno.com/fish",
                        "https://www.shwapno.com/fresh-water-fish",
                        "https://www.shwapno.com/sea-fish"
                    ]
                },
                {
                    "Meat": [
                        "https://www.shwapno.com/meat",
                        "https://www.shwapno.com/beef",
                        "https://www.shwapno.com/chicken",
                        "https://www.shwapno.com/mutton",
                        "https://www.shwapno.com/other-birds"
                    ]
                }
            ]
        },
        "https://www.shwapno.com/eggs",
        {
            "Baking Needs": [
                "https://www.shwapno.com/baking-needs",
                "https://www.shwapno.com/baking-ingredients",
                "https://www.shwapno.com/flours",
                "https://www.shwapno.com/colours-and-flavors"
            ]
        },
        {
            "Beverages": [
                "https://www.shwapno.com/beverages",
                {
                    "Tea": [
                        "https://www.shwapno.com/tea",
                        "https://www.shwapno.com/Black-Tea-2",
                        "https://www.shwapno.com/Green-Tea-2",
                        "https://www.shwapno.com/Flavored-Tea",
                        "https://www.shwapno.com/Tea-Others"
                    ]
                },
                {
                    "Coffee": [
                        "https://www.shwapno.com/coffee",
                        "https://www.shwapno.com/Instant-Coffee",
                        "https://www.shwapno.com/Coffee-Mate",
                        "https://www.shwapno.com/Coffee-Others"
                    ]
                },
                "https://www.shwapno.com/juice",
                "https://www.shwapno.com/soft-drinks",
                "https://www.shwapno.com/energy-and-malted-drinks",
                "https://www.shwapno.com/syrups-and-powder-drinks",
                "https://www.shwapno.com/drinking-water"
            ]
        },
        {
            "Snacks": [
                "https://www.shwapno.com/snacks",
                "https://www.shwapno.com/Noodles",
                "https://www.shwapno.com/Pasta",
                "https://www.shwapno.com/Macaroni",
                "https://www.shwapno.com/soup",
                "https://www.shwapno.com/cakes",
                {
                    "Biscuits": [
                        "https://www.shwapno.com/biscuits",
                        "https://www.shwapno.com/Energy-Biscuit",
                        "https://www.shwapno.com/Milk-Biscuits",
                        "https://www.shwapno.com/Cream-Sandwich-Biscuits",
                        "https://www.shwapno.com/Toast-Biscuit",
                        "https://www.shwapno.com/Salted",
                        "https://www.shwapno.com/Sugar-Free-Biscuits",
                        "https://www.shwapno.com/Dry-Cake",
                        "https://www.shwapno.com/Biscuits-Others"
                    ]
                },
                "https://www.shwapno.com/local-snacks",
                "https://www.shwapno.com/popcorn-and-nuts",
                "https://www.shwapno.com/chips-and-pretzels",
                "https://www.shwapno.com/dried-fruits",
                "https://www.shwapno.com/mayonnaise",
                "https://www.shwapno.com/shemai-and-suji"
            ]
        },
        {
            "Frozen": [
                "https://www.shwapno.com/Frozen",
                "https://www.shwapno.com/Paratha",
                "https://www.shwapno.com/Singara",
                "https://www.shwapno.com/Samosa",
                "https://www.shwapno.com/Nuggets",
                "https://www.shwapno.com/Sausage",
                "https://www.shwapno.com/French-Fries",
                "https://www.shwapno.com/Frozen-Snacks-Others"
            ]
        },
        {
            "Canned Food": [
                "https://www.shwapno.com/canned-food",
                "https://www.shwapno.com/Canned-Vegetables",
                "https://www.shwapno.com/Canned-Fish",
                "https://www.shwapno.com/Canned-Fruits",
                "https://www.shwapno.com/Canned-Meat-2"
            ]
        },
        "https://www.shwapno.com/ice-cream",
        "https://www.shwapno.com/candy-chocolate",
        {
            "Dairy": [
                "https://www.shwapno.com/dairy",
                "https://www.shwapno.com/ghee",
                "https://www.shwapno.com/butter",
                "https://www.shwapno.com/Cheese",
                "https://www.shwapno.com/condensed-milk-and-cream",
                "https://www.shwapno.com/liquid-and-uht-milk",
                "https://www.shwapno.com/Low-Fat-Milk-2",
                "https://www.shwapno.com/Milk-Others",
                {
                    "Powder Milk": [
                        "https://www.shwapno.com/powder-milk",
                        "https://www.shwapno.com/Full-Cream-Milk",
                        "https://www.shwapno.com/Diabetic-Milk",
                        "https://www.shwapno.com/Low-Fat-Milk",
                        "https://www.shwapno.com/Non-Fat-Milk",
                        "https://www.shwapno.com/Powder-Milk-Others"
                    ]
                },
                "https://www.shwapno.com/Yogurt",
                "https://www.shwapno.com/Laban",
                "https://www.shwapno.com/Lacchi"
            ]
        },
        {
            "Breakfast": [
                "https://www.shwapno.com/breakfast",
                "https://www.shwapno.com/breads",
                "https://www.shwapno.com/jam-and-jelly",
                "https://www.shwapno.com/dips-and-spreads",
                "https://www.shwapno.com/honey",
                "https://www.shwapno.com/cereals"
            ]
        },
        {
            "Sauces and Pickles": [
                "https://www.shwapno.com/sauces-and-pickles",
                "https://www.shwapno.com/pickle-and-condiments",
                "https://www.shwapno.com/dipping-sauce",
                "https://www.shwapno.com/cooking-sauce"
            ]
        },
        {
            "Cooking": [
                "https://www.shwapno.com/cooking",
                {
                    "Rice": [
                        "https://www.shwapno.com/rice",
                        "https://www.shwapno.com/loose-rice",
                        "https://www.shwapno.com/packed-rice"
                    ]
                },
                {
                    "Daal": [
                        "https://www.shwapno.com/daal-or-lentil",
                        "https://www.shwapno.com/loose-daal",
                        "https://www.shwapno.com/packed-daal"
                    ]
                },
                {
                    "Oil": [
                        "https://www.shwapno.com/oil",
                        "https://www.shwapno.com/soybean-oil",
                        "https://www.shwapno.com/rice-bran-oil",
                        "https://www.shwapno.com/sunflower-oil",
                        "https://www.shwapno.com/olive-oil",
                        "https://www.shwapno.com/mustard-oil",
                        "https://www.shwapno.com/flavored-oil"
                    ]
                },
                {
                    "Spices": [
                        "https://www.shwapno.com/spices",
                        "https://www.shwapno.com/Regular-Spice",
                        "https://www.shwapno.com/Mixed-Spice",
                        "https://www.shwapno.com/Wholespice"
                    ]
                },
                {
                    "Salt and Sugar": [
                        "https://www.shwapno.com/salt-and-sugar",
                        "https://www.shwapno.com/salt",
                        "https://www.shwapno.com/sugar"
                    ]
                }
            ]
        }
    ]
}

def flatten_hierarchy(h, parent=None):
    flat = []
    if isinstance(h, list):
        for item in h:
            flat.extend(flatten_hierarchy(item, parent))
    elif isinstance(h, dict):
        for name, sub in h.items():
            # If the first item in sub is a URL, it's the main link for this category
            main_url = sub[0] if isinstance(sub, list) and isinstance(sub[0], str) else None
            flat.append({
                "name": name,
                "url": main_url,
                "parent": parent,
                "enabled": True
            })
            flat.extend(flatten_hierarchy(sub, name))
    elif isinstance(h, str):
        # Regular URL
        name = h.split('/')[-1].replace('-', ' ').title()
        flat.append({
            "name": name,
            "url": h,
            "parent": parent,
            "enabled": True
        })
    return flat

with open('categories.json', 'r') as f:
    existing = json.load(f)

# Map URLs to existing objects to preserve status if possible
existing_map = {c['url']: c for c in existing}

flat_new = flatten_hierarchy(hierarchy)
new_categories = []

seen_urls = set()
for c in flat_new:
    if c['url'] in existing_map:
        c['enabled'] = existing_map[c['url']].get('enabled', True)
    if c['url'] not in seen_urls or not c['url']:
        new_categories.append(c)
        if c['url']: seen_urls.add(c['url'])

# Add remaining categories from existing that weren't in the hierarchy
for c in existing:
    if c['url'] not in seen_urls:
        c['parent'] = None
        new_categories.append(c)

with open('categories.json', 'w') as f:
    json.dump(new_categories, f, indent=2)

print(f"Organized {len(new_categories)} categories.")
