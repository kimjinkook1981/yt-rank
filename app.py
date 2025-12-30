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

def iso_7days_ago():
    # 최근 7일
    dt = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    return dt.replace(microsecond=0).isoformat() + "Z"

def yt_search(q, page_token=None):
    # YouTube Data API: search.list
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": q,
        "type": "video",
        "maxResults": 50,
        "order": "viewCount",
        "publishedAfter": iso_7days_ago(),
        "key": YOUTUBE_API_KEY,
    }
    if page_token:
        params["pageToken"] = page_token

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def yt_videos(video_ids):
    # videos.list (통계+길이)
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,contentDetails,statistics",
        "id": ",".join(video_ids),
        "maxResults": 50,
        "key": YOUTUBE_API_KEY,
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def parse_duration_to_seconds(iso):
    # PT#H#M#S
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
    limit = int(request.args.get("limit") or "30")  # 기본 30위까지

    if not q:
        return jsonify({"error": "q parameter required"}), 400

    if not YOUTUBE_API_KEY:
        return jsonify({"error": "YOUTUBE_API_KEY is not set"}), 500

    # 1) 최근 7일 검색 결과에서 영상 ID 많이 수집 (조회수 높은 순으로)
    video_ids = []
    page_token = None
    for _ in range(6):  # 6*50 = 300개 정도 훑기(쿼터/속도 균형)
        data = yt_search(q, page_token=page_token)
        items = data.get("items", [])
        for it in items:
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

    # 2) videos.list로 통계/길이/업로드일 가져오기
    videos = []
    for i in range(0, len(uniq_ids), 50):
        chunk = uniq_ids[i:i+50]
        vdata = yt_videos(chunk)
        videos.extend(vdata.get("items", []))

    # 3) 10분 이상(>=600초)만 필터 → 채널별 주간 조회수 합산
    by_channel = {}  # channelId -> stats
    for v in videos:
        content = v.get("contentDetails", {})
        stats = v.get("statistics", {})
        snip = v.get("snippet", {})

        duration_sec = parse_duration_to_seconds(content.get("duration"))
        if duration_sec < 600:
            continue

        view_count = int(stats.get("viewCount") or 0)
        channel_id = snip.get("channelId")
        channel_title = snip.get("channelTitle") or ""
        video_title = snip.get("title") or ""
        published_at = snip.get("publishedAt") or ""
        video_id = v.get("id")

        if not channel_id:
            continue

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

        # 대표영상: 조회수 가장 높은 10분+ 영상
        if view_count > entry["topVideoViews"]:
            entry["topVideoViews"] = view_count
            entry["topVideoTitle"] = video_title
            entry["topVideoUrl"] = f"https://www.youtube.com/watch?v={video_id}"
            entry["topVideoPublishedAt"] = published_at

    # 4) 주간 합산조회수로 정렬해서 TOP limit
    rows = list(by_channel.values())
    rows.sort(key=lambda x: x["weeklyViews"], reverse=True)
    rows = rows[:limit]

    # 5) 출력 포맷 정리(프론트에서 쓰기 쉽게)
    result = []
    for idx, r in enumerate(rows, start=1):
        result.append({
            "rank": idx,
            "channel": r["channel"],
            "weeklyViews": r["weeklyViews"],
            "longCount": r["longCount"],
            "topVideoTitle": r["topVideoTitle"],
            "topVideoUrl": r["topVideoUrl"],
            "topVideoPublishedAt": r["topVideoPublishedAt"],
        })

    return jsonify(result)

if __name__ == "__main__":
    # 로컬에서는 5000, 배포(Render)는 PORT 환경변수 사용
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
