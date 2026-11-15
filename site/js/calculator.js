// Размеры переведены из миллиметров в метры; покрытие — на единицу продажи.
// Для утеплителя берём заявленные производителем 9 м² на упаковку.
const materials = {
  drywall: { name: 'Vetonit Стронг — лист', coverage: 2.5 * 1.2, unit: 'м²', sale: 'листов', note: '2500 × 1200 мм: 3 м² на лист, один слой.' },
  'drywall-knauf': { name: 'Knauf влагостойкий — лист', coverage: 1.5 * 0.6, unit: 'м²', sale: 'листов', note: '1500 × 600 мм: 0,9 м² на лист, один слой.' },
  'drywall-multicomfort': { name: 'Vetonit Мультикомфорт — лист', coverage: 2.5 * 1.2, unit: 'м²', sale: 'листов', note: '2500 × 1200 мм: 3 м² на лист, один слой.' },
  'drywall-wind': { name: 'Vetonit ветрозащитный — лист', coverage: 3 * 1.2, unit: 'м²', sale: 'листов', note: '3000 × 1200 мм: 3,6 м² на лист, один слой.' },
  plywood: { name: 'Фанера ФК 12 мм — лист', coverage: 1.525 * 1.525, unit: 'м²', sale: 'листов', note: '1525 × 1525 мм: 2,325625 м² на лист, один слой.' },
  insulation: { name: 'ТеплоKnauf 100 мм — упаковка', coverage: 9, unit: 'м²', sale: 'упаковок', note: '9 м² на упаковку при толщине 100 мм.' },
  brick: { name: 'Кирпич ЛСР М150 — штука', coverage: 0.25 * 0.12 * 0.065, unit: 'м³', sale: 'штук', note: '250 × 120 × 65 мм: 0,00195 м³ на штуку. Объём изделий, без швов.' },
  block: { name: 'Газобетон ЛСР D400 — штука', coverage: 0.15 * 0.25 * 0.625, unit: 'м³', sale: 'штук', note: '150 × 250 × 625 мм: 0,0234375 м³ на штуку. Объём изделий, без швов.' },
  board: { name: 'Доска 50 × 150 × 6000 мм — штука', coverage: 0.05 * 0.15 * 6, unit: 'м³', sale: 'штук', note: '50 × 150 × 6000 мм: 0,045 м³ на штуку.' }
};
const calculatorForm = document.querySelector('#calculator-form');
const materialField = document.querySelector('#material');
const amountField = document.querySelector('#amount');
const reserveField = document.querySelector('#reserve');
const calculatorResult = document.querySelector('#calculator-result');
const numberFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 8 });

for (const [id, material] of Object.entries(materials)) {
  materialField.add(new Option(material.name, id));
}

function updateMaterial() {
  const material = materials[materialField.value];
  document.querySelector('#material-note').textContent = material.note;
  document.querySelector('#amount-label').textContent = material.unit === 'м²' ? 'Площадь, м²' : 'Объём изделий, м³';
  calculatorResult.textContent = '';
}

function readDecimal(field, maxDecimals, min, max, allowMin) {
  const text = field.value.trim().replace(',', '.');
  const value = Number(text);
  const validFormat = new RegExp(`^\\d+(?:\\.\\d{1,${maxDecimals}})?$`).test(text);
  const valid = validFormat && Number.isFinite(value) && (allowMin ? value >= min : value > min) && value <= max;
  const error = valid ? '' : (field === amountField
    ? 'Введите число больше 0 и до 10 000 включительно, до 6 знаков после разделителя.'
    : 'Введите запас от 0 до 50 %, до 2 знаков после разделителя.');
  document.querySelector(`#${field.id}-error`).textContent = error;
  field.setAttribute('aria-invalid', String(!valid));
  return valid ? value : null;
}

function calculateQuantity(amount, reserve, coverage) {
  const rawQuantity = amount * (1 + reserve / 100) / coverage;
  // Убираем только машинную погрешность возле целого числа (например, 3 / 0.9).
  const nearestInteger = Math.round(rawQuantity);
  const tolerance = Number.EPSILON * Math.max(1, rawQuantity) * 8;
  return Math.abs(rawQuantity - nearestInteger) <= tolerance
    ? Math.max(1, nearestInteger) : Math.ceil(rawQuantity);
}

calculatorForm.addEventListener('submit', (event) => {
  event.preventDefault();
  calculatorResult.textContent = '';
  const amount = readDecimal(amountField, 6, 0, 10000, false);
  const reserve = readDecimal(reserveField, 2, 0, 50, true);
  if (amount === null || reserve === null) {
    (amount === null ? amountField : reserveField).focus();
    return;
  }
  const material = materials[materialField.value];
  const quantity = calculateQuantity(amount, reserve, material.coverage);
  calculatorResult.textContent = `Количество ${material.sale}: ${quantity}. Расчёт: ${numberFormat.format(amount)} × (1 + ${numberFormat.format(reserve)} / 100) / ${numberFormat.format(material.coverage)}, округление вверх. Покрытие или объём покупки: ${numberFormat.format(quantity * material.coverage)} ${material.unit}.`;
});
calculatorForm.addEventListener('input', () => { calculatorResult.textContent = ''; });
materialField.addEventListener('change', updateMaterial);
updateMaterial();
calculatorForm.querySelector('button').disabled = false;
