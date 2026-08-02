# HAR findings — Meena Bazar mobile API

Capture source: Reqable 3.2.17, recorded from 2026-07-31 19:13:10Z to 19:15:36Z.

## Traffic summary

- 1,285 total HAR entries.
- 97 requests to `https://meenabazardev.com`.
- 1,111 requests were primarily product/banner images on Amazon S3.
- Meena API responses use JSON and return HTTP 201/202 even for several successful GET requests; treat every 2xx response as success and verify the JSON `status` field.
- Every observed Meena request carried one bearer credential. The HAR also contains personal account data returned by `startup`. Neither is included in this starter.

## Reusable public-catalog contracts

| Purpose | Method and path | Inputs | Response data |
|---|---|---|---|
| Navigation hierarchy | `GET /api/mobile/front/nav/categories/list` | none | Categories with nested subcategories and slugs |
| Category/subcategory page | `POST /api/mobile/front/product/category/{slug}` | JSON: `StartSl`, `NoOfItem`, `AreaId`, `SubUnitId`, `SearchType`, empty filter arrays | `all_category`, `category_name`, `category_product`, `nav_serch`, optional banners |
| Home composition | `GET /api/mobile/front/home/section` | JSON body: `AreaId`, `SubUnitId` | Deals, top banners, offer tags, section products/thumbnails, payment offers, featured brands |
| Tag products | `GET /api/mobile/front/tag/product` | `StartSl`, `NoOfItem`, `AreaId`, `SubUnitId`, `TagSlug` | `{ product: [...] }` |
| All offers | `GET /api/mobile/front/offer/product/all` | `StartSl`, `NoOfItem`, `AreaId`, `SubUnitId` | Product array |
| Offer count | `GET /api/mobile/front/offer/product/count` | `AreaId`, `SubUnitId` | Integer |
| Featured brand products | `GET /api/mobile/front/product/brand/{slug}` | JSON category-style paging body with `SearchType: "B"` | `{ Brand: [...] }` |

## Request semantics observed

- Default location in this capture: `AreaId=265`, `SubUnitId=11`.
- Paging is one-based: `StartSl=1`, normally `NoOfItem=50`.
- Category request: `SearchType="C"`.
- Subcategory request: `SearchType="S"`; the captured example used slug `tea`.
- Brand request: `SearchType="B"`.
- The first product commonly contains `TotalItem`; stop after the total, a short/empty page, or a repeated page signature.
- The category endpoint's `all_category` returned 16 categories, while the navigation endpoint returned 13 menu-visible categories. Using both avoids missing hidden categories such as promotions, cosmetics, or toys.
- `nav_serch` contains both subcategory filters (`FilterType="S"`) and brand filters (`FilterType="B"`), with IDs, display names, slugs, and item counts.

## Product fields available without a detail endpoint

The list responses already include full useful detail: stable item ID, external ID, slug, names, category/subcategory/brand IDs and names, unit, stock, regular price, discounted price, discount data, purchase limits, description HTML, image URL, tag image, and restricted-item metadata. The HAR did not contain a separate product-detail request, so the app should treat the normalized list record as the product detail source.

## Home sections discovered

The home response dynamically exposed offer tags such as Summer Items, Weekend Deals, Buy & Get Free, and others. Banner links use patterns such as `tag/{slug}`, `category/{slug}`, `subcategory/{slug}/{id}`, and `offer`. The scraper should discover these links from each response rather than hard-code campaign names.

## Endpoints intentionally excluded

- `POST /startup`: returns the signed-in user's profile and is unnecessary for catalog scraping.
- `GET /cart/items`: private cart data and unnecessary.
- `POST /areas/search`: not useful in this capture and not needed when area/subunit are configured.

## Architecture implication

GitHub Pages must never call this API directly because that would expose the bearer token and may encounter CORS restrictions. A scheduled GitHub Action should scrape server-side, normalize public product data, update compact static JSON and history shards, then deploy the frontend.
