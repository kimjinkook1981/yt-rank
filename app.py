import os
import time
import datetime
import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.json.ensure_ascii = False

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()

# =========================
# 간단 캐시 (같은 검색 반복 호출 방지)
# =========================
CACHE = {}  # key -> (expire_ts, data)

def cache_get(key: str):
    it = CACHE.get(key)
    if not it:
        return None
    exp, data = it
    if time.time() > exp:
        CACHE.pop(key, None)
        return None
    return data

def cache_set(key: str, data, ttl: int = 300):  # 기본 5분 캐시
    CACHE[key] = (time.time() + ttl, data)


@app.route("/")
def home():
    return render_template("index.html")


def iso_days_ago(days: int = 7) -> str:
    dt = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    return dt.replace(microsecond=0).isoformat() + "Z"


def yt_search(q: str, page_token: str | None = None, days: int = 7) -> dict:
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": q,
        "type": "video",
        "maxResults": 50,
        "order": "viewCount",
        "publishedAfter": iso_days_ago(days),
        "key": YOUTUBE_API_KEY,
    }
    if page_token:
        params["pageToken"] = page_token

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def yt_videos(video_ids: list[str]) -> dict:
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,contentDetails,statistics",
        "id": ",".join(video_ids),
        "key": YOUTUBE_API_KEY,
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def parse_duration_to_seconds(iso: str) -> int:
    if not iso or not iso.startswith("PT"):
        return 0
    iso = iso[2:]
    h = m = s = 0
    num = ""
    for ch in iso:
        if ch.isdigit():
            num += ch
        else:
            val = int(num) if num else 0
            if ch == "H":
                h = val
            elif ch == "M":
                m = val
            elif ch == "S":
                s = val
            num = ""
    return h * 3600 + m * 60 + s


def parse_google_error(resp_json: dict) -> dict:
    err = (resp_json or {}).get("error", {})
    errors = err.get("errors", []) or []
    reason = errors[0].get("reason") if errors else None
    message = err.get("message") or ""
    code = err.get("code") or 500
    return {"code": code, "reason": reason, "message": message}


@app.route("/api/rank", methods=["GET"])
def rank():
    q = (request.args.get("q") or "").strip()

    # ✅ 기본값: TOP 50
    limit = int(request.args.get("limit") or "50")

    # ✅ 기본값: 10분+
    min_sec = int(request.args.get("minSec") or "600")

    # ✅ 기본값: 최근 7일
    days = int(request.args.get("days") or "7")

    # ✅ 기본값: search 2페이지(=최대 100개 후보), 쿼터 보호
    pages = int(request.args.get("pages") or "2")
    pages = max(1, min(pages, 3))  # 최대 3페이지까지만 허용(쿼터 보호)

    if not q:
        return jsonify({"error": "q parameter required"}), 400

    if not YOUTUBE_API_KEY:
        return jsonify({"error": "YOUTUBE_API_KEY is not set"}), 500

    cache_key = f"rank:q={q}|limit={limit}|minSec={min_sec}|days={days}|pages={pages}"
    cached = cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)

    try:
        # 1) search로 videoId 수집 (pages 만큼만)
        video_ids = []
        page_token = None
        for _ in range(pages):
            data = yt_search(q, page_token=page_token, days=days)
            for it in data.get("items", []):
                vid = it.get("id", {}).get("videoId")
                if vid:
                    video_ids.append(vid)
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        # 중복 제거(순서 유지)
        seen = set()
        uniq_ids = []
        for vid in video_ids:
            if vid not in seen:
                seen.add(vid)
                uniq_ids.append(vid)

        if not uniq_ids:
            cache_set(cache_key, [], ttl=120)
            return jsonify([])

        # 2) videos.list로 상세 정보
        videos = []
        for i in range(0, len(uniq_ids), 50):
            chunk = uniq_ids[i:i + 50]
            vdata = yt_videos(chunk)
            videos.extend(vdata.get("items", []))

        # 3) 10분+만 채널별 합산
        by_channel = {}
        for v in videos:
            snip = v.get("snippet", {})
            stats = v.get("statistics", {})
            content = v.get("contentDetails", {})

            channel_id = snip.get("channelId")
            if not channel_id:
                continue

            duration_sec = parse_duration_to_seconds(content.get("duration") or "")
            if duration_sec < min_sec:
                continue

            view_count = int(stats.get("viewCount") or 0)
            channel_title = snip.get("channelTitle") or ""
            video_title = snip.get("title") or ""
            published_at = snip.get("publishedAt") or ""
            video_id = v.get("id")

            entry = by_channel.get(channel_id)
            if not entry:
                entry = {
                    "channelId": channel_id,
                    "channel": channel_title,
                    "weeklyViews": 0,
                    "longCount": 0,
                    "topVideoTitle": "",
                    "topVideoUrl": "",
                    "topVideoViews": -1,
                    "topVideoPublishedAt": "",
                }
                by_channel[channel_id] = entry

            entry["weeklyViews"] += view_count
            entry["longCount"] += 1

            if view_count > entry["topVideoViews"]:
                entry["topVideoViews"] = view_count
                entry["topVideoTitle"] = video_title
                entry["topVideoUrl"] = f"https://www.youtube.com/watch?v={video_id}"
                entry["topVideoPublishedAt"] = published_at

        # 4) 정렬 후 TOP limit
        rows = list(by_channel.values())
        rows.sort(key=lambda x: x["weeklyViews"], reverse=True)
        rows = rows[:limit]

        # 5) 응답
        result = []
        for idx, r in enumerate(rows, start=1):
            pub = (r["topVideoPublishedAt"] or "")
            pub_date = pub[:10] if len(pub) >= 10 else pub

            result.append({
                "rank": idx,
                "channel": r["channel"],
                "weeklyViews": r["weeklyViews"],
                "longCount": r["longCount"],
                "topVideoTitle": r["topVideoTitle"],
                "topVideoUrl": r["topVideoUrl"],
                "topVideoPublishedAt": pub_date,
            })

        cache_set(cache_key, result, ttl=300)
        return jsonify(result)

    except requests.exceptions.HTTPError as e:
        resp = getattr(e, "response", None)
        try:
            j = resp.json() if resp is not None else {}
        except Exception:
            j = {}

        info = parse_google_error(j)
        reason = info.get("reason")

        if reason == "quotaExceeded":
            return jsonify({
                "error": "할당량(Quota) 초과입니다. 잠시 후 또는 다음 날 다시 시도해 주세요.",
                "detail": info
            }), 429
        elif reason == "keyInvalid":
            return jsonify({
                "error": "API 키가 유효하지 않습니다. 키를 다시 확인해 주세요.",
                "detail": info
            }), 401
        else:
            return jsonify({
                "error": "YouTube API 오류가 발생했습니다.",
                "detail": info
            }), 500

    except Exception as e:
        return jsonify({"error": f"서버 오류: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
