const fs = require("fs");
const https = require("https");
const path = require("path");

const htmlFile = path.resolve(__dirname, "..", "index.html");

const charts = [
  {
    id: "mb-chart-index",
    title: "米主要指数 1dayパフォーマンス",
    subtitle: "NASDAQ100 / S&P500 / DOW / Russell2000、前日終値 = 0%",
    range: "1d",
    interval: "5m",
    fallback: "https://finance.yahoo.com/quote/%5ENDX",
    series: [
      ["^NDX", "NASDAQ100", "NASDAQ100", "#2563eb", "pt"],
      ["^GSPC", "S&P500", "S&P500", "#facc15", "pt"],
      ["^DJI", "DOW", "Dow Jones", "#16a34a", "pt"],
      ["^RUT", "Russell2000", "Russell2000", "#f97316", "pt"],
    ],
  },
  {
    id: "mb-chart-qld-fang",
    title: "QLD / FANG+ 1dayパフォーマンス",
    subtitle: "レバナスとFANG+、前日終値 = 0%",
    range: "1d",
    interval: "5m",
    fallback: "https://finance.yahoo.com/quote/QLD",
    series: [
      ["QLD", "QLD", "レバナス", "#2563eb", "$"],
      ["^NYFANG", "FANG+", "NYSE FANG+", "#db2777", "pt"],
    ],
  },
  {
    id: "mb-chart-fang-top20",
    title: "レバナス FANG TOP20 年初来パフォーマンス",
    subtitle: "QLD / FANG+ / 2244、年初来",
    range: "ytd",
    interval: "1d",
    fallback: "https://finance.yahoo.com/quote/QLD",
    series: [
      ["QLD", "QLD", "レバナス", "#2563eb", "$"],
      ["^NYFANG", "FANG+", "NYSE FANG+", "#db2777", "pt"],
      ["2244.T", "2244", "FANG+ ETF", "#f97316", "円"],
    ],
  },
  {
    id: "mb-chart-tecl-soxl-webl",
    title: "TECL / SOXL / WEBL 1dayパフォーマンス",
    subtitle: "テック、半導体、ネット株、前日終値 = 0%",
    range: "1d",
    interval: "5m",
    fallback: "https://finance.yahoo.com/quote/TECL",
    series: [
      ["TECL", "TECL", "テック3倍", "#2563eb", "$"],
      ["SOXL", "SOXL", "半導体3倍", "#f97316", "$"],
      ["WEBL", "WEBL", "ネット3倍", "#16a34a", "$"],
    ],
  },
  {
    id: "mb-chart-tmf",
    title: "TMF 1dayパフォーマンス",
    subtitle: "長期金利の逆方向感を確認、前日終値 = 0%",
    range: "1d",
    interval: "5m",
    fallback: "https://finance.yahoo.com/quote/TMF",
    series: [["TMF", "TMF", "20年債3倍", "#2563eb", "$"]],
  },
  {
    id: "mb-chart-usdjpy",
    title: "ドル円 1dayパフォーマンス",
    subtitle: "USD/JPY、前日終値 = 0%",
    range: "1d",
    interval: "5m",
    fallback: "https://finance.yahoo.com/quote/JPY=X",
    series: [["USDJPY=X", "USD/JPY", "ドル円", "#16a34a", "円"]],
  },
  {
    id: "mb-chart-metals",
    title: "GOLD / Silver / Copper 1dayパフォーマンス",
    subtitle: "金、銀、銅、前日終値 = 0%",
    range: "1d",
    interval: "5m",
    fallback: "https://finance.yahoo.com/quote/GC=F",
    series: [
      ["GC=F", "GOLD", "金", "#facc15", "$"],
      ["SI=F", "Silver", "銀", "#94a3b8", "$"],
      ["HG=F", "Copper", "銅", "#c2410c", "$"],
    ],
  },
  {
    id: "mb-chart-bitcoin",
    title: "Bitcoin 1dayパフォーマンス",
    subtitle: "BTC-USD、前日終値 = 0%",
    range: "1d",
    interval: "5m",
    fallback: "https://finance.yahoo.com/quote/BTC-USD",
    series: [["BTC-USD", "BTC", "Bitcoin", "#f97316", "$"]],
  },
  {
    id: "mb-chart-riot-mara",
    title: "RIOT / MARA 1dayパフォーマンス",
    subtitle: "ビットコイン関連株、前日終値 = 0%",
    range: "1d",
    interval: "5m",
    fallback: "https://finance.yahoo.com/quote/RIOT",
    series: [
      ["RIOT", "RIOT", "Riot", "#2563eb", "$"],
      ["MARA", "MARA", "MARA", "#f97316", "$"],
    ],
  },
  {
    id: "mb-chart-cweb",
    title: "CWEB 1dayパフォーマンス",
    subtitle: "中国ネット株、前日終値 = 0%",
    range: "1d",
    interval: "5m",
    fallback: "https://finance.yahoo.com/quote/CWEB",
    series: [["CWEB", "CWEB", "中国ネット2倍", "#dc2626", "$"]],
  },
];

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fetchJson(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(
      url,
      {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
          Accept: "application/json,text/plain,*/*",
        },
      },
      (res) => {
        let body = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => (body += chunk));
        res.on("end", () => {
          if (res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`HTTP ${res.statusCode}: ${body.slice(0, 120)}`));
            return;
          }
          resolve(JSON.parse(body));
        });
      }
    );
    req.setTimeout(20000, () => req.destroy(new Error("request timeout")));
    req.on("error", reject);
  });
}

