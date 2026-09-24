// Админка владельца в браузере. Данные — с сервера через SSH-туннель (localhost).
// Графики рисуются своим SVG: страница открывается без интернета, и тянуть
// библиотеку с чужого CDN ради двух линий незачем.

const screen = document.getElementById("screen");
const state = { tab: "overview", days: 30, users: { q: "", offset: 0 }, tracks: { q: "", offset: 0 } };
const PAGE = 50;

async function api(path, options) {
  const response = await fetch(path, options);
  if (response.status === 401) {
    renderLogin();
    throw new Error("нужен вход");
  }
  if (!response.ok) {
    let detail = `${path}: ${response.status}`;
    try {
      const payload = await response.json();
      if (payload && payload.detail) detail = payload.detail;
    } catch {
      // тело не JSON — оставляем код ответа
    }
    throw new Error(detail);
  }
  return response.json();
}

function post(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

// --- Вход: пароль, затем одноразовый код из Telegram (решение владельца 22.09) ---

let loginStage = "password";

function renderLogin(message) {
  document.getElementById("tabs").style.display = "none";
  screen.innerHTML = `
    <div class="login">
      <h2>${loginStage === "password" ? "Вход в админку" : "Код из Telegram"}</h2>
      <p class="muted">${
        loginStage === "password"
          ? "Пароль знаете только вы. Вторым шагом бот пришлёт одноразовый код."
          : "Код действует 5 минут и сгорает после первой попытки."
      }</p>
      <input id="login-input" type="password" autocomplete="off"
        placeholder="${loginStage === "password" ? "Пароль" : "6 цифр"}" />
      <button id="login-go">${loginStage === "password" ? "Дальше" : "Войти"}</button>
      ${message ? `<p class="error">${esc(message)}</p>` : ""}
    </div>
  `;
  const input = document.getElementById("login-input");
  input.focus();
  const submit = async () => {
    const value = input.value.trim();
    if (!value) return;
    try {
      if (loginStage === "password") {
        await post("/api/login", { password: value });
        loginStage = "code";
        renderLogin();
      } else {
        await post("/api/login/code", { code: value });
        loginStage = "password";
        document.getElementById("tabs").style.display = "";
        async function boot() {
  try {
    const session = await fetch("/api/session").then((r) => r.json());
    if (!session.authorized) {
      loginStage = session.code_pending ? "code" : "password";
      renderLogin();
      return;
    }
  } catch {
    // сессия не отвечает — покажем обычную ошибку в render()
  }
  render();
}

boot();
      }
    } catch (error) {
      renderLogin(error.message);
    }
  };
  document.getElementById("login-go").addEventListener("click", submit);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") submit();
  });
}

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const num = (value) => (value ?? 0).toLocaleString("ru-RU");
const date = (iso) => (iso ? iso.slice(0, 10) : "—");
const pct = (part, whole) => (whole ? Math.round((part * 100) / whole) + "%" : "—");
const mins = (sec) => `${Math.floor((sec || 0) / 60)} мин ${(sec || 0) % 60} сек`;

function card(value, label, sub) {
  return `<div class="card"><div class="value">${esc(value)}</div><div class="label">${esc(label)}</div>${
    sub ? `<div class="sub">${esc(sub)}</div>` : ""
  }</div>`;
}

// Линейный график: две серии на общей сетке дней.
function lineChart(series, keys, colors, height = 160) {
  const width = 900;
  const max = Math.max(1, ...series.flatMap((point) => keys.map((key) => point[key])));
  const stepX = series.length > 1 ? width / (series.length - 1) : width;
  const paths = keys.map((key, index) => {
    const d = series
      .map((point, i) => `${i ? "L" : "M"}${(i * stepX).toFixed(1)} ${(height - (point[key] / max) * (height - 20)).toFixed(1)}`)
      .join(" ");
    return `<path d="${d}" fill="none" stroke="${colors[index]}" stroke-width="2" />`;
  });
  const labels = [series[0], series[Math.floor(series.length / 2)], series[series.length - 1]]
    .filter(Boolean)
    .map((point, i) => {
      const x = i === 0 ? 0 : i === 1 ? width / 2 : width;
      const anchor = i === 0 ? "start" : i === 1 ? "middle" : "end";
      return `<text x="${x}" y="${height + 14}" fill="#9a9aa2" font-size="11" text-anchor="${anchor}">${esc(point.day)}</text>`;
    });
  return `<div class="chart"><svg viewBox="0 0 ${width} ${height + 20}" preserveAspectRatio="none" style="width:100%;height:${height + 24}px">
    ${paths.join("")}${labels.join("")}
  </svg><div class="muted" style="font-size:13px;margin-top:6px">
    ${keys.map((key, i) => `<span style="color:${colors[i]}">■</span> ${key === "listens" ? "прослушивания" : "новые люди"}`).join(" &nbsp; ")}
    · максимум ${num(max)} в день
  </div></div>`;
}

