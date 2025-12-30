const btn = document.getElementById("btn");
const out = document.getElementById("out");
const qInput = document.getElementById("q");

function comma(n) {
  return Number(n).toLocaleString("ko-KR");
}

btn.addEventListener("click", async () => {
  const q = (qInput?.value || "낚시").trim() || "낚시";

  out.innerHTML = `<tr><td colspan="5">불러오는 중...</td></tr>`;

  const res = await fetch(`/api/rank?q=${encodeURIComponent(q)}`);
  const rows = await res.json();

  out.innerHTML = "";

  rows.forEach((r, i) => {
    const weeklyViews = Number(r.weeklyViews || 0);
    const longVideos = Number(r.longVideos || 0);

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td>${r.channel || "-"}</td>
      <td>${comma(weeklyViews)}회</td>
      <td>${comma(longVideos)}</td>
      <td>${r.topVideoUrl ? `<a href="${r.topVideoUrl}" target="_blank">${r.topVideoTitle || "보기"}</a>` : "-"}</td>
    `;
    out.appendChild(tr);
  });

  if (rows.length === 0) {
    out.innerHTML = `<tr><td colspan="5">결과가 없습니다 (최근 7일 + 10분 이상 영상이 부족할 수 있음)</td></tr>`;
  }
});
