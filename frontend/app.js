"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const money = (value) =>
  new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(value);
const escapeHtml = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        ch
      ],
  );
let products = [];
let cartTotal = 0;
let usdRate = null;
async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = null;
    }
    const error = new Error(
      typeof detail === "string"
        ? detail
        : "Проверьте введённые данные и повторите попытку.",
    );
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}
function toast(message) {
  const target = $("#toast");
  target.textContent = message;
  target.classList.add("visible");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => target.classList.remove("visible"), 4500);
}
function showError(id, message) {
  const element = $(`#${id}`);
  element.setAttribute("aria-invalid", String(Boolean(message)));
  const output = $(`#${id}-error`);
  if (output) {
    output.textContent = message;
    element.setAttribute("aria-describedby", output.id);
  }
  return !message;
}
function empty(
  title,
  message,
  link = "/catalog.html",
  label = "Перейти в каталог",
) {
  return `<div class="empty-state"><h2>${escapeHtml(title)}</h2><p>${escapeHtml(message)}</p><a class="button dark" href="${link}">${label} ↗</a></div>`;
}
function card(product) {
  return `<article class="product-card"><a class="product-image" href="/product.html?id=${product.id}"><img src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}" loading="lazy"><span class="tag">${escapeHtml(product.category)}</span></a><h3><a href="/product.html?id=${product.id}">${escapeHtml(product.name)}</a></h3><p>${escapeHtml(product.unit)} · Для вашего проекта</p><div class="card-bottom"><span class="price">${money(product.price)} <small>/ ${escapeHtml(product.unit)}</small></span><button type="button" class="add-cart" data-add="${product.id}">В корзину +</button></div></article>`;
}
async function refreshCartCount() {
  try {
    const cart = await api("/cart");
    $("#cart-count").textContent = cart.items.reduce(
      (sum, item) => sum + item.quantity,
      0,
    );
  } catch {
    $("#cart-count").textContent = "0";
  }
}
async function addToCart(id, amount = 1) {
  try {
    const cart = await api("/cart");
    const current =
      cart.items.find((item) => item.product.id === id)?.quantity || 0;
    if (current + amount > 999) {
      toast("В корзине может быть не более 999 упаковок одного материала.");
      return;
    }
    await api(`/cart/${id}`, {
      method: "PUT",
      body: JSON.stringify({ quantity: current + amount }),
    });
    await refreshCartCount();
    toast("Материал добавлен в вашу корзину.");
  } catch (error) {
    if (error.status === 401) {
      toast("Войдите или зарегистрируйтесь, чтобы сохранить корзину.");
      setTimeout(() => {
        window.location.href = "/account.html";
      }, 1200);
    } else {
      toast(
        error.status
          ? error.message
          : "Нет связи с сервером. Попробуйте ещё раз.",
      );
    }
  }
}
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-add]");
  if (!button) return;
  button.disabled = true;
  try {
    await addToCart(button.dataset.add, Number(button.dataset.quantity || 1));
  } finally {
    button.disabled = false;
  }
});
function initCatalog() {
  const form = $("#filters");
  const params = new URLSearchParams(location.search);
  const categories = [...new Set(products.map((product) => product.category))];
  $("#category").innerHTML += categories
    .map((category) => `<option>${escapeHtml(category)}</option>`)
    .join("");
  $("#search").value = params.get("q") || "";
  $("#category").value = categories.includes(params.get("category"))
    ? params.get("category")
    : "";
  function render() {
    const priceField = $("#max-price");
    const max = Number(priceField.value);
    const invalid =
      priceField.value !== "" &&
      (!Number.isFinite(max) || max <= 0 || !Number.isInteger(max));
    $("#price-error").textContent = invalid
      ? "Укажите целую положительную цену."
      : "";
    priceField.setAttribute("aria-invalid", String(invalid));
    priceField.setAttribute("aria-describedby", "price-error");
    if (invalid) return;
    const query = $("#search").value.trim().toLocaleLowerCase("ru");
    let filtered = products.filter(
      (product) =>
        product.name.toLocaleLowerCase("ru").includes(query) &&
        (!$("#category").value || product.category === $("#category").value) &&
        (!max || product.price <= max),
    );
    const sort = $("#sort").value;
    if (sort === "asc") filtered.sort((a, b) => a.price - b.price);
    if (sort === "desc") filtered.sort((a, b) => b.price - a.price);
    if (sort === "name")
      filtered.sort((a, b) => a.name.localeCompare(b.name, "ru"));
    $("#catalog").innerHTML = filtered.length
      ? filtered.map(card).join("")
      : empty(
          "Ничего не нашлось",
          "Попробуйте другую категорию, название или цену.",
        );
    $("#product-count").textContent = `Найдено: ${filtered.length}`;
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    render();
  });
  form.addEventListener("input", render);
  form.addEventListener("change", render);
  render();
}
async function initProduct() {
  const id = new URLSearchParams(location.search).get("id") || "cement";
  const target = $("#product-detail");
  if (!/^[a-z]+$/.test(id)) {
    target.innerHTML =
      "<h1>Материал не найден</h1>" +
      empty("Проверьте ссылку", "Выберите материал из каталога.");
    return;
  }
  try {
    const product = await api(`/products/${id}`);
    document.title = `${product.name} · Строймаркет`;
    target.innerHTML = `<article class="detail-layout"><div class="detail-image"><img src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}"></div><div class="detail-copy"><p class="eyebrow">${escapeHtml(product.category)}</p><h1>${escapeHtml(product.name)}</h1><p>${escapeHtml(product.description)}</p><h2>Характеристики</h2><dl>${Object.entries(
      product.specs,
    )
      .map(
        ([key, value]) =>
          `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`,
      )
      .join(
        "",
      )}</dl><span class="price">${money(product.price)} <small>/ ${escapeHtml(product.unit)}</small></span><button class="button dark" data-add="${product.id}">Добавить в корзину +</button><p><a class="text-link" href="/calculator.html?product=${product.id}">Рассчитать нужное количество ↗</a></p></div></article>`;
  } catch (error) {
    target.innerHTML =
      "<h1>Материал недоступен</h1>" +
      empty(
        "Не удалось открыть карточку",
        error.status === 404
          ? "Такого материала нет в каталоге."
          : "Проверьте соединение и обновите страницу.",
      );
  }
}
function initCalculator() {
  const select = $("#calc-product");
  select.innerHTML += products
    .map(
      (product) =>
        `<option value="${product.id}">${escapeHtml(product.name)}</option>`,
    )
    .join("");
  select.value = new URLSearchParams(location.search).get("product") || "";
  function invalidate() {
    $("#calculation").innerHTML =
      '<span class="large-symbol">м²</span><p>Параметры изменены. Нажмите «Рассчитать количество», чтобы обновить смету.</p>';
  }
  function updateMode() {
    const volume = $("#calc-mode").value === "volume";
    $("#depth-field").hidden = !volume;
    $("#coverage-label").textContent = volume
      ? "Объём одной упаковки, м³"
      : "Площадь покрытия одной упаковки, м²";
    const product = products.find((item) => item.id === select.value);
    $("#coverage").value = volume ? "" : product?.coverage || "";
    invalidate();
  }
  select.addEventListener("change", updateMode);
  $("#calc-mode").addEventListener("change", updateMode);
  $("#calculator").addEventListener("input", invalidate);
  updateMode();
  $("#calculator").addEventListener("submit", (event) => {
    event.preventDefault();
    let valid = showError(
      "calc-product",
      select.value ? "" : "Выберите материал.",
    );
    const values = {};
    for (const [id, min, max] of [
      ["length", 0.01, 1000],
      ["width", 0.01, 1000],
      ["coverage", 0.001, 1000000],
      ["reserve", 0, 50],
      ...($("#calc-mode").value === "volume" ? [["depth", 0.001, 10]] : []),
    ]) {
      const field = $(`#${id}`);
      const value = Number(field.value);
      values[id] = value;
      const ok = showError(
        id,
        field.value !== "" &&
          Number.isFinite(value) &&
          value >= min &&
          value <= max
          ? ""
          : `Введите число от ${min} до ${max}.`,
      );
      valid = ok && valid;
    }
    if (!valid) return;
    const product = products.find((item) => item.id === select.value);
    const volume = $("#calc-mode").value === "volume";
    const size = values.length * values.width * (volume ? values.depth : 1);
    const count = Math.ceil(
      Number(
        ((size * (1 + values.reserve / 100)) / values.coverage).toFixed(8),
      ),
    );
    const addButton =
      count <= 999
        ? `<button class="button dark" data-add="${product.id}" data-quantity="${count}">Добавить расчёт в корзину +</button>`
        : '<p class="notice">Для такого объёма нужно больше 999 упаковок. Разделите проект на этапы.</p>';
    $("#calculation").innerHTML =
      `<p>${escapeHtml(product.name)}</p><strong class="result-number">${count.toLocaleString("ru-RU")} <small>упак.</small></strong><p>${volume ? "Объём" : "Площадь"}: ${size.toLocaleString("ru-RU", { maximumFractionDigits: 4 })} ${volume ? "м³" : "м²"} · Запас ${values.reserve}%</p><h3>Итого: ${money(count * product.price)}</h3>${addButton}`;
  });
}
async function renderCart() {
  const target = $("#cart-content");
  try {
    const cart = await api("/cart");
    cartTotal = cart.total;
    target.innerHTML = cart.items.length
      ? `<div>${cart.items.map(({ product, quantity }) => `<article class="cart-row"><img src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}"><div><h2><a href="/product.html?id=${product.id}">${escapeHtml(product.name)}</a></h2><span class="muted">${money(product.price)} / ${escapeHtml(product.unit)}</span></div><label><span class="sr-only">Количество: ${escapeHtml(product.name)}</span><input data-cart-id="${product.id}" type="number" min="1" max="999" step="1" value="${quantity}"></label><strong class="row-price">${money(product.price * quantity)}</strong><button data-remove="${product.id}">Удалить</button></article>`).join("")}</div><div class="cart-total"><span>Итого <strong class="price">${money(cart.total)}</strong></span><a class="button outline" href="/catalog.html">Продолжить подбор ↗</a></div><p class="muted">Это учебная корзина: оформление заказа и оплата не предусмотрены.</p>`
      : empty(
          "Здесь начнётся ваш проект",
          "Пока корзина пуста. Найдите материалы или начните с калькулятора.",
        );
    updateCurrencyText();
    await refreshCartCount();
  } catch (error) {
    target.innerHTML =
      error.status === 401
        ? empty(
            "Сохраним ваш список?",
            "Войдите или создайте аккаунт, чтобы пользоваться личной корзиной.",
            "/account.html",
            "Войти или зарегистрироваться",
          )
        : empty(
            "Нет связи с сервером",
            "Не удалось загрузить корзину. Обновите страницу.",
          );
  }
}
function updateCurrencyText() {
  if (!usdRate) return;
  $("#exchange-rate").textContent =
    `1 USD = ${usdRate.value.toFixed(2)} ₽ · Курс на ${usdRate.date}.` +
    (cartTotal
      ? ` Ваша корзина: ≈ ${(cartTotal / usdRate.value).toFixed(2)} USD.`
      : "");
}
function initCart() {
  renderCart();
  $("#cart-content").addEventListener("change", async (event) => {
    const input = event.target.closest("[data-cart-id]");
    if (!input) return;
    const quantity = Number(input.value);
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 999) {
      toast("Количество — целое число от 1 до 999.");
      await renderCart();
      return;
    }
    try {
      await api(`/cart/${input.dataset.cartId}`, {
        method: "PUT",
        body: JSON.stringify({ quantity }),
      });
      await renderCart();
    } catch {
      toast("Не удалось изменить количество. Повторите попытку.");
      await renderCart();
    }
  });
  $("#cart-content").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-remove]");
    if (!button) return;
    button.disabled = true;
    try {
      await api(`/cart/${button.dataset.remove}`, { method: "DELETE" });
      await renderCart();
    } catch {
      toast("Не удалось удалить материал.");
      button.disabled = false;
    }
  });
  $("#load-rate").addEventListener("click", async (event) => {
    const button = event.target;
    button.disabled = true;
    $("#exchange-rate").textContent = "Загружаем курс ЦБ РФ…";
    try {
      const response = await fetch(
        "https://www.cbr-xml-daily.ru/daily_json.js",
        { signal: AbortSignal.timeout(10000), cache: "no-store" },
      );
      if (!response.ok) throw new Error("API недоступен");
      const data = await response.json();
      const value = data.Valute?.USD?.Value / data.Valute?.USD?.Nominal;
      const date = new Date(data.Date);
      if (!Number.isFinite(value) || value <= 0 || Number.isNaN(date.getTime()))
        throw new Error("Неверный ответ API");
      usdRate = { value, date: date.toLocaleDateString("ru-RU") };
      updateCurrencyText();
      button.textContent = "Обновить курс";
    } catch {
      usdRate = null;
      $("#exchange-rate").textContent =
        "Не удалось загрузить курс. Проверьте интернет и попробуйте ещё раз. Цены в рублях по-прежнему доступны.";
    } finally {
      button.disabled = false;
    }
  });
}
function validEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) && value.length <= 254;
}
function initContact() {
  $("#contact").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = $("#name").value.trim(),
      email = $("#email").value.trim(),
      message = $("#message").value.trim();
    const checks = [
      showError(
        "name",
        name.length >= 2 && name.length <= 80
          ? ""
          : "Укажите имя длиной от 2 до 80 символов.",
      ),
      showError(
        "email",
        validEmail(email) ? "" : "Укажите корректную электронную почту.",
      ),
      showError(
        "message",
        message.length >= 10 && message.length <= 2000
          ? ""
          : "Сообщение должно содержать от 10 до 2000 символов.",
      ),
    ];
    if (checks.includes(false)) {
      $("#contact-result").textContent = "Проверьте отмеченные поля.";
      return;
    }
    const button = $("button", event.target);
    button.disabled = true;
    try {
      await api("/contact", {
        method: "POST",
        body: JSON.stringify({ name, email, message }),
      });
      $("#contact-result").textContent =
        "Сообщение сохранено в учебной базе. Спасибо!";
      event.target.reset();
    } catch (error) {
      $("#contact-result").textContent = error.status
        ? error.message
        : "Нет связи с сервером. Данные не отправлены.";
    } finally {
      button.disabled = false;
    }
  });
}
async function initAccount() {
  try {
    const user = await api("/auth/me");
    $("#account-content").innerHTML =
      `<section class="panel"><h2>Здравствуйте, ${escapeHtml(user.name)}!</h2><p>${escapeHtml(user.email)}</p><p>Ваша личная корзина хранится в базе и доступна после входа с другого устройства.</p><a class="button dark" href="/cart.html">Моя корзина ↗</a> <button class="button outline" id="logout">Выйти</button></section>`;
    $("#logout").addEventListener("click", async () => {
      try {
        await api("/auth/logout", { method: "POST" });
        location.reload();
      } catch {
        toast("Не удалось выйти. Попробуйте ещё раз.");
      }
    });
    return;
  } catch (error) {
    if (error.status !== 401) {
      toast("Не удалось проверить вход. Проверьте соединение.");
    }
  }
  for (const action of ["login", "register"]) {
    $(`#${action}`).addEventListener("submit", async (event) => {
      event.preventDefault();
      const email = $(`#${action}-email`).value.trim(),
        password = $(`#${action}-password`).value;
      const checks = [
        showError(
          `${action}-email`,
          validEmail(email) ? "" : "Укажите корректную электронную почту.",
        ),
        showError(
          `${action}-password`,
          password.length >= 8 && password.length <= 128
            ? ""
            : "Пароль должен содержать от 8 до 128 символов.",
        ),
      ];
      const body = { email, password };
      if (action === "register") {
        body.name = $("#register-name").value.trim();
        checks.push(
          showError(
            "register-name",
            body.name.length >= 2 && body.name.length <= 80
              ? ""
              : "Укажите имя длиной от 2 до 80 символов.",
          ),
        );
      }
      if (checks.includes(false)) return;
      const button = $("button", event.target);
      button.disabled = true;
      try {
        await api(`/auth/${action}`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        location.reload();
      } catch (error) {
        $(`#${action}-result`).textContent = error.status
          ? error.message
          : "Нет связи с сервером. Попробуйте ещё раз.";
        button.disabled = false;
      }
    });
  }
}
async function main() {
  refreshCartCount();
  const page = document.body.dataset.page;
  if (page === "contacts") return initContact();
  if (page === "account") return initAccount();
  if (page === "cart") return initCart();
  if (page === "product") return initProduct();
  try {
    products = await api("/products");
    if (page === "index")
      $("#featured").innerHTML = products.slice(0, 6).map(card).join("");
    if (page === "catalog") initCatalog();
    if (page === "calculator") initCalculator();
  } catch {
    const target = $("#featured") || $("#catalog") || $("#calculation");
    if (target)
      target.innerHTML = empty(
        "Не удалось загрузить материалы",
        "Проверьте соединение и обновите страницу.",
      );
  }
}
main();
