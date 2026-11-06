# Checks node definitions on the live server.
import json, sys, urllib.request
url, key = sys.argv[1], sys.argv[2]
def get(p):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url + p, headers={"X-Key": key}), timeout=60).read())
for n in ["SaveVideo", "LoadVideo", "GetVideoComponents", "CreateVideo", "RIFE VFI", "Wan22ImageToVideoLatent", "ImageUpscaleWithModel", "UpscaleModelLoader"]:
    try:
        o = get("/g0/object_info/" + urllib.parse.quote(n))
        print(n, json.dumps(o.get(n, {}).get("input", {}))[:400])
    except Exception as e:
        print(n, "ERR", e)
print(get("/health")["gpus"])
