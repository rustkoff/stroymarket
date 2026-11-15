// Карточки остаются в HTML. JavaScript меняет только порядок и видимость.
const filterForm = document.querySelector('#catalog-filters');
const productGrid = document.querySelector('.product-grid');
const productCards = Array.from(productGrid.querySelectorAll('.product-card'));
const searchField = document.querySelector('#search');
const categoryField = document.querySelector('#category');
const sortField = document.querySelector('#sort');
filterForm.querySelector('fieldset').disabled = false;

function normalizeSearch(text) {
  return text.trim().toLocaleLowerCase('ru').replaceAll('ё', 'е');
}

function updateCatalog() {
  const search = normalizeSearch(searchField.value);
  const category = categoryField.value;
  const sortedCards = [...productCards];
  if (sortField.value === 'price-asc') {
    sortedCards.sort((a, b) => Number(a.dataset.price) - Number(b.dataset.price));
  } else if (sortField.value === 'price-desc') {
    sortedCards.sort((a, b) => Number(b.dataset.price) - Number(a.dataset.price));
  }
  let visibleCount = 0;
  for (const card of sortedCards) {
    const nameMatches = normalizeSearch(card.querySelector('h3').textContent).includes(search);
    const categoryMatches = category === 'all' || card.querySelector('.category').textContent.trim() === category;
    card.hidden = !(nameMatches && categoryMatches);
    if (!card.hidden) visibleCount += 1;
    productGrid.append(card);
  }
  document.querySelector('#catalog-status').textContent = `Показано товаров: ${visibleCount} из ${productCards.length}.`;
  document.querySelector('#catalog-empty').hidden = visibleCount !== 0;
}

filterForm.addEventListener('submit', (event) => {
  event.preventDefault();
  updateCatalog();
});
searchField.addEventListener('input', updateCatalog);
categoryField.addEventListener('change', updateCatalog);
sortField.addEventListener('change', updateCatalog);
// reset сначала посылает событие, а затем восстанавливает значения полей.
filterForm.addEventListener('reset', () => setTimeout(updateCatalog, 0));
