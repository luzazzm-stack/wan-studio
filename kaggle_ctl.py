"""Kaggle control for Wan Studio: push (start), delete (hard stop), status and GPU quota."""
import json, os, secrets, shutil, tempfile

HERE = os.environ.get("WAN_STUDIO_HOME") or os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("KAGGLE_API_TOKEN", open(os.path.join(HERE, "keys", "kaggle_luzamhjo_access_token.txt")).read().strip())
os.environ.setdefault("KAGGLE_CONFIG_DIR", os.path.join(HERE, "data", ".kaggle_cfg"))
os.makedirs(os.environ["KAGGLE_CONFIG_DIR"], exist_ok=True)

from kaggle.api.kaggle_api_extended import KaggleApi  # noqa: E402

USER = "luzamhjo"
SLUG = "wan-studio-server"
KERNEL = f"{USER}/{SLUG}"

_api = None


def api():
    global _api
    if _api is None:
        _api = KaggleApi()
        _api.authenticate()
    return _api


def push(key, topic, idle_min, max_hours):
    src = open(os.path.join(HERE, "kaggle", "wan_server.py"), encoding="utf-8").read()
    src = (src.replace("__KEY__", key).replace("__TOPIC__", topic)
              .replace("__IDLE_MIN__", str(int(idle_min))).replace("__MAX_HOURS__", str(float(max_hours))))
    d = tempfile.mkdtemp()
    try:
        open(os.path.join(d, "wan_server.py"), "w", encoding="utf-8").write(src)
        json.dump({"id": KERNEL, "title": "wan studio server", "code_file": "wan_server.py", "language": "python",
                   "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
                   "machine_shape": "NvidiaTeslaT4", "dataset_sources": [], "competition_sources": [], "kernel_sources": []},
                  open(os.path.join(d, "kernel-metadata.json"), "w"))
        r = api().kernels_push(d)
        if getattr(r, "error", None):
            raise RuntimeError(r.error)
        return {"version": r.version_number, "url": r.url}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def status():
    """Returns 'running', 'queued', 'complete', 'error', 'cancel...', or 'none' if the kernel doesn't exist."""
    try:
        r = api().kernels_status(KERNEL)
        s = str(getattr(r, "status", r)).lower()
        return s.split(".")[-1]
    except Exception as e:
        if any(s in str(e).lower() for s in ("404", "not found", "denied", "403")):
            return "none"
        raise


def delete():
    try:
        api().kernels_delete(KERNEL, no_confirm=True)
        return True
    except Exception as e:
        if any(s in str(e).lower() for s in ("404", "not found", "denied", "403")):
            return False
        raise


def quota():
    from kagglesdk.kernels.types.kernels_api_service import ApiGetAcceleratorQuotaStatisticsRequest
    with api().build_kaggle_client() as k:
        r = k.kernels.kernels_api_client.get_accelerator_quota_statistics(ApiGetAcceleratorQuotaStatisticsRequest())
    q = r.gpu_quota
    h = lambda td: round(td.total_seconds() / 3600, 2) if td else 0.0
    return {"used_h": h(q.time_used), "reserved_h": h(q.time_reserved), "total_h": h(q.total_time_allowed),
            "refresh": r.quota_refresh_time.isoformat() if r.quota_refresh_time else None}


def new_key():
    return secrets.token_urlsafe(24)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(status())
    elif cmd == "quota":
        print(quota())
    elif cmd == "delete":
        print(delete())
    elif cmd == "push":
        print(push(sys.argv[2], sys.argv[3], int(sys.argv[4]), float(sys.argv[5])))
