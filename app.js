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

  // ✅ 백엔드가 이제 n/days/min/pages를 받아줌
  const url = `/api/rank?q=${encodeURIComponent(q)}&n=30&days=7&min=10&pages=10`;
  const res = await fetch(url);
  const data = await res.json();

  if (!res.ok) {
    out.innerHTML = `<tr><td colspan="6">에러: ${data.error || res.status}</td></tr>`;
    return;
  }

  // ✅ 백엔드가 500으로 내려준 detail도 화면에서 보이게
  if (data?.error && data?.detail) {
    out.innerHTML = `<tr><td colspan="6">에러: ${data.error}<br/>${JSON.stringify(data.detail).slice(0, 800)}</td></tr>`;
    return;
  }

  out.innerHTML = "";

  data.forEach((r, i) => {
    const weeklyViews = toInt(r.weeklyViews);
    const longVideos = toInt(r.longCount);
    const channel = r.channel || "-";
    const published = r.topVideoPublishedAt || "-";
    const title = r.topVideoTitle || "보기";
    const link = r.topVideoUrl || "";

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
