import hashlib, hmac, json

# Collect all sxsrf data from HAR
import base64
har = json.load(open('imrs.foodibd.com_2026_07_24_03_32_42.har', encoding='utf-8'))
entries = har['log']['entries']

def decode_sxsrf(raw):
    val = raw
    while True:
        try:
            return json.loads(val)
        except:
            try:
                val = base64.b64decode(val).decode('utf-8', errors='replace')
            except:
                return None

data = []
for e in entries:
    for h in e['request']['headers']:
        if h['name'] == 'sxsrf':
            d = decode_sxsrf(h['value'])
            if d and 'sign' in d:
                data.append(d)
            break

print("Got %d sxsrf entries" % len(data))
# Use first 3 for testing
test = data[:3]

# Try many more HMAC key candidates
keys_to_try = [
    b'', b'foodi', b'foodibd', b'ktor-client', b'ktor',
    b'foodi-prod-android', b'foodi-prod', b'prod-android',
    b'android', b'8.0.3', b'8.0', b'16',
    b'foodi-prod-android 8.0.3 16',
    b'foodi-prod-android 8.0.3 16 1b5a4567bbcb95d4',
    b'1b5a4567bbcb95d4',
    b'foodibd.com', b'api.foodibd.com', b'imrs.foodibd.com',
    b'x-requested-with', b'XMLHttpRequest',
    b'sxsrf', b'application/json',
    b'Foodi', b'FOODI', b'FOODIBD',
    b'foodibdus', b'foodibdusbangla',
    b'bangla', b'us-bangla', b'us_bangla',
    b'secret', b'key', b'token', b'sign',
    b'foodi-secret', b'foodibd-secret',
    b'foodi-key', b'foodibd-key',
]

for key in keys_to_try:
    all_match = True
    for d in test:
        # Build the JSON to sign
        to_sign = json.dumps({"expires": d["expires"], "random": d["random"]}, separators=(',', ':'))
        h = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
        if h != d["sign"]:
            all_match = False
            break
    if all_match:
        print("FOUND! key=%r" % key)
        break

    # Also try with str(random)
    all_match = True
    for d in test:
        to_sign = json.dumps({"expires": d["expires"], "random": str(d["random"])}, separators=(',', ':'))
        h = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
        if h != d["sign"]:
            all_match = False
            break
    if all_match:
        print("FOUND! key=%r (with str random)" % key)
        break

    # Also try including sign field as empty
    all_match = True
    for d in test:
        to_sign = json.dumps({"expires": d["expires"], "sign": "", "random": d["random"]}, separators=(',', ':'))
        h = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
        if h != d["sign"]:
            all_match = False
            break
    if all_match:
        print("FOUND! key=%r (with empty sign)" % key)
        break

    # Try SHA256(key + data) instead of HMAC
    all_match = True
    for d in test:
        to_sign = json.dumps({"expires": d["expires"], "random": d["random"]}, separators=(',', ':'))
        h = hashlib.sha256(key + to_sign.encode()).hexdigest()
        if h != d["sign"]:
            all_match = False
            break
    if all_match:
        print("FOUND! sha256(key+data) key=%r" % key)
        break

    all_match = True
    for d in test:
        to_sign = json.dumps({"expires": d["expires"], "random": d["random"]}, separators=(',', ':'))
        h = hashlib.sha256(to_sign.encode() + key).hexdigest()
        if h != d["sign"]:
            all_match = False
            break
    if all_match:
        print("FOUND! sha256(data+key) key=%r" % key)
        break

print("No match found with any key")

# Also check if the sign might be HMAC with the full JSON including sign as empty string, with various keys
# Try with different JSON formats
formats = [
    lambda d: json.dumps({"expires": d["expires"], "random": d["random"]}, separators=(',', ':')),
    lambda d: json.dumps({"expires": d["expires"], "random": d["random"]}),
    lambda d: json.dumps({"expires": d["expires"], "random": d["random"]}, sort_keys=True, separators=(',', ':')),
    lambda d: json.dumps({"sign": "", "random": d["random"], "expires": d["expires"]}, separators=(',', ':')),
    lambda d: "%d%s" % (d["expires"], d["random"]),
    lambda d: "%s%d" % (d["random"], d["expires"]),
    lambda d: str(d["random"]) + str(d["expires"]),
    lambda d: str(d["expires"]) + str(d["random"]),
]

for fmt_fn in formats:
    for key in keys_to_try:
        all_match = True
        for d in test:
            to_sign = fmt_fn(d)
            h = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
            if h != d["sign"]:
                all_match = False
                break
        if all_match:
            print("FOUND! key=%r fmt=%r" % (key, fmt_fn(test[0])))
            break
    else:
        continue
    break
else:
    print("Exhausted all combinations, no match")
