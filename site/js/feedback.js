const feedbackForm = document.querySelector('#feedback-form');
const feedbackResult = document.querySelector('#feedback-result');
feedbackForm.querySelector('button').disabled = false;

function validateFeedbackField(field) {
  const value = field.value.trim();
  let error = '';
  if (field.id === 'name' && (value.length < 2 || value.length > 80)) {
    error = 'Введите имя от 2 до 80 символов без пробелов по краям.';
  } else if (field.id === 'email' && (!value || value.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) || field.validity.typeMismatch)) {
    error = 'Введите email в формате name@example.ru (до 254 символов).';
  } else if (field.id === 'message' && (value.length < 10 || value.length > 2000)) {
    error = 'Введите сообщение от 10 до 2000 символов без пробелов по краям.';
  }
  document.querySelector(`#${field.id}-error`).textContent = error;
  field.setAttribute('aria-invalid', String(Boolean(error)));
  return !error;
}

feedbackForm.addEventListener('submit', (event) => {
  event.preventDefault();
  feedbackResult.textContent = '';
  let firstInvalid = null;
  for (const id of ['name', 'email', 'message']) {
    const field = document.getElementById(id);
    if (!validateFeedbackField(field) && !firstInvalid) firstInvalid = field;
  }
  if (firstInvalid) {
    firstInvalid.focus();
    return;
  }
  feedbackResult.textContent = 'Проверка пройдена. Сообщение не отправлено и не сохранено: это учебная форма ПР 2.';
});

feedbackForm.addEventListener('input', (event) => {
  feedbackResult.textContent = '';
  if (event.target.hasAttribute('aria-invalid')) validateFeedbackField(event.target);
});
feedbackForm.addEventListener('change', () => { feedbackResult.textContent = ''; });
