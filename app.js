const btn = document.getElementById("btn");
const out = document.getElementById("out");
const qInput = document.getElementById("q");

function toInt(v) {
  if (v === undefined || v === null) return 0;
  if (typeof v === "number") return Math.floor(v);
  const n = parseInt(String(v).replace(/[^\d]/g, ""), 10);
  return Number.isFinite(n) ? n : 0;
}

function comma(n) {
  return Number(n).toLocaleString("ko-KR");
}

btn.addEventListener("click", async () => {
  const q = (qInput?.value || "낚시").trim() || "낚시";
  out.innerHTML = `<tr><td colspan="6">불러오는 중...</td></tr>`;

  // ✅ TOP 50 / 최근7일 / 10분+ / search 2페이지(최대 100개 후보)
  const url = `/api/rank?q=${encodeURIComponent(q)}&limit=50&minSec=600&days=7&pages=2`;

  const res = await fetch(url);
  const data = await res.json();

  if (!res.ok) {
    const msg = data?.error || `HTTP ${res.status}`;
    out.innerHTML = `<tr><td colspan="6">에러: ${msg}</td></tr>`;
    return;
  }

  out.innerHTML = "";

  data.forEach((r, i) => {
    const weeklyViews = toInt(r.weeklyViews);
    const longVideos  = toInt(r.longCount);
    const channel     = r.channel || "-";
    const published   = r.topVideoPublishedAt || "-";
    const title       = r.topVideoTitle || "보기";
    const link        = r.topVideoUrl || "";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td>${channel}</td>
      <td>${comma(weeklyViews)}회</td>
      <td>${comma(longVideos)}</td>
      <td>${published}</td>
      <td>${link ? `<a href="${link}" target="_blank" rel="noopener">${title}</a>` : "-"}</td>
    `;
    out.appendChild(tr);
  });

  if (data.length === 0) {
    out.innerHTML = `<tr><td colspan="6">결과가 없습니다</td></tr>`;
  }
});