async function renderOverview() {
  const data = await api(`/api/overview?days=${state.days}`);
  const r = data.report;
  const cat = data.catalog;
  const money = data.revenue;
  screen.innerHTML = `
    <div class="tools">
      <select id="days">
        ${[1, 7, 30, 90].map((d) => `<option value="${d}" ${d === state.days ? "selected" : ""}>${d} дн.</option>`).join("")}
      </select>
    </div>
    <div class="cards">
      ${card(num(r.users_total), "всего людей", `новых за период: ${num(r.users_new)}`)}
      ${card(num(r.active_7d), "активны за неделю", `за сутки: ${num(r.active_1d)}`)}
      ${card(pct(r.retention_d1[0], r.retention_d1[1]), "вернулись через сутки", `через неделю: ${pct(r.retention_d7[0], r.retention_d7[1])}`)}
      ${card(num(r.listens), "прослушиваний", `у ${num(r.listeners)} человек`)}
      ${card(num(r.sessions), "сессий Mini App", `медиана ${mins(r.session_median_sec)}`)}
      ${card(num(r.searches), "поисков", `пустых: ${pct(r.searches_empty, r.searches_with_count)}`)}
      ${card(num(r.premium_active), "Premium активен", `пробных всего: ${num(r.trials_total)}`)}
      ${card(`${num(money.month)} ₽`, "оплаты за 30 дней", `всего: ${num(money.total)} ₽ · донаты ${num(data.donations.rub)} ₽`)}
      ${card(num(cat.tracks_total), "треков в каталоге", `артистов: ${num(cat.artists_total)}`)}
    </div>
    <h2>По дням</h2>
    ${lineChart(data.series, ["listens", "users"], ["#3b7bfe", "#35c759"])}
    <h2>Жанры</h2>
    <div class="list">${
      (r.top_genres || []).map(([name, count]) => `<div class="row-line"><span>${esc(name)}</span><span class="muted">${num(count)}</span></div>`).join("") ||
      '<span class="muted">нет данных</span>'
    }</div>
    <h2>Топ треков</h2>
    <div class="list">${
      (r.top_tracks || []).map(([name, count]) => `<div class="row-line"><span>${esc(name)}</span><span class="muted">${num(count)}</span></div>`).join("") ||
      '<span class="muted">нет данных</span>'
    }</div>
    <h2>Топ запросов</h2>
    <div class="list">${
      (r.top_queries || []).map(([q, count]) => `<div class="row-line"><span>${esc(q)}</span><span class="muted">${num(count)}</span></div>`).join("") ||
      '<span class="muted">нет данных</span>'
    }</div>`;
  document.getElementById("days").addEventListener("change", (event) => {
    state.days = Number(event.target.value);
    render();
  });
}