function jstParts(timestamp, range) {
  const opts =
    range === "ytd"
      ? { timeZone: "Asia/Tokyo", month: "2-digit", day: "2-digit" }
      : {
          timeZone: "Asia/Tokyo",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        };
  const parts = new Intl.DateTimeFormat("ja-JP", opts).formatToParts(
    new Date(timestamp * 1000)
  );
  const get = (type) => parts.find((part) => part.type === type)?.value || "";
  if (range === "ytd") return `${get("month")}/${get("day")}`;
  return `${get("month")}/${get("day")} ${get("hour")}:${get("minute")}`;
}

async function fetchSeries([symbol, label, name, color, unit], chart) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(
    symbol
  )}?range=${chart.range}&interval=${chart.interval}`;
  const json = await fetchJson(url);
  const result = json.chart?.result?.[0];
  const timestamps = result?.timestamp || [];
  const closes = result?.indicators?.quote?.[0]?.close || [];
  const points = timestamps
    .map((timestamp, index) => ({ timestamp, close: closes[index] }))
    .filter((point) => Number.isFinite(point.close));
  if (points.length < 2) throw new Error(`No chart points for ${symbol}`);
  const previousClose = result?.meta?.chartPreviousClose;
  const first =
    chart.range === "1d" && Number.isFinite(previousClose)
      ? previousClose
      : points[0].close;
  return {
    symbol,
    label,
    name,
    color,
    unit,
    latest: Number.isFinite(result?.meta?.regularMarketPrice)
      ? result.meta.regularMarketPrice
      : points[points.length - 1].close,
    startLabel: jstParts(points[0].timestamp, chart.range),
    endLabel: jstParts(points[points.length - 1].timestamp, chart.range),
    points: points.map((point) => ({
      label: jstParts(point.timestamp, chart.range),
      pct: ((point.close / first) - 1) * 100,
    })),
  };
}

function niceBounds(values) {
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const spread = Math.max(max - min, 1);
  const pad = Math.max(spread * 0.18, 0.4);
  const lo = Math.floor((min - pad) * 2) / 2;
  const hi = Math.ceil((max + pad) * 2) / 2;
  return { lo, hi: hi <= lo ? lo + 1 : hi };
}

function formatPct(value) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatLatest(value, unit, symbol) {
  if (symbol === "USDJPY=X") {
    return `${value.toLocaleString("ja-JP", {
      minimumFractionDigits: 3,
      maximumFractionDigits: 3,
    })}円`;
  }
  if (unit === "円") {
    return `${value.toLocaleString("ja-JP", {
      maximumFractionDigits: 2,
    })}円`;
  }
  if (unit === "pt") return `${Math.round(value).toLocaleString("ja-JP")} pt`;
  if (value >= 1000) return `$${Math.round(value).toLocaleString("en-US")}`;
  return `$${value.toFixed(2)}`;
}

function labelSlots(rows, y, plot) {
  const minGap = 34;
  const minY = plot.y + 12;
  const maxY = plot.y + plot.h - 12;
  const slots = rows
    .map((row) => {
      const last = row.points[row.points.length - 1];
      return { row, last, rawY: y(last.pct), labelY: y(last.pct) };
    })
    .sort((a, b) => a.rawY - b.rawY);

  for (let i = 0; i < slots.length; i += 1) {
    slots[i].labelY =
      i === 0 ? Math.max(slots[i].rawY, minY) : Math.max(slots[i].rawY, slots[i - 1].labelY + minGap);
  }

  const overflow = slots.length ? slots[slots.length - 1].labelY - maxY : 0;
  if (overflow > 0) {
    for (const slot of slots) slot.labelY -= overflow;
  }

  for (let i = slots.length - 2; i >= 0; i -= 1) {
    slots[i].labelY = Math.min(slots[i].labelY, slots[i + 1].labelY - minGap);
  }

  const underflow = slots.length ? minY - slots[0].labelY : 0;
  if (underflow > 0) {
    for (const slot of slots) slot.labelY += underflow;
  }

  return new Map(slots.map((slot) => [slot.row.symbol, slot]));
}

function buildSvg(chart, rows, stamp) {
  const width = 1160;
  const height = 650;
  const plot = { x: 72, y: 148, w: 820, h: 434 };
  const values = rows.flatMap((row) => row.points.map((point) => point.pct));
  const { lo, hi } = niceBounds(values);
  const y = (value) => plot.y + ((hi - value) / (hi - lo)) * plot.h;
  const x = (index, length) =>
    plot.x + (length <= 1 ? 0 : (index / (length - 1)) * plot.w);
  const gridValues = Array.from({ length: 6 }, (_, i) => lo + ((hi - lo) / 5) * i);
  const grid = gridValues
    .map((value) => {
      const yy = y(value);
      const label = `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
      return `<line x1="${plot.x}" y1="${yy.toFixed(1)}" x2="${plot.x + plot.w}" y2="${yy.toFixed(1)}" stroke="#e5e7eb" stroke-width="1"></line>
<text x="18" y="${(yy + 5).toFixed(1)}" fill="#64748b" font-size="13" font-weight="700" font-family="-apple-system,BlinkMacSystemFont,Hiragino Sans,Yu Gothic,Meiryo,sans-serif">${label}</text>`;
    })
    .join("\n");
  const zeroLine =
    lo <= 0 && hi >= 0
      ? `<line x1="${plot.x}" y1="${y(0).toFixed(1)}" x2="${plot.x + plot.w}" y2="${y(0).toFixed(1)}" stroke="#94a3b8" stroke-width="1.5"></line>`
      : "";
  const valueChips = rows
    .map((row, index) => {
      const col = index % 4;
      const chipX = 72 + col * 250;
      const chipY = 104 + Math.floor(index / 4) * 31;
      const last = row.points[row.points.length - 1];
      return `<rect x="${chipX}" y="${chipY}" width="236" height="25" rx="8" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1"></rect>
<circle cx="${chipX + 14}" cy="${chipY + 12.5}" r="5" fill="${row.color}"></circle>
<text x="${chipX + 27}" y="${chipY + 17}" fill="#111827" font-size="13" font-weight="900" font-family="-apple-system,BlinkMacSystemFont,Hiragino Sans,Yu Gothic,Meiryo,sans-serif">${escapeHtml(row.label)} ${escapeHtml(formatLatest(row.latest, row.unit, row.symbol))} / ${escapeHtml(formatPct(last.pct))}</text>`;
    })
    .join("\n");
  const slots = labelSlots(rows, y, plot);
  const lines = rows
    .map((row) => {
      const d = row.points
        .map((point, index) => `${index === 0 ? "M" : "L"}${x(index, row.points.length).toFixed(1)} ${y(point.pct).toFixed(1)}`)
        .join(" ");
      const last = row.points[row.points.length - 1];
      const lx = plot.x + plot.w + 28;
      const ly = y(last.pct);
      const slot = slots.get(row.symbol);
      const labelY = slot ? slot.labelY : ly;
      const leaderStartX = plot.x + plot.w + 6;
      const leaderMidX = lx - 12;
      return `<path d="${d}" fill="none" stroke="${row.color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M${leaderStartX} ${ly.toFixed(1)} H${leaderMidX} V${labelY.toFixed(1)} H${lx - 5}" fill="none" stroke="${row.color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<rect x="${lx}" y="${(labelY - 14).toFixed(1)}" width="154" height="27" rx="7" fill="${row.color}"></rect>
<text x="${lx + 8}" y="${(labelY + 4).toFixed(1)}" fill="#ffffff" font-size="13" font-weight="900" font-family="-apple-system,BlinkMacSystemFont,Hiragino Sans,Yu Gothic,Meiryo,sans-serif">${escapeHtml(row.label)} ${escapeHtml(formatPct(last.pct))}</text>`;
    })
    .join("\n");
  const legend = rows
    .map((row, index) => {
      const lx = 72 + index * 210;
      return `<rect x="${lx}" y="616" width="14" height="14" rx="3" fill="${row.color}"></rect>
<text x="${lx + 22}" y="628" fill="#111827" font-size="13" font-weight="900" font-family="-apple-system,BlinkMacSystemFont,Hiragino Sans,Yu Gothic,Meiryo,sans-serif">${escapeHtml(row.label)} / ${escapeHtml(row.name)}</text>`;
    })
    .join("\n");
  const firstLabel = rows[0]?.startLabel || "";
  const lastLabel = rows[0]?.endLabel || "";
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(chart.title)}" style="display:block;width:100%;height:auto;min-height:620px;background:#ffffff;border-radius:14px;">
<rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff"></rect>
<text x="72" y="34" fill="#111827" font-size="24" font-weight="900" font-family="-apple-system,BlinkMacSystemFont,Hiragino Sans,Yu Gothic,Meiryo,sans-serif">${escapeHtml(chart.title)}</text>
<text x="72" y="60" fill="#64748b" font-size="15" font-weight="800" font-family="-apple-system,BlinkMacSystemFont,Hiragino Sans,Yu Gothic,Meiryo,sans-serif">${escapeHtml(chart.subtitle)}</text>
<text x="768" y="34" fill="#64748b" font-size="12" font-weight="800" font-family="-apple-system,BlinkMacSystemFont,Hiragino Sans,Yu Gothic,Meiryo,sans-serif">データ取得 ${escapeHtml(stamp)} JST</text>
<text x="72" y="91" fill="#111827" font-size="14" font-weight="900" font-family="-apple-system,BlinkMacSystemFont,Hiragino Sans,Yu Gothic,Meiryo,sans-serif">取得時の価格</text>
${valueChips}
${grid}
${zeroLine}
${lines}
${legend}
<text x="72" y="600" fill="#64748b" font-size="12" font-weight="700" font-family="-apple-system,BlinkMacSystemFont,Hiragino Sans,Yu Gothic,Meiryo,sans-serif">${escapeHtml(firstLabel)}</text>
<text x="820" y="600" fill="#64748b" font-size="12" font-weight="700" font-family="-apple-system,BlinkMacSystemFont,Hiragino Sans,Yu Gothic,Meiryo,sans-serif">${escapeHtml(lastLabel)}</text>
</svg>`;
}

function popupSection(chart, svg, stamp) {
  return `<section id="${chart.id}" class="market-board-popup">
  <div class="market-board-popup-panel">
    <div class="market-board-popup-header">
      <span>${escapeHtml(chart.title)}</span>
      <a href="#market-board-top" class="market-board-popup-close">閉じる</a>
    </div>
    <div class="market-board-popup-body">
      <div style="min-height:650px;background:#ffffff;color:#111827;padding:14px;box-sizing:border-box;">
        ${svg}
        <div style="padding:10px 4px 0;color:#64748b;font-size:13px;font-weight:800;">外部埋め込みではなく、Yahoo Financeの価格データから生成した画像です。取得確認 ${escapeHtml(stamp)} JST</div>
      </div>
    </div>
  </div>
