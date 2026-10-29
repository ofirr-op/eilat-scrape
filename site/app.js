/* Club Hotel Eilat price calendar. Data comes from data.json, built by scrape.site_data. */
(function () {
  const WEEKDAYS = ["א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳"];
  const LONG_PRESS_MS = 350;
  const PRESS_MOVE_PX = 10;
  const BLUE = "#1d6fd6";
  const RED = "#d1263d";

  let data = null;
  let pinned = null;
  let pressTimer = null;
  let pressStart = null;
  let pressFiredFor = null;
  let touchDay = null;
  let hideTimer = null;

  const $ = (id) => document.getElementById(id);

  function fmt(n) {
    return Math.round(n).toLocaleString("en-US");
  }

  function pad(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function dmy(date) {
    return date.slice(8, 10) + "/" + date.slice(5, 7) + "/" + date.slice(2, 4);
  }

  function dmyFull(date) {
    return date.slice(8, 10) + "/" + date.slice(5, 7) + "/" + date.slice(0, 4);
  }

  function addDays(date, n) {
    const p = date.split("-").map(Number);
    const o = new Date(Date.UTC(p[0], p[1] - 1, p[2] + n));
    return o.getUTCFullYear() + "-" + pad(o.getUTCMonth() + 1) + "-" + pad(o.getUTCDate());
  }

  function state() {
    return {
      party: $("party").value || "2a3c",
      nights: $("nights").value || "3",
      board: $("board").value || "RO",
      rooms: $("rooms").value || "1",
    };
  }

  function offerKey(s) {
    return s.party + "|" + s.nights + "|" + s.board + "|" + s.rooms;
  }

  function offersFor(s) {
    return (data.offers[offerKey(s)] || []).slice();
  }

  function points(s, date, promo) {
    const block = data.history[offerKey(s)];
    if (!block || !block[date] || !block[date][promo]) return [];
    return block[date][promo];
  }

  function gridId(party, useMhot) {
    return party + (useMhot ? "-mhot" : "");
  }

  function trend(party, useMhot, s, date) {
    const scans = (data.scans && data.scans[gridId(party, useMhot)]) || [];
    if (scans.length < 2) return null;
    const prevScan = scans[scans.length - 2];
    const lastScan = scans[scans.length - 1];
    const series = points(s, date, useMhot ? "mhot" : "none");
    const prev = series.find((p) => p.at === prevScan.at);
    const last = series.find((p) => p.at === lastScan.at);
    if (!prev || !last || prev.price == null || last.price == null) return null;
    const delta = last.price - prev.price;
    const kind = Math.abs(delta) < 0.5 ? "flat" : delta > 0 ? "up" : "down";
    return { kind, delta, prevLabel: prevScan.label };
  }

  function cheapest(list) {
    let best = null;
    for (const row of list) {
      if (!best || row.total < best.total || (row.total === best.total && row.date < best.date)) best = row;
    }
    return best;
  }

  function heatColor(t) {
    const hue = 142 - Math.max(0, Math.min(1, t)) * 142;
    return "hsl(" + hue + " 62% 38%)";
  }

  function fillFilters() {
    const party = $("party");
    party.innerHTML = data.parties.map((p) =>
      '<option value="' + p.id + '">' + p.label + "</option>"
    ).join("");
    const board = $("board");
    board.innerHTML = data.boards.map((b) =>
      '<option value="' + b.id + '"' + (b.id === "RO" ? " selected" : "") + ">" + b.label + "</option>"
    ).join("");
  }

  function renderStatus() {
    const status = data.status || {};
    const grids = status.grids || {};
    let banner = "";
    if (status.run_state === "running") {
      const clock = status.started_clock ? " – התחילה ב־" + status.started_clock : "";
      const note = status.note ? " " + status.note : "";
      const from = lastFinishedLabel();
      banner = '<div class="banner" role="status">סריקה רצה עכשיו' + clock + note +
        ". המחירים בעמוד עדיין מהסריקה הקודמת" + (from ? " (" + from + ")" : "") + ".</div>";
    } else if (status.run_state === "failed") {
      banner = '<div class="banner failed" role="status">הסריקה האחרונה נכשלה' +
        (status.error ? ": " + escapeText(status.error) : "") +
        ". המחירים בעמוד הם מהסריקה הקודמת.</div>";
    }
    const rows = Object.keys(grids).map((id) => {
      const g = grids[id];
      const running = g.state === "running";
      const failed = g.state === "failed";
      const badge = running
        ? "רצה עכשיו" + (status.started_clock ? " · מ־" + status.started_clock : "")
        : failed ? "נכשלה" : "";
      const finished = !running && !failed && !!g.last_scan_label;
      const barClass = running ? "bar running" : finished ? "bar done" : "bar";
      const width = finished ? ' style="width:100%"' : "";
      const detail = failed && g.error
        ? escapeText(g.error)
        : g.last_scan_label
          ? "סריקה אחרונה: " + g.last_scan_label + " (שעון ישראל)"
          : "אין עדיין סריקה";
      return '<div class="grid-row"><div class="grid-top"><span><strong>' + g.label + "</strong>" +
        (badge ? '<span class="badge' + (failed ? " failed" : "") + '">' + badge + "</span>" : "") +
        '</span><span class="caption">' + (running ? "רצה עכשיו" : failed ? "נכשלה" : finished ? "הושלמה" : "אין סריקה") +
        '</span></div><div class="' + barClass + '" role="progressbar"><span' + width + '></span></div>' +
        '<div class="hint">' + detail + "</div></div>";
    }).join("");
    $("status").innerHTML = "<h2>מצב הסריקה</h2>" + banner + '<div class="grid-status">' + rows + "</div>";
  }

  function lastFinishedLabel() {
    const grids = (data.status && data.status.grids) || {};
    let best = "";
    for (const id of Object.keys(grids)) {
      const label = grids[id].last_scan_date || "";
      if (label > best) best = label;
    }
    return best;
  }

  function renderBest(s, rows) {
    const best = cheapest(rows);
    const boardLabel = data.boards.find((b) => b.id === s.board).label;
    const partyLabel = data.parties.find((p) => p.id === s.party).label;
    if (!best) {
      $("best").innerHTML = "<h2>ההצעה הזולה ביותר</h2><p>לא נמצאה זמינות לשילוב הזה.</p>";
      return;
    }
    const room = best.use_mhot ? best.room_mhot : best.room_none;
    const chosen = best.use_mhot
      ? "עם קוד mhot (הזול מהשניים); הקישור נפתח עם הקוד"
      : best.mhot != null
        ? "מחיר רגיל (הזול מהשניים); הקישור נפתח בלי קוד"
        : "מחיר רגיל (אין מחיר עם קוד בתאריך הזה); הקישור נפתח בלי קוד";
    const split = Number(s.rooms) === 2
      ? "<div><dt>פיצול החדרים</dt><dd>" + data.splits[s.party] + "</dd></div>"
      : "";
    $("best").innerHTML = "<h2>ההצעה הזולה ביותר</h2><dl class=\"props\">" +
      "<div><dt>" + s.nights + " לילות, " + boardLabel + ", " + (s.rooms === "1" ? "חדר אחד" : "2 חדרים") +
      "</dt><dd><a href=\"" + best.url + "\" target=\"_blank\" rel=\"noopener noreferrer\">" +
      fmt(best.total) + " ₪ בסך הכל (" + fmt(best.per_night) + " ללילה), " + dmy(best.date) + " → " +
      dmy(addDays(best.date, Number(s.nights))) + "</a></dd></div>" +
      "<div><dt>מחיר רגיל</dt><dd>" + priceText(best.none, best.room_none) + "</dd></div>" +
      "<div><dt>עם קוד mhot</dt><dd>" + priceText(best.mhot, best.room_mhot) + "</dd></div>" +
      "<div><dt>המחיר שנבחר</dt><dd>" + chosen + "</dd></div>" +
      "<div><dt>" + (s.rooms === "1" ? "חדר" : "חדרים") + "</dt><dd>" + (room || "—") + "</dd></div>" +
      split +
      "<div><dt>הרכב המשפחה</dt><dd>" + partyLabel + "</dd></div>" +
      "<div><dt>תאריכי כניסה עם זמינות</dt><dd>" + rows.length + "</dd></div></dl>";
  }

  function priceText(value, room) {
    if (value == null) return "לא זמין";
    return fmt(value) + " ₪" + (room ? " (" + room + ")" : "");
  }

  function renderTop(s, rows) {
    const from = $("from") ? $("from").value : (data.window.first || "");
    const to = $("to") ? $("to").value : (data.window.last || "");
    const invalid = from && to && from > to;
    const rangeFrom = invalid || !from ? data.window.first : from;
    const rangeTo = invalid || !to ? data.window.last : to;
    const inRange = rows.filter((row) => row.date >= rangeFrom && row.date <= rangeTo);
    const top = inRange.slice().sort((a, b) => a.total - b.total || (a.date < b.date ? -1 : 1)).slice(0, 10);
    const count = inRange.length;
    const countText = count === 0 ? "לא נמצאו תוצאות" : count === 1 ? "נמצאה תוצאה אחת בלבד" :
      count < 10 ? "נמצאו רק " + count + " תוצאות" : "מוצגות 10 הזולות מבין " + count + " תוצאות";
    const two = s.rooms === "2";
    const head = "<tr><th>תאריכים</th><th class=\"num\">סה״כ ₪</th><th class=\"num\">ללילה</th><th class=\"num\">רגיל</th><th class=\"num\">mhot</th><th>נבחר</th><th>חדר</th>" +
      (two ? "<th>פיצול</th>" : "") + "<th></th></tr>";
    const body = top.map((row) => {
      const room = row.use_mhot ? row.room_mhot : row.room_none;
      const used = row.use_mhot ? "עם קוד" : "רגיל";
      return "<tr><td>" + dmy(row.date) + " → " + dmy(addDays(row.date, Number(s.nights))) +
        "</td><td class=\"num\">" + fmt(row.total) + "</td><td class=\"num\">" + fmt(row.per_night) +
        "</td><td class=\"num\">" + (row.none == null ? "—" : fmt(row.none)) +
        "</td><td class=\"num\">" + (row.mhot == null ? "—" : fmt(row.mhot)) +
        "</td><td>" + used + "</td><td>" + (room || "—") + "</td>" +
        (two ? "<td>" + data.splits[s.party] + "</td>" : "") +
        "<td><a href=\"" + row.url + "\" target=\"_blank\" rel=\"noopener noreferrer\">להזמנה</a></td></tr>";
    }).join("");
    $("top").innerHTML = "<h2>עשרת טווחי התאריכים הזולים ביותר</h2>" +
      '<p class="caption">תאריכי כניסה מ־' + dmyFull(rangeFrom || "") + " עד " + dmyFull(rangeTo || "") + " · " + countText + "</p>" +
      '<div class="range-row"><label>מתאריך<input type="date" id="from" value="' + (from || "") + '" min="' + (data.window.first || "") + '" max="' + (data.window.last || "") + '"></label>' +
      '<label>עד תאריך<input type="date" id="to" value="' + (to || "") + '" min="' + (data.window.first || "") + '" max="' + (data.window.last || "") + '"></label>' +
      '<button type="button" id="reset">איפוס</button></div>' +
      (invalid ? '<p class="warn">תאריך ההתחלה מאוחר מתאריך הסיום, לכן מוצג כל הטווח.</p>' : "") +
      '<p class="hint">הטווח מסנן לפי תאריך הכניסה. הקישור נפתח עם הקוד רק כשהמחיר איתו זול יותר.</p>' +
      (top.length ? '<div class="table-wrap"><table>' + head + body + "</table></div>" : "<p>לא נמצאו הצעות בטווח הזה.</p>");
    $("from").addEventListener("change", refresh);
    $("to").addEventListener("change", refresh);
    $("reset").addEventListener("click", () => {
      $("from").value = data.window.first || "";
      $("to").value = data.window.last || "";
      refresh();
    });
  }

  function renderBars(rows) {
    const points = [];
    for (const month of data.months) {
      const best = cheapest(rows.filter((row) => row.date.slice(0, 7) === month.key));
      if (best) points.push({ label: month.short, value: best.total, display: fmt(best.total) + " ₪" });
    }
    if (!points.length) {
      $("bars").hidden = true;
      return;
    }
    $("bars").hidden = false;
    const min = Math.min(...points.map((p) => p.value));
    const max = Math.max(...points.map((p) => p.value));
    const bestIdx = points.reduce((bi, p, i) => p.value < points[bi].value ? i : bi, 0);
    $("bars").innerHTML = "<h2>המחיר הזול ביותר לפי חודש כניסה</h2><div class=\"month-bars\">" +
      points.map((p, i) => {
        const t = max === min ? 1 : (p.value - min) / (max - min);
        const width = 18 + (1 - t) * 82;
        return '<div class="month-bar' + (i === bestIdx ? " best" : "") + '"><span>' + p.label +
          '</span><i style="width:' + width + '%"></i><strong>' + p.display + "</strong></div>";
      }).join("") + "</div>";
  }

  function renderMatrix(s) {
    const body = ["2", "3", "4"].map((nights) => ["1", "2"].map((rooms) => {
      const cells = data.boards.map((board) => {
        const list = data.offers[s.party + "|" + nights + "|" + board.id + "|" + rooms] || [];
        const best = cheapest(list);
        if (!best) return "אין זמינות";
        return fmt(best.total) + (best.use_mhot ? " (עם קוד, " : " (") + dmy(best.date) + ")";
      });
      return "<tr><td>" + nights + " לילות, " + (rooms === "1" ? "חדר אחד" : "2 חדרים") + "</td>" +
        cells.map((cell) => '<td class="num">' + cell + "</td>").join("") + "</tr>";
    }).join("")).join("");
    $("matrix").innerHTML = "<h2>הזול ביותר בכל שילוב</h2><div class=\"table-wrap\"><table><tr><th>שילוב</th>" +
      data.boards.map((b) => "<th class=\"num\">" + b.label + "</th>").join("") + "</tr>" + body + "</table></div>";
  }

  function renderAbout() {
    const grids = (data.status && data.status.grids) || {};
    const bits = Object.keys(grids).map((id) => {
      const g = grids[id];
      return g.last_scan_label ? g.label + " " + g.last_scan_label : null;
    }).filter(Boolean);
    const windowText = data.window.first
      ? "תאריכי כניסה מ־" + dmyFull(data.window.first) + " עד " + dmyFull(data.window.last)
      : "אין עדיין חלון סריקה";
    $("summary").textContent = "המחיר הזול לכל יום כניסה במועדון הוטלס אילת, מבין המחיר הרגיל והמחיר עם קוד mhot. " + windowText + ".";
    $("about").innerHTML = "<h2>על הנתונים</h2><p>" + windowText + ". " +
      "המחירים הם התעריפים הפומביים כפי שהאתר של מועדון הוטלס מחזיר; מחירי חברי i-club לא כלולים. " +
      "הקישור להזמנה פותח את תוצאות החיפוש באתר לאותם תאריכים ולאותו הרכב, והוא כולל את הקוד רק כשהמחיר איתו זול יותר. " +
      "קוד mhot אינו הנחה קבועה: בחדר אחד הוא בדרך כלל מייקר את ההצעה הזולה ביותר כי הסוויטה עם המטבחון נעלמת, ובשני חדרים הוא בדרך כלל זול יותר. " +
      (bits.length ? "סריקות אחרונות (שעון ישראל): " + bits.join("; ") + ". " : "") +
      "מקור: m.clubhotels.co.il.</p>";
  }

  function renderCalendar(s, rows) {
    const byDate = {};
    for (const row of rows) byDate[row.date] = row;
    let lo = Infinity;
    let hi = 0;
    for (const row of rows) {
      if (row.per_night < lo) lo = row.per_night;
      if (row.per_night > hi) hi = row.per_night;
    }
    const scans = (data.scans && data.scans[s.party]) || [];
    const legend = '<div class="legend"><span>זול</span>' +
      [0, 0.25, 0.5, 0.75, 1].map((t) => '<span class="swatch" style="background:' + heatColor(t) + '"></span>').join("") +
      "<span>" + (hi > 0 ? "יקר (" + fmt(lo) + " עד " + fmt(hi) + " ₪ ללילה)" : "אין תאריכים זמינים בסינון הזה") + "</span></div>" +
      '<div class="trend-key"><span>מגמה מול הסריקה הקודמת' +
      (scans.length >= 2 ? " (" + scans[scans.length - 2].label + " ל־" + scans[scans.length - 1].label + ")" : "") +
      ':</span><span class="up">▲ עלה</span><span class="down">▼ ירד</span><span class="flat">▬ יציב</span></div>' +
      '<p class="hint">בכל יום מוצג המחיר הזול מבין הרגיל ועם קוד mhot. הסימון <span class="mhot">mhot</span> אומר שהקוד זול יותר והקישור נפתח איתו. במחשב, העבירו את העכבר מעל יום כדי לראות את ההיסטוריה. בטלפון, לחיצה ארוכה פותחת את ההיסטוריה בלי לעבור לאתר, והקשה רגילה פותחת את ההזמנה. ימים עם מסגרת מקווקוו אינם זמינים עכשיו אבל יש להם היסטוריה. כותרת החודש נשארת בראש המסך בזמן הגלילה ואינה מכסה את כרטיס ההיסטוריה.</p>' +
      '<div class="month-jump"><span class="hint">קפיצה לחודש:</span>' +
      data.months.map((month) => '<button type="button" data-jump="' + month.key + '">' + month.name + "</button>").join("") +
      "</div>";
    const months = data.months.map((month, index) => monthHtml(month, index, s, byDate, lo, hi)).join("");
    $("calendar").innerHTML = legend + months;
  }

  function monthHtml(month, index, s, byDate, lo, hi) {
    const year = Number(month.key.slice(0, 4));
    const monthIndex = Number(month.key.slice(5, 7)) - 1;
    const first = new Date(Date.UTC(year, monthIndex, 1)).getUTCDay();
    const days = new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
    const prev = index > 0 ? data.months[index - 1].key : "";
    const next = index < data.months.length - 1 ? data.months[index + 1].key : "";
    let cells = "";
    for (let i = 0; i < first; i++) cells += "<div></div>";
    for (let day = 1; day <= days; day++) {
      const date = year + "-" + pad(monthIndex + 1) + "-" + pad(day);
      cells += dayHtml(date, day, s, byDate, lo, hi);
    }
    return '<section class="month" id="cal-' + month.key + '">' +
      '<div class="month-head"><button type="button" data-jump="' + prev + '"' + (prev ? "" : " disabled") + ' aria-label="לחודש הקודם">→ חודש קודם</button>' +
      "<h3>" + month.name + "</h3>" +
      '<button type="button" data-jump="' + next + '"' + (next ? "" : " disabled") + ' aria-label="לחודש הבא">חודש הבא ←</button></div>' +
      '<div class="week">' + WEEKDAYS.map((name) => "<div>" + name + "</div>").join("") + "</div>" +
      '<div class="days">' + cells + "</div></section>";
  }

  function holidayOf(date) {
    return (data.holidays && data.holidays[date]) || null;
  }

  function holidayClass(date) {
    const holiday = holidayOf(date);
    return holiday ? " hol hol-" + holiday.kind : "";
  }

  function holidayMark(date) {
    const holiday = holidayOf(date);
    if (!holiday) return "";
    return '<span class="holiday-name">' + escapeText(holiday.name) + "</span>";
  }

  function dayHtml(date, day, s, byDate, lo, hi) {
    const offer = byDate[date];
    const had = points(s, date, "none").some((p) => p.price != null) || points(s, date, "mhot").some((p) => p.price != null);
    const klass = holidayClass(date);
    const name = holidayMark(date);
    if (!offer && had) {
      return '<div class="day past' + klass + '" data-date="' + date + '" tabindex="0"><span class="top"><span>' +
        day + "</span></span>" + name + "</div>";
    }
    if (!offer) {
      const open = holidayOf(date) ? ' data-date="' + date + '" tabindex="0"' : "";
      return '<div class="day empty' + klass + '"' + open + '><span class="top"><span>' + day + "</span></span>" + name + "</div>";
    }
    const t = hi === lo ? 0 : (offer.per_night - lo) / (hi - lo);
    const color = heatColor(t);
    const tr = trend(s.party, offer.use_mhot, s, date);
    const mark = tr ? '<span class="' + tr.kind + '">' + (tr.kind === "up" ? "▲" : tr.kind === "down" ? "▼" : "▬") + "</span>" : "";
    return '<a class="day' + klass + '" data-date="' + date + '" href="' + offer.url + '" target="_blank" rel="noopener noreferrer" style="background:' +
      color + '22;border-bottom:3px solid ' + color + '"><span class="top"><span>' + day + "</span>" + mark +
      '</span><span class="price' + (offer.use_mhot ? " mhot" : "") + '">' + fmt(offer.per_night) + " ₪" +
      (offer.use_mhot ? ' <span class="mhot">mhot</span>' : "") + "</span>" + name + "</a>";
  }

  function refresh() {
    hideCard();
    const s = state();
    const rows = offersFor(s);
    renderBest(s, rows);
    renderTop(s, rows);
    renderBars(rows);
    renderMatrix(s);
    renderAbout();
    renderCalendar(s, rows);
  }

  function openCard(day, pin) {
    const date = day.dataset.date;
    const s = state();
    const rows = offersFor(s);
    const offer = rows.find((row) => row.date === date) || null;
    $("card").dataset.date = date;
    $("card").innerHTML = chartHtml(s, date, offer);
    $("card").hidden = false;
    cancelHide();
    placeCard(day.getBoundingClientRect());
    if (pin) {
      pinned = date;
      $("backdrop").hidden = false;
    }
  }

  function cancelHide() {
    if (hideTimer !== null) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
  }

  function scheduleHide() {
    if (pinned) return;
    cancelHide();
    // The card sits a few pixels away from the day. Keep it open long enough
    // for the pointer to cross that gap and land on the booking link.
    hideTimer = setTimeout(() => {
      hideTimer = null;
      if (!pinned) hideCard();
    }, 300);
  }

  function hideCard() {
    cancelHide();
    pinned = null;
    $("card").hidden = true;
    $("backdrop").hidden = true;
  }

  function placeCard(rect) {
    const card = $("card");
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const cardW = Math.min(300, vw - 16);
    card.style.width = cardW + "px";
    const left = Math.max(8, Math.min(vw - cardW - 8, (rect.left + rect.right) / 2 - cardW / 2));
    const headerH = 52;
    const spaceBelow = vh - rect.bottom - 12;
    const spaceAbove = rect.top - headerH - 12;
    const down = spaceBelow >= 280 || spaceBelow >= spaceAbove;
    card.style.left = left + "px";
    // Overlap the day by a few pixels so the pointer never falls in a gap
    // between the cell and the booking link.
    if (down) {
      card.style.top = (rect.bottom - 6) + "px";
      card.style.bottom = "auto";
      card.style.maxHeight = Math.max(180, Math.min(spaceBelow + 6, vh * 0.72)) + "px";
    } else {
      card.style.top = "auto";
      card.style.bottom = (vh - rect.top - 6) + "px";
      card.style.maxHeight = Math.max(180, Math.min(spaceAbove + 6, vh * 0.72)) + "px";
    }
  }

  function chartHtml(s, date, offer) {
    const none = points(s, date, "none");
    const mhot = points(s, date, "mhot");
    const both = none.concat(mhot);
    const avail = both.filter((p) => p.price != null);
    const holiday = holidayOf(date);
    let html = "<strong>כניסה ב־" + dmyFull(date) + "</strong>";
    if (holiday) html += '<div class="card-holiday">' + escapeText(holiday.name) + "</div>";
    if (offer) {
      html += '<div><span class="dot" style="background:' + BLUE + '"></span>מחיר רגיל: ' +
        (offer.none == null ? "לא זמין" : fmt(offer.none) + " ₪") + "</div>";
      html += '<div><span class="dot" style="background:' + RED + '"></span>עם קוד mhot: ' +
        (offer.mhot == null ? "לא זמין" : fmt(offer.mhot) + " ₪") + "</div>";
      html += "<strong>הזול: " + fmt(offer.total) + " ₪ ל־" + s.nights + " לילות (" + fmt(offer.per_night) +
        " ₪ ללילה), " + (offer.use_mhot ? "עם קוד mhot" : "מחיר רגיל") + "</strong>";
      html += bookingLink(offer);
    } else {
      html += "<div>אין זמינות בסריקה האחרונה.</div>";
    }
    html += chartSvg(none, mhot, avail);
    html += '<div class="chart-key"><span><span class="dot" style="background:' + BLUE + '"></span>כחול = מחיר רגיל</span>' +
      '<span><span class="dot" style="background:' + RED + '"></span>אדום = עם קוד mhot</span></div>';
    html += "<div>" + changeText(none) + "</div>";
    html += "<div>" + mhotText(mhot) + "</div>";
    const tr = offer ? trend(s.party, offer.use_mhot, s, date) : trend(s.party, false, s, date);
    if (tr) {
      const sign = tr.kind === "flat" ? "ללא שינוי (0 ₪)" : (tr.kind === "up" ? "+" : "−") + fmt(Math.abs(tr.delta)) + " ₪";
      html += '<div class="' + tr.kind + '"><strong>' + (tr.kind === "up" ? "▲ " : tr.kind === "down" ? "▼ " : "▬ ") +
        (offer && offer.use_mhot ? "עם קוד, " : "") + "מהסריקה הקודמת (" + tr.prevLabel + "): " + sign + "</strong></div>";
    }
    if (both.some((p) => p.price == null)) html += '<div class="hint">עיגול ריק בתחתית הגרף = לא זמין באותה סריקה.</div>';
    return html;
  }

  function bookingLink(offer) {
    const which = offer.use_mhot ? "עם mhot" : "מחיר רגיל";
    const kind = offer.use_mhot ? "mhot" : "regular";
    return '<a class="book-link ' + kind + '" href="' + offer.url + '" target="_blank" rel="noopener noreferrer">' +
      "להזמנה באתר מועדון הוטלס – " + fmt(offer.total) + " ₪ (" + which + ")</a>";
  }

  function changeText(none) {
    const avail = none.filter((p) => p.price != null);
    if (!avail.length) return "אין עדיין מחיר רגיל להשוואה.";
    const first = avail[0];
    const last = none[none.length - 1];
    if (last.price == null) return "בסריקה האחרונה (" + last.label + ") לא זמין. המחיר האחרון שנצפה: " + fmt(avail[avail.length - 1].price) + " ₪.";
    if (last.at === first.at) return "זו הסריקה הראשונה שבה התאריך זמין, אין עדיין שינוי להשוות.";
    const delta = last.price - first.price;
    if (delta === 0) return "שינוי מהסריקה הראשונה (" + first.label + "): ללא שינוי.";
    const pct = (Math.abs(delta) / first.price) * 100;
    return "שינוי מהסריקה הראשונה (" + first.label + "): " + (delta > 0 ? "+" : "−") + fmt(Math.abs(delta)) +
      " ₪ (" + (delta > 0 ? "+" : "−") + pct.toFixed(1) + "%).";
  }

  function mhotText(mhot) {
    const avail = mhot.filter((p) => p.price != null);
    if (!mhot.length) return "עם קוד mhot: אין עדיין מדידה לתאריך הזה.";
    const last = mhot[mhot.length - 1];
    let min = null;
    for (const point of avail) if (!min || point.price < min.price) min = point;
    if (mhot.length === 1) {
      return "עם קוד mhot: " + (last.price == null ? "לא זמין" : fmt(last.price) + " ₪") + " (נמדד פעם אחת, " + last.label + ").";
    }
    return "עם קוד mhot: " + (last.price == null ? "לא זמין" : fmt(last.price) + " ₪") + " (" + last.label + ")" +
      (min ? ", הכי זול עד עכשיו: " + fmt(min.price) + " ₪ (" + min.label + ")" : "") + ".";
  }

  function chartSvg(none, mhot, avail) {
    const X0 = 52;
    const X1 = 250;
    const YT = 16;
    const YB = 62;
    let t0 = Infinity;
    let t1 = -Infinity;
    for (const point of none.concat(mhot)) {
      const time = Date.parse(point.at);
      if (time < t0) t0 = time;
      if (time > t1) t1 = time;
    }
    const xOf = (point) => (t1 <= t0 ? (X0 + X1) / 2 : X0 + ((Date.parse(point.at) - t0) / (t1 - t0)) * (X1 - X0));
    let lo = Infinity;
    let hi = 0;
    for (const point of avail) {
      if (point.price < lo) lo = point.price;
      if (point.price > hi) hi = point.price;
    }
    const yOf = (value) => (hi === lo ? (YT + YB) / 2 : YB - ((value - lo) / (hi - lo)) * (YB - YT));
    const runs = (list) => {
      const out = [];
      let current = [];
      for (const point of list) {
        if (point.price != null) current.push(xOf(point).toFixed(1) + "," + yOf(point.price).toFixed(1));
        else if (current.length > 1) { out.push(current.join(" ")); current = []; }
        else current = [];
      }
      if (current.length > 1) out.push(current.join(" "));
      return out;
    };
    const labels = none.concat(mhot).slice().sort((a, b) => Date.parse(a.at) - Date.parse(b.at))
      .filter((point, i, arr) => i === 0 || point.at !== arr[i - 1].at);
    let svg = '<svg viewBox="0 0 260 100" role="img" aria-label="גרף היסטוריית מחיר">';
    if (avail.length) {
      svg += '<line x1="' + X0 + '" y1="' + yOf(hi) + '" x2="' + X1 + '" y2="' + yOf(hi) + '" stroke="#d5dde6" stroke-dasharray="3 3"/>';
      if (hi !== lo) svg += '<line x1="' + X0 + '" y1="' + yOf(lo) + '" x2="' + X1 + '" y2="' + yOf(lo) + '" stroke="#d5dde6" stroke-dasharray="3 3"/>';
      svg += '<text x="' + (X0 - 6) + '" y="' + (yOf(hi) + 3) + '" font-size="10" fill="#5c6b7a" text-anchor="end">' + fmt(hi) + "</text>";
      if (hi !== lo) svg += '<text x="' + (X0 - 6) + '" y="' + (yOf(lo) + 3) + '" font-size="10" fill="#5c6b7a" text-anchor="end">' + fmt(lo) + "</text>";
    }
    for (const run of runs(none)) svg += '<polyline points="' + run + '" fill="none" stroke="' + BLUE + '" stroke-width="2"/>';
    for (const run of runs(mhot)) svg += '<polyline points="' + run + '" fill="none" stroke="' + RED + '" stroke-width="2"/>';
    none.forEach((point) => {
      const x = xOf(point);
      svg += point.price != null
        ? '<circle cx="' + x + '" cy="' + yOf(point.price) + '" r="3.5" fill="' + BLUE + '"/>'
        : '<circle cx="' + x + '" cy="74" r="3.5" fill="none" stroke="#8b98a6"/>';
    });
    mhot.forEach((point) => {
      const x = xOf(point);
      svg += point.price != null
        ? '<circle cx="' + x + '" cy="' + yOf(point.price) + '" r="4" fill="' + RED + '"/>'
        : '<circle cx="' + x + '" cy="83" r="3.5" fill="none" stroke="' + RED + '"/>';
    });
    labels.forEach((point, i) => {
      if (labels.length > 3 && i !== 0 && i !== labels.length - 1) return;
      const anchor = labels.length === 1 ? "middle" : i === 0 ? "start" : "end";
      svg += '<text x="' + xOf(point) + '" y="97" font-size="10" fill="#5c6b7a" text-anchor="' + anchor + '">' + point.label + "</text>";
    });
    svg += "</svg>";
    return svg;
  }

  function cancelPress() {
    if (pressTimer !== null) {
      clearTimeout(pressTimer);
      pressTimer = null;
    }
  }

  function beginPress(day, x, y) {
    if (pressTimer !== null) return;
    pressFiredFor = null;
    pressStart = { x: x, y: y };
    const key = day.dataset.date;
    pressTimer = setTimeout(() => {
      pressTimer = null;
      pressFiredFor = key;
      openCard(day, true);
    }, LONG_PRESS_MS);
  }

  function wire() {
    for (const id of ["party", "nights", "board", "rooms"]) {
      $(id).addEventListener("change", refresh);
    }
    const calendar = $("calendar");
    calendar.addEventListener("click", (event) => {
      const jump = event.target.closest("[data-jump]");
      if (jump) {
        const target = document.getElementById("cal-" + jump.dataset.jump);
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      const day = event.target.closest("a[data-date]");
      if (!day) return;
      if (pressFiredFor === day.dataset.date) {
        event.preventDefault();
        return;
      }
      if (touchDay === day.dataset.date && pinned !== day.dataset.date) {
        event.preventDefault();
        openCard(day, true);
      }
    });
    calendar.addEventListener("mouseover", (event) => {
      const day = event.target.closest("[data-date]");
      if (!day || pinned) return;
      openCard(day, false);
    });
    calendar.addEventListener("mouseout", (event) => {
      const day = event.target.closest("[data-date]");
      if (!day || pinned) return;
      const next = event.relatedTarget;
      if (next && (day.contains(next) || (next.closest && next.closest("#card")))) {
        cancelHide();
        return;
      }
      scheduleHide();
    });
    calendar.addEventListener("pointerdown", (event) => {
      const day = event.target.closest("[data-date]");
      if (!day || (event.pointerType !== "touch" && event.pointerType !== "pen")) return;
      touchDay = day.dataset.date;
      beginPress(day, event.clientX, event.clientY);
    });
    calendar.addEventListener("pointermove", (event) => {
      if (pressTimer === null || pressStart === null) return;
      if (Math.abs(event.clientX - pressStart.x) > PRESS_MOVE_PX || Math.abs(event.clientY - pressStart.y) > PRESS_MOVE_PX) {
        cancelPress();
      }
    });
    calendar.addEventListener("pointerup", () => {
      cancelPress();
      if (pressFiredFor !== null) setTimeout(() => { pressFiredFor = null; }, 500);
    });
    calendar.addEventListener("contextmenu", (event) => {
      const day = event.target.closest("[data-date]");
      if (!day || touchDay !== day.dataset.date) return;
      event.preventDefault();
      pressFiredFor = day.dataset.date;
      openCard(day, true);
    });
    $("backdrop").addEventListener("click", hideCard);
    $("card").addEventListener("mouseenter", cancelHide);
    $("card").addEventListener("mouseleave", () => {
      if (!pinned) scheduleHide();
    });
    $("card").addEventListener("click", (event) => {
      if (event.target.closest("a.book-link")) event.stopPropagation();
    });
    window.addEventListener("scroll", () => {
      if (!$("card").hidden) {
        const day = document.querySelector('[data-date="' + ($("card").dataset.date || "") + '"]');
        if (pinned) hideCard();
        else if (day) placeCard(day.getBoundingClientRect());
      }
    }, { passive: true });
  }

  function escapeText(value) {
    return String(value).replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]));
  }

  fetch("data.json")
    .then((response) => {
      if (!response.ok) throw new Error("status " + response.status);
      return response.json();
    })
    .then((loaded) => {
      data = loaded;
      fillFilters();
      renderStatus();
      wire();
      refresh();
    })
    .catch((error) => {
      $("status").innerHTML = "<h2>מצב הסריקה</h2><p class=\"warn\">לא הצלחנו לטעון את הנתונים (" +
        escapeText(error.message) + ").</p>";
    });
})();