async function renderUsers() {
  const { q, offset } = state.users;
  const data = await api(`/api/users?q=${encodeURIComponent(q)}&limit=${PAGE}&offset=${offset}`);
  screen.innerHTML = `
    <div class="tools">
      <input type="search" id="q" placeholder="Имя, @username или Telegram-id" value="${esc(q)}" />
      <span class="muted">найдено: ${num(data.total)}</span>
    </div>
    <table><thead><tr>
      <th>Кто</th><th>id</th><th>Пришёл</th><th>Premium</th><th>Прослушиваний</th><th>Язык</th><th>Статус</th><th>Premium вручную</th>
    </tr></thead><tbody>
      ${data.items
        .map(
          (u) => `<tr>
            <td class="wide">${esc(u.name)}${u.username ? ` <span class="muted">@${esc(u.username)}</span>` : ""}</td>
            <td class="muted">${esc(u.telegram_id)}</td>
            <td>${date(u.created_at)}</td>
            <td>${u.premium_active ? `<span class="pill good">до ${date(u.premium_until)}</span>` : u.trial_used ? '<span class="pill warn">пробный был</span>' : "—"}</td>
            <td>${num(u.listens)}</td>
            <td>${esc(u.language)}</td>
            <td>${u.blocked ? '<span class="pill bad">заблокировал бота</span>' : '<span class="pill">активен</span>'}</td>
            <td class="actions">
              <button class="mini" data-premium="${u.telegram_id}" data-days="30">+30д</button>
              <button class="mini" data-premium="${u.telegram_id}" data-days="365">+год</button>
              <button class="mini danger" data-premium="${u.telegram_id}" data-days="0">снять</button>
            </td>
          </tr>`
        )
        .join("")}
    </tbody></table>
    ${pager(data.total, offset, "users")}`;
  bindSearch("users");
  bindPager("users");
  // Выдача Premium руками: подтверждение обязательно — это чужая подписка,
  // а кнопки стоят вплотную к строке поиска.
  screen.querySelectorAll("button[data-premium]").forEach((button) =>
    button.addEventListener("click", async () => {
      const days = Number(button.dataset.days);
      const who = button.dataset.premium;
      const question = days
        ? `Выдать Premium на ${days} дней пользователю ${who}?`
        : `Снять Premium у пользователя ${who}?`;
      if (!window.confirm(question)) return;
      try {
        await post(`/api/users/${who}/premium`, { days });
        render();
      } catch (error) {
        window.alert(error.message);
      }
    })
  );
}

async function renderTracks() {
  const { q, offset } = state.tracks;
  const data = await api(`/api/tracks?q=${encodeURIComponent(q)}&limit=${PAGE}&offset=${offset}`);
  screen.innerHTML = `
    <div class="tools">
      <input type="search" id="q" placeholder="Исполнитель или название" value="${esc(q)}" />
      <span class="muted">найдено: ${num(data.total)}</span>
    </div>
    <table><thead><tr>
      <th>id</th><th class="wide">Исполнитель — Название</th><th>Альбом</th><th>Длина</th><th>Настроение</th><th>Прослушиваний</th><th>Файл</th>
    </tr></thead><tbody>
      ${data.items
        .map(
          (t) => `<tr>
            <td class="muted">${t.id}</td>
            <td class="wide">${esc(t.artist)} — ${esc(t.title)}</td>
            <td>${esc(t.album || "—")}</td>
            <td>${t.duration ? Math.floor(t.duration / 60) + ":" + String(t.duration % 60).padStart(2, "0") : "—"}</td>
            <td>${t.mood ? esc(t.mood) : '<span class="muted">не размечено</span>'}</td>
            <td>${num(t.listens)}</td>
            <td>${t.playable ? '<span class="pill good">готов</span>' : '<span class="pill warn">нужен ремонт</span>'}</td>
          </tr>`
        )
        .join("")}
    </tbody></table>
    ${pager(data.total, offset, "tracks")}`;
  bindSearch("tracks");
  bindPager("tracks");
}

async function renderMoney() {
  const data = await api("/api/money?limit=50");
  const rows = (items, kind) =>
    items
      .map(
        (item) => `<tr>
          <td>${date(item.created_at)}</td>
          <td class="wide">${esc(item.user.name || "—")} <span class="muted">${esc(item.user.telegram_id ?? "")}</span></td>
          <td>${num(item.rub)} ₽${item.stars ? ` · ${num(item.stars)} ⭐` : ""}</td>
          <td>${kind === "pay" ? esc(item.source) : item.refunded ? '<span class="pill bad">возврат</span>' : '<span class="pill good">зачтён</span>'}</td>
        </tr>`
      )
      .join("") || '<tr><td colspan="4" class="muted">нет записей</td></tr>';
  screen.innerHTML = `
    <h2>Оплаты Premium</h2>
    <table><thead><tr><th>Когда</th><th>Кто</th><th>Сумма</th><th>Способ</th></tr></thead>
      <tbody>${rows(data.payments, "pay")}</tbody></table>
    <h2>Донаты</h2>
    <table><thead><tr><th>Когда</th><th>Кто</th><th>Сумма</th><th>Статус</th></tr></thead>
      <tbody>${rows(data.donations, "don")}</tbody></table>
    <p class="muted">Рассылки и возвраты остаются в боте: их подтверждение — там, где к нему привыкли.</p>`;
}