</section>`;
}

function heatmapSection(stamp) {
  return `<section id="mb-chart-heatmap" class="market-board-popup">
  <div class="market-board-popup-panel">
    <div class="market-board-popup-header">
      <span>ヒートマップ</span>
      <a href="#market-board-top" class="market-board-popup-close">閉じる</a>
    </div>
    <div class="market-board-popup-body">
      <div style="min-height:650px;background:#ffffff;color:#111827;padding:28px;box-sizing:border-box;">
        <h3 style="margin:0 0 14px;color:#111827;font-size:28px;line-height:1.35;font-weight:900;">ヒートマップ</h3>
        <p style="margin:0 0 18px;color:#374151;font-size:18px;line-height:1.8;font-weight:800;">ヒートマップは外部サイト側が埋め込み表示を制限するため、ポップアップではリンクを開く方式にしています。</p>
        <a href="https://finviz.com/map.ashx" target="_blank" rel="noopener noreferrer" style="display:inline-block;background:#facc15;color:#111827;border-radius:12px;padding:12px 16px;font-size:16px;font-weight:900;text-decoration:none;">ヒートマップを開く</a>
        <div style="margin-top:18px;color:#64748b;font-size:13px;font-weight:800;">確認 ${escapeHtml(stamp)} JST</div>
      </div>
    </div>
  </div>
