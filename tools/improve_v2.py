async def api_improve(req):
    d = await req.json()
    idea = (d.get("prompt") or "").strip()
    if not idea:
        return web.json_response({"error": "Write an idea first"}, status=400)
    i2v = d.get("mode") == "i2v"
    system = IMPROVE_SYSTEM_I2V if i2v else IMPROVE_SYSTEM
    shape = {"9:16": "vertical 9:16 video for Reels/TikTok", "1:1": "square video"}.get(d.get("aspect"), "landscape video")
    user_text = f"Idea ({shape}): {idea}" + (" The attached photo is the first frame." if i2v else "")
    img = os.path.join(UPLOADS, os.path.basename(d["image"])) if i2v and d.get("image") else None
    if img and not os.path.exists(img):
        img = None

    now = time.time()
    cands = [(n, p, m, v) for n, p, m, v in LLM_MODELS
             if llm_key(p) and llm_health.get(f"{p}|{m}", {}).get("rest_until", 0) < now]
    cands.sort(key=lambda c: (-(1 if (img and c[3]) else 0), -health_score(c[0], f"{c[1]}|{c[2]}")))
    free = [c for c in cands if c[1] not in PAID_PROVIDERS]
    paid = [c for c in cands if c[1] in PAID_PROVIDERS] if paid_left() > 0 else []
    tried = []
    start = time.time()

    async def ask(c):
        n, p, m, v = c
        t0 = time.time()
        try:
            opts = parse_options(await call_cloud_llm(p, m, v, system, user_text, img))
            if not opts:
                raise RuntimeError("empty answer")
            health_record(f"{p}|{m}", True, time.time() - t0)
            log(f"improve: {n} answered in {time.time() - t0:.0f}s ({len(opts)} versions)")
            return c, opts
        except asyncio.CancelledError:
            raise
        except Exception as e:
            err = str(e)
            busy = any(x in err for x in ("429", "503", "rate", "overloaded", "Timeout", "timed out")) or not err
            health_record(f"{p}|{m}", False, rest=300 if busy else 60)
            tried.append(f"{n}: {(err or 'timed out')[:70]}")
            return c, None

    async def run_pool(pool, deadline):
        """Ask `pool` in waves; prefer a big model's answer over a small one (wait up to SMALL_GRACE for it)."""
        queue, tasks, best, best_at = list(pool), {}, None, 0
        while time.time() < deadline:
            launched = len(pool) - len(queue)
            if queue and (not tasks or time.time() - start >= WAVE_EVERY * launched / WAVE_SIZE):
                for c in queue[:WAVE_SIZE]:
                    tasks[asyncio.create_task(ask(c))] = c
                queue = queue[WAVE_SIZE:]
            if best and best[0][0] in LLM_SMALL and not any(c[0] not in LLM_SMALL for c in tasks.values()):
                for c in [c for c in queue if c[0] not in LLM_SMALL][:WAVE_SIZE]:
                    tasks[asyncio.create_task(ask(c))] = c
                    queue.remove(c)
            if not tasks:
                break
            done, _ = await asyncio.wait(list(tasks), timeout=1.0, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                c = tasks.pop(t)
                _, opts = t.result()
                if opts and (best is None or (best[0][0] in LLM_SMALL and c[0] not in LLM_SMALL)
                             or ((best[0][0] in LLM_SMALL) == (c[0] in LLM_SMALL) and len(opts) > len(best[1]))):
                    best, best_at = (c, opts), time.time()
            if best and len(best[1]) >= 3 and (best[0][0] not in LLM_SMALL or time.time() - best_at > SMALL_GRACE
                                               or all(c[0] in LLM_SMALL for c in tasks.values())):
                break
        for t in tasks:
            t.cancel()
        return best

    # 1) the free key; 2) only if it gave nothing at all, the paid key (capped per day)
    best = await run_pool(free, start + IMPROVE_DEADLINE) if free else None
    if not best and paid:
        log("improve: free key gave no answer, using the paid key")
        best = await run_pool(paid, time.time() + 45)
    if best:
        c, opts = best
        return web.json_response({"options": opts, "text": opts[0], "model": c[0], "saw_photo": bool(img and c[3]),
                                  "paid": c[1] in PAID_PROVIDERS, "seconds": round(time.time() - start)})
    return web.json_response({"offline": True, "error": "; ".join(tried)[:400]})