function pager(total, offset, key) {
  const from = total ? offset + 1 : 0;
  const to = Math.min(offset + PAGE, total);
  return `<div class="pager">
    <button class="page" data-step="-1" data-key="${key}" ${offset === 0 ? "disabled" : ""}>Назад</button>
    <span class="muted">${from}–${to} из ${num(total)}</span>
    <button class="page" data-step="1" data-key="${key}" ${to >= total ? "disabled" : ""}>Вперёд</button>
  </div>`;
}

function bindSearch(key) {
  const input = document.getElementById("q");
  let timer = null;
  input.addEventListener("input", (event) => {
    clearTimeout(timer);
    const value = event.target.value;
    timer = setTimeout(() => {
      state[key] = { q: value, offset: 0 };
      render().then(() => {
        const next = document.getElementById("q");
        if (next) {
          next.focus();
          next.setSelectionRange(value.length, value.length);
        }
      });
    }, 300);
  });
}

function bindPager(key) {
  screen.querySelectorAll("button.page").forEach((button) =>
    button.addEventListener("click", () => {
      state[key].offset = Math.max(0, state[key].offset + Number(button.dataset.step) * PAGE);
      render();
    })
  );
}

async function renderBroadcast() {
  screen.innerHTML = `
    <div class="broadcast">
      <h2>Рассылка</h2>
      <p class="muted">Уйдёт всем, кто не заблокировал бота. Два шага: сперва
        покажем охват, отправка — отдельным подтверждением.</p>
      <textarea id="bc-text" rows="8" placeholder="Текст сообщения"></textarea>
      <button id="bc-check">Посчитать охват</button>
      <div id="bc-result" class="muted"></div>
    </div>`;
  const result = document.getElementById("bc-result");
  document.getElementById("bc-check").addEventListener("click", async () => {
    const text = document.getElementById("bc-text").value.trim();
    if (!text) return;
    try {
      const preview = await post("/api/broadcast", { text, confirm: false });
      result.innerHTML = `Получат сообщение: <b>${num(preview.reach)}</b> человек.
        <button id="bc-send" class="danger">Отправить</button>`;
      document.getElementById("bc-send").addEventListener("click", async () => {
        if (!window.confirm(`Отправить ${num(preview.reach)} людям? Отменить будет нельзя.`)) return;
        try {
          await post("/api/broadcast", { text, confirm: true });
          result.textContent = "Рассылка запущена.";
        } catch (error) {
          result.textContent = error.message;
        }
      });
    } catch (error) {
      result.textContent = error.message;
    }
  });
}

const VIEWS = {
  overview: renderOverview,
  users: renderUsers,
  tracks: renderTracks,
  money: renderMoney,
  broadcast: renderBroadcast,
};

async function render() {
  try {
    await VIEWS[state.tab]();
  } catch (error) {
    screen.innerHTML = `<p class="error">Не удалось получить данные: ${esc(error.message)}</p>
      <p class="muted">Туннель закрылся? Проверь окно, где запущен python -m app.webadmin.</p>`;
  }
}

document.getElementById("tabs").addEventListener("click", (event) => {
  const button = event.target.closest(".tab");
  if (!button) return;
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("is-active", tab === button));
  state.tab = button.dataset.tab;
  render();
});

async function boot() {
  try {
    const session = await fetch("/api/session").then((r) => r.json());
    if (!session.authorized) {
      loginStage = session.code_pending ? "code" : "password";
      renderLogin();
      return;
    }
  } catch {
    // страница открыта, а сервера нет — обычная ошибка покажется в render()
  }
  render();
}

boot();
