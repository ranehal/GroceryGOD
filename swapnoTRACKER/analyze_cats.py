import json

with open('response_store-api_shwapno_com__common_megamenutree.json') as f:
    data = json.load(f)

cats = data.get('data', [])

def extract_leaves(items, parent=''):
    leaves = []
    for item in items:
        title = item.get('title', '')
        url = item.get('url', '')
        children = item.get('childMenuItems', [])
        if children:
            leaves.extend(extract_leaves(children, parent=title))
        else:
            leaves.append({'title': title, 'url': url, 'parent': parent})
    return leaves

leaves = extract_leaves(cats)
print(f'Total leaf categories: {len(leaves)}')
for i, l in enumerate(leaves):
    print(f'  [{i}] {l["parent"]:35s} > {l["title"]:30s}  url={l["url"]}')
