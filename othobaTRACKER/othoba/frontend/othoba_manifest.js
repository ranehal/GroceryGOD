window.othobaManifest = {
  metadata: {
    total: 50000,
    date_range: '2024-01 to 2026-07',
    source: 'har',
    har_capture_date: '2026-07-30',
    api_base: 'https://app.othoba.com/api-frontend',
    categories: [
      {name:'Global Finds',id:3411,sub:[
        {name:'HAIRBAND',id:3417},{name:'BAGS AND ACCESSORIES',id:3418},{name:'TOYS',id:3419},{name:'STATIONARY',id:3420},{name:'1-99',id:3412},{name:'100-199',id:3413},{name:'200-499',id:3414},{name:'500-999+',id:3415}
      ]},
      {name:'Quick Commerce',id:3449,sub:[
        {name:'Pharmacy',id:3267},{name:'Grocery (Quick Commerce)',id:3970},{name:'Food (Quick Commerce)',id:3971},{name:'Mithai',id:3523},{name:'Frozen Foods',id:3525},{name:'Fry Bucket',id:3524},{name:'Tasty Treat',id:3473}
      ]},
      {name:'Daily Bazar',id:5292,sub:[
        {name:'Grocery Staples',id:5302},{name:'Household Essentials',id:5309},{name:'Laundry & Cleaning',id:5304},{name:'Dairy, Chilled & Eggs',id:5299},{name:'Fish & Meat',id:5296},{name:'Fresh Produce',id:5295},{name:'Coffee, Tea & Beverages',id:5303},{name:'Snacks',id:5301},{name:'Mother & Baby',id:5307},{name:'Beauty & Personal Care',id:5306},{name:'Pharmacy',id:5308},{name:'Pet Care',id:5305},{name:'Ice Cream & Sweet Delights',id:5300}
      ]},
      {name:'Electronics & Appliances',id:32,sub:[
        {name:'Home Appliances',id:65},{name:'Small Appliances',id:3141},{name:'Mobile Phones & Tablets',id:3668},{name:'Computers, Components & Accessories',id:3669},{name:'Gadgets',id:90},{name:'Cameras & Accessories',id:1100},{name:'Large Appliances',id:256},{name:'Kitchen Appliances',id:71},{name:'Electrical Hardware',id:2009},{name:'Smartwatches & Accessories',id:3862},{name:'Audio, Video & Games',id:3863},{name:'Electrical Accessories',id:3865}
      ]},
      {name:'Mother, Baby & Toys',id:3656,sub:[
        {name:'Baby Care',id:3657},{name:'Toys',id:220},{name:'Mothers Care',id:3658}
      ]},
      {name:'Beauty',id:259,sub:[
        {name:'Skin Care',id:271},{name:'Grooming & Wellness',id:260},{name:'Makeup',id:283},{name:'Hair Care',id:270},{name:'Oral Care',id:1040},{name:'Fragrance',id:3631},{name:'Feminine Care',id:3284}
      ]},
      {name:'Sports',id:127,sub:[
        {name:'Sports',id:597},{name:'Fitness & Exercise',id:3621},{name:'Bicycle',id:128},{name:'Camping & Hiking',id:3620}
      ]},
      {name:'Automotive',id:39,sub:[
        {name:'Lubricants & Oils',id:1302},{name:'Car & Bike Care',id:478},{name:'Biking & Accessories',id:1272},{name:'Bikes',id:3528},{name:'Cars',id:3527}
      ]},
      {name:'Stationery, Books & Music',id:119,sub:[
        {name:'Stationery',id:3427},{name:'Books',id:3460},{name:'Office Supplies',id:3459},{name:'Educational Supplies',id:3460},{name:'Color Supplies',id:3461},{name:'Gifts & Wrapping',id:5278}
      ]},
      {name:'Fashion',id:67,sub:[
        {name:'Men',id:91},{name:'Women',id:92},{name:'Bags, Wallets & Belts',id:3157},{name:'Shoes',id:3487},{name:'Jewellary, Watch and Accessories',id:3196}
      ]},
      {name:'Home',id:35,sub:[
        {name:'Furniture',id:46},{name:'Household Essentials',id:3149},{name:'Home Decor',id:83},{name:'Kitchen & Dining',id:94},{name:'Hardware & Sanitary Fittings',id:88}
      ]},
      {name:'Grocery',id:179,sub:[
        {name:'Fish & Meat',id:3888},{name:'Milk',id:239},{name:'Bread & Bakery',id:765},{name:'Snacks',id:766},{name:'Rice',id:240},{name:'Oil',id:247},{name:'Dairy',id:769},{name:'Spice & Ready Mix',id:244},{name:'Noodles',id:245},{name:'Frozen Snacks',id:246},{name:'Beverages',id:3901},{name:'Breakfast Essentials',id:3900}
      ]},
      {name:'Garden & Pet Care',id:3428,sub:[
        {name:'Pet Care',id:3508},{name:'Gardening',id:3428}
      ]},
      {name:'Special Weekly Offer',id:4953,sub:[
        {name:'Geyser & Water Heater',id:5276},{name:'Air Conditioner',id:2174},{name:'Air Fryer',id:3234},{name:'Refrigerator',id:2979},{name:'Washing Machine',id:2956},{name:'Cooker',id:170}
      ]}
    ]
  },
  endpoints: {
    catalog_root: '/Catalog/GetCatalogRoot',
    category_products: (id) => `/Catalog/GetCategoryProducts/${id}`,
    category_subcategories: (id) => `/Catalog/GetCategorySubcategories/${id}`,
    product_details: (id) => `/Product/GetProductDetails/${id}`,
    product_related: (id) => `/Product/GetRelatedProducts/${id}`,
    homepage: '/Home/GetHomePageProductList',
    trending: '/OthobaTrendingStore/GetOthobaTrendingStoreData',
    top_picks: '/OthobaTrendingStore/GetTopPicksProduct'
  }
};
