import json

raw_data = """
New Arrival - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/new-arrival
Medical Devices - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/medical-devices
Mouthwashes, Inhaler & Balm - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/mouthwashes
Family Planning - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/family-planning
Face Masks & Safety - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/face-masks-safety
Food Supplements - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/food-supplements
Herbal & Digestive Aids - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/herbal-products
Handwash & Handrub - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/handwash-handrub
Antiseptics - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/antiseptics
Keto Food - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/keto-food
Health & Wellness - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/hygiene
Toys & Sports - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/toys-sports
Pet Care - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/pet-care
Color Pencils - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/color-pencil
Arts & Crafts - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/arts-crafts
Diaries & Notebooks - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/school-supplies
Diaries & Notebooks - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/notebook-diary
Printing Paper - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/printing-paper
Paper Supplies - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/paper-supplies
Pencils - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/erasers-correction-fluid
Pencils - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/pencils
Toner & Ink - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/printer-ink
Highlighters & Markers - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/highlighters
Pens - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/pens
Writing & Printing - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/writing
Desk Organizers - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/desk-organizers
Measuring Tools - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/measuring
Cutting - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/file-folder
Cutting - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/cutting-2
Organizing Accessories - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/organizing-accessories
Stapler & Punch - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/stapler-punch
Tapes, Glues & Adhesive - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/glue-tapes
Organizers - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/organizers
Calculators - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/calculators
Batteries - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/batteries
Office Electronics - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/office-electronics
Stationery & Office - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/stationery-office
Hair Color - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/hair-color
Talcom Powder - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/talcom-powder
Lipsticks & Lip Balm - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/lipsticks-lip-balm
Body & Hair Oil - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/body-hair-oil
Face Wash & Mask - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/face-wash-mask
Creams - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/creams
Petroleum Jelly - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/petroleum-jelly
Lotions - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/lotions
Soaps - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/soaps
Skin Care - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/skin-care-2
Mouthwash & Others - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/mouthwash-others
Toothbrushes - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/toothbrushes
Toothpastes - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/toothpastes
Oral Care - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/oral-care-2
Tissue & Wipes - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/tissue-wipes
Hand Sanitizer - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/hand-sanitizer
Liquid Handwash - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/liquid-handwash
Handwash - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/handwash
Men's Shower Gels - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/mens-shower-gels
Men's Facewash - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/mens-facewash
Cream & Lotion - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/lotion-cream
Men's Hair Care - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/mens-hair-care
Razors & Blades - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/razors-blades
Men's Deodorants - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/deodorants
Beard Grooming - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/beard-grooming
Shaving Needs - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/shaving-needs
Men's Shampoos & Conditioners - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/shampoo
Men's Perfume - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/mens-perfume
Men's Soaps - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/mens-soaps
Men's Care - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/male-care
Serum, Oil & Toners - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/serum-oil-toners
Masks & Cleansers - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/masks-cleansers
Women's Shower Gel - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/womens-shower-gel
Women's Perfume - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/womens-perfume
Female Deo - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/female-deo
Face Wash & Scrub - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/face-wash-scrub
Female Moisturizer - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/female-moisturizer
Feminine Care - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/feminine-care
Women's Shampoos & Conditioners - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/female-shampoo
Hair Care - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/hair-care
Women's Soaps - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/womens-soaps
Women's Care - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/female-care
Personal Care - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/personal-care
Baby Care - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/babycare
Fashion & Lifestyle - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/fashion-lifestyle
Tools & Hardware - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/tools-hardware
Basket & Bucket - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/baskets-buckets
Box & Container - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/box-container
Gardening - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/gardening
Rack & Organizer - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/rack-organizer
Disposables - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/disposables
Home & Kitchen - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/home-kitchen
Trash Bin & Basket - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/trash-bin-basket
Disposables & Trash Bags - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/trash-bags
Air Fresheners - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/air-freshners
Cleaning Accessories - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/cleaning-accessories
Floor & Glass Cleaners - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/floor-glass-cleaners
Cleaning Supplies - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/cleaning
Electronics - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/electronics
Electric & Multiplug - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/electric-multiplug
Mosquito Swatter - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/mosquito-swatter
Lights - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/lights
Lights & Electrical - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/lights-electrical
Kitchen Appliances - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/kitchen-appliances
Kitchen Accessories - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/kitchen-accessories
Napkins & Paper Products - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/paper-products
Toilet Cleaners - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/toilet-cleaning
Laundry - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/laundry
Dishwashing Supplies - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/dish-wash
Ice Cream - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/ice-cream
Diabetic Food - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/diabetic-food
Fish Snacks - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/fish-snacks
Canned Fruits & Sweets - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/canned-fruits
Fish Cans - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/fish-cans
Vegetable Cans - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/vegetable-cans
Beef Snacks - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/beef-snacks
Mushroom Cans - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/mushroom-cans
Vegetable Snacks - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/vegetable-snacks
Frozen Parathas & Roti - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/frozen-parathas-roti
Chicken Snacks - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/chicken-snacks
Frozen & Canned - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/frozen-foods
Baking & Dessert Mixes - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/baking-mixes
Baking Tools - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/baking-tools
Baking Ingredients - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/baking-ingredients
Nuts & Dried Fruits - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/nuts-dried-fruits
Flour - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/flour
Baking - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/baking-needs
Water - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/water
Juice - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/juice
Syrups & Powder Drinks - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/powder-mixes
Coffee - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/coffees
Soft Drinks - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/soft-drinks
Tea - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/beverages-tea
Beverages - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/beverages
Salad Dressing - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/salad-dressing
Cakes - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/cakes
Salted Biscuits - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/salted-biscuits
Popcorn & Nuts - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/popcorn-nuts
Soups - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/soups
Pasta & Macaroni - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/pasta-macaroni
Cream Biscuits - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/cream-biscuits
Toast & Bakery Biscuits - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/toast-biscuits
Plain Biscuits - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/plain-biscuits
Chips & Pretzels - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/chips-pretzels
Local Snacks - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/local-snacks
Cookies - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/cookies-2
Noodles - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/noodles
Snacks - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/snacks
Jellies & Marshmallows - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/halal-marshmallows
Gums, Mints & Mouth Fresheners - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/mints-mouth-fresheners
Candies - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/candies
Wafers - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/wafers
Chocolates - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/chocolates
Candy & Chocolate - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/candy-chocolate
Jams & Jellies - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/jams-jellies
Energy Boosters - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/energy-boosters
Dips, Spreads & Syrups - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/spreads-syrups
Honey - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care,പോക്കറ്റ് ബാഗ്, baby products and more		https://chaldal.com/honey
Cereals - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/cereals
Local Breakfast - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/local-breakfast
Tea & Coffee - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/tea-coffee-2
Breads - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/breads
Eggs - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/eggs-2
Breakfast - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/breakfast
Butter & Sour Cream - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/butter-sour-cream
Condensed Milk & Cream - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/condensed-milk-cream
Cheese - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/cheeses
Yogurt & Sweets - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/yogurt
Liquid & UHT Milk - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/liquid-uht-milk
Powder Milk - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/powder-milk
Eggs - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/eggs
Dairy & Eggs - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/dairy
Other Table Sauces - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/other-sauces
Cooking Sauces - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/cooking-sauces
Pickles - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/pickles
Tomato Sauces - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/tomato-sauces
Sauces & Pickles - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/sauces-pickles
Premium Ingredients - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/premium-ingredients
Ghee - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/ghee
Colors & Flavours - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/colors-flavours
Oil - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/oil
Special Ingredients - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/miscellaneous
Shemai & Suji - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/shemai-suji
Ready Mix - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/ready-mix
Dal or Lentil - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/dal-or-lentil
Rice - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/rices
Salt & Sugar - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/salt-sugar
Spices - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/spices
Cooking - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/cooking
Dried Fish - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/dried-fish
Tofu & Meat Alternatives - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/tofu-meat-alternatives
Meat - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/meat-new
Frozen Fish - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/frozen-fish
Premium Perishables - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/premium-perishables
Chicken & Poultry - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/chicken-poultry
Meat & Fish - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/meat-fish
Fresh Fruits - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/fresh-fruit
Fresh Vegetables - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/fresh-vegetable
Fruits & Vegetables - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/fruits-vegetables
Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/food
Flash Sales - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/flash-sales
Ramadan - Online Grocery Shopping and Delivery in Bangladesh | Buy fresh food items, personal care, baby products and more		https://chaldal.com/ramadan
""

cats = []
seen_urls = set()

for line in raw_data.strip().split('\n'):
    parts = line.split('\t\t')
    if len(parts) >= 2:
        name = parts[0].split(' - Online Grocery')[0].strip()
        url = parts[1].strip()
        
        if url not in seen_urls:
            cats.append({
                "name": name,
                "url": url,
                "active": True
            })
            seen_urls.add(url)

with open('categories.json', 'w') as f:
    json.dump(cats, f, indent=2)
    
print(f"Imported {len(cats)} categories.")
