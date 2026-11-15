// Единственный внешний запрос. Каталог и калькулятор не зависят от его результата.
const currencyProduct = document.querySelector('#currency-product');
const currencyCode = document.querySelector('#currency-code');
const currencyReload = document.querySelector('#currency-reload');
const currencyStatus = document.querySelector('#currency-status');
const currencyResult = document.querySelector('#currency-result');
let exchangeRates = null;

for (const card of document.querySelectorAll('.product-card')) {
  const name = card.querySelector('h3').textContent.trim();
  const unit = card.querySelector('.unit').textContent.trim();
  currencyProduct.add(new Option(`${name} — ${unit}`, card.dataset.price));
}
currencyProduct.disabled = false;
currencyCode.disabled = false;

function updateCurrencyPrice() {
  currencyResult.textContent = '';
  if (!exchangeRates) return;
  const currency = currencyCode.value;
  const rate = exchangeRates.Valute[currency];
  const rubles = Number(currencyProduct.value);
  const converted = rubles * rate.Nominal / rate.Value;
  const price = new Intl.NumberFormat('ru-RU', { style: 'currency', currency }).format(converted);
  currencyResult.textContent = `${rubles} ₽ ≈ ${price} за единицу продажи. ${rate.Nominal} ${currency} = ${rate.Value} ₽.`;
}

function validateExchangeRates(data) {
  if (!data || typeof data.Date !== 'string' || !Number.isFinite(Date.parse(data.Date))) return false;
  return ['USD', 'EUR'].every((code) => {
    const rate = data.Valute?.[code];
    return rate && Number.isFinite(rate.Value) && rate.Value > 0 && Number.isFinite(rate.Nominal) && rate.Nominal > 0;
  });
}

async function loadExchangeRates() {
  currencyReload.disabled = true;
  exchangeRates = null;
  currencyResult.textContent = '';
  currencyStatus.textContent = 'Загрузка курсов валют…';
  currencyStatus.setAttribute('aria-busy', 'true');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch('https://www.cbr-xml-daily.ru/daily_json.js', { signal: controller.signal, cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!validateExchangeRates(data)) throw new Error('Неверный формат ответа');
    exchangeRates = data;
    const date = new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow' }).format(new Date(data.Date));
    currencyStatus.textContent = `Курсы загружены. Дата курса: ${date}.`;
    updateCurrencyPrice();
  } catch (error) {
    currencyStatus.textContent = error.name === 'AbortError'
      ? 'Источник не ответил за 10 секунд. Повторите загрузку. Каталог и калькулятор доступны.'
      : 'Не удалось загрузить курсы. Проверьте подключение и повторите загрузку. Каталог и калькулятор доступны.';
  } finally {
    clearTimeout(timeout);
    currencyStatus.setAttribute('aria-busy', 'false');
    currencyReload.textContent = 'Повторить загрузку курсов';
    // Ограничение сервиса: не более одного запроса в секунду.
    setTimeout(() => { currencyReload.disabled = false; }, 1100);
  }
}

currencyProduct.addEventListener('change', updateCurrencyPrice);
currencyCode.addEventListener('change', updateCurrencyPrice);
currencyReload.addEventListener('click', loadExchangeRates);
loadExchangeRates();
