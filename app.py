import os
import datetime
import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.json.ensure_ascii = False

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()


@app.route("/")
def home():
    return render_template("index.html")


def iso_days_ago(days: int = 7) -> str:
    dt = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    return dt.replace(microsecond=0).isoformat() + "Z"


def yt_search(q: str, page_token: str | None = None) -> dict:
    # YouTube Data API: search.list
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": q,
        "type": "video",
        "maxResults": 50,
        "order": "viewCount",
        "publishedAfter": iso_days_ago(7),
        "key": YOUTUBE_API_KEY,
    }
    if page_token:
        params["pageToken"] = page_token

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def yt_videos(video_ids: list[str]) -> dict:
    # YouTube Data API: videos.list (통계+길이+snippet)
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
    # ISO 8601 duration 예: PT1H2M3S, PT15M, PT9M59S
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


@app.route("/api/rank", methods=["GET"])
def rank():
    q = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit") or "30")
    min_sec = int(request.args.get("minSec") or "600")  # 기본: 10분 이상

    if not q:
        return jsonify({"error": "q parameter required"}), 400

    if not YOUTUBE_API_KEY:
        return jsonify({"error": "YOUTUBE_API_KEY is not set"}), 500

    # 1) 최근 7일 검색 결과에서 videoId 수집
    video_ids = []
    page_token = None
    for _ in range(6):  # 최대 300개 정도
        data = yt_search(q, page_token=page_token)
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
        return jsonify([])

    # 2) videos.list로 상세 정보 가져오기
    videos = []
    for i in range(0, len(uniq_ids), 50):
        chunk = uniq_ids[i:i + 50]
        vdata = yt_videos(chunk)
        videos.extend(vdata.get("items", []))

    # 3) 길이(min_sec 이상)만 채널별 집계
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
        video_id = v.get("id")  # videos.list에서는 id가 문자열

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

        # 대표영상: viewCount 최대
        if view_count > entry["topVideoViews"]:
            entry["topVideoViews"] = view_count
            entry["topVideoTitle"] = video_title
            entry["topVideoUrl"] = f"https://www.youtube.com/watch?v={video_id}"
            entry["topVideoPublishedAt"] = published_at

    # 4) 정렬 TOP limit
    rows = list(by_channel.values())
    rows.sort(key=lambda x: x["weeklyViews"], reverse=True)
    rows = rows[:limit]

    # 5) 응답
    result = []
    for idx, r in enumerate(rows, start=1):
        # 날짜를 YYYY-MM-DD로 깔끔하게
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

    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