</section>`;
}

async function main() {
  const now = new Date();
  const stamp = new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
    .format(now)
    .replace(/\//g, "/");
  const sections = new Map();
  for (const chart of charts) {
    const rows = await Promise.all(chart.series.map((series) => fetchSeries(series, chart)));
    sections.set(chart.id, popupSection(chart, buildSvg(chart, rows, stamp), stamp));
  }
  sections.set("mb-chart-heatmap", heatmapSection(stamp));

  let html = fs.readFileSync(htmlFile, "utf8");
  for (const [id, section] of sections) {
    const re = new RegExp(`<section id="${id}" class="market-board-popup">[\\s\\S]*?<\\/section>`);
    if (!re.test(html)) throw new Error(`Missing popup section: ${id}`);
    html = html.replace(re, section);
  }

  const yahooLinks = new Map([
    ["https://www.google.com/finance/quote/QLD:NYSEARCA?hl=ja&window=1D&comparison=INDEXNYSEGIS%3ANYFANG", "https://finance.yahoo.com/quote/QLD"],
    ["https://www.google.com/finance/quote/QLD:NYSEARCA?hl=ja&window=YTD&comparison=INDEXNYSEGIS%3AFANGST%2CTYO%3A2244", "https://finance.yahoo.com/quote/QLD"],
    ["https://www.google.com/finance/quote/TECL:NYSEARCA?hl=ja&window=1D&comparison=NYSEARCA%3ASOXL%2CNYSEARCA%3AWEBL", "https://finance.yahoo.com/quote/TECL"],
    ["https://www.google.com/finance/quote/TMF:NYSEARCA?hl=ja&window=1D", "https://finance.yahoo.com/quote/TMF"],
    ["https://www.google.com/finance/quote/USD-JPY?hl=ja&window=1D", "https://finance.yahoo.com/quote/JPY=X"],
    ["https://www.google.com/finance/quote/GCW00:COMEX?hl=ja&window=1D&comparison=COMEX%3ASIW00%2CCOMEX%3AHGW00", "https://finance.yahoo.com/quote/GC=F"],
    ["https://www.google.com/finance/quote/BTC-USD?hl=ja&window=1D", "https://finance.yahoo.com/quote/BTC-USD"],
    ["https://www.google.com/finance/quote/RIOT:NASDAQ?hl=ja&window=1D&comparison=NASDAQ%3AMARA", "https://finance.yahoo.com/quote/RIOT"],
    ["https://www.google.com/finance/quote/CWEB:NYSEARCA?hl=ja&window=1D", "https://finance.yahoo.com/quote/CWEB"],
  ]);
  for (const [from, to] of yahooLinks) {
    html = html.split(from).join(to);
  }

  fs.writeFileSync(htmlFile, html, "utf8");
  console.log(`Rebuilt ${charts.length} popup SVG charts and heatmap fallback at ${stamp} JST.`);
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
