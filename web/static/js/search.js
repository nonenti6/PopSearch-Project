// Воспроизведение YouTube с делегированием событий: работает и для новых карточек.
document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-play]');
  if (!button) return;
  const frame = button.closest('.video-frame');
  const id = frame && frame.dataset.videoId;
  if (!id || !/^[a-zA-Z0-9_-]{11}$/.test(id)) return;
  const iframe = document.createElement('iframe');
  iframe.src = `https://www.youtube-nocookie.com/embed/${id}?autoplay=1`;
  iframe.title = 'Видеоплеер YouTube';
  iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
  iframe.allowFullscreen = true;
  iframe.referrerPolicy = 'strict-origin-when-cross-origin';
  frame.replaceChildren(iframe);
});

// Подгрузка десяти следующих результатов без перезагрузки страницы.
// Flask по-прежнему отдаёт HTML по параметру show, поэтому отдельный API не нужен.
const loadMoreForm = document.querySelector('form.load-more');
if (loadMoreForm) {
  let loading = false;
  const resultsSelector = {
    all: '.search-feed',
    artists: '.results-section .stack',
    albums: '.results-section .tile-grid',
    songs: '.results-section .song-list',
    video: '.results-section .media-grid',
    image: '.results-section .media-grid',
  };
  const itemSelector = {
    all: ':scope > .feed-result',
    artists: ':scope > .result-card',
    albums: ':scope > .result-card',
    songs: ':scope > .song-row',
    video: ':scope > .result-card',
    image: ':scope > .result-card',
  };

  loadMoreForm.addEventListener('submit', async (event) => {
    const category = loadMoreForm.elements.namedItem('type')?.value || 'all';
    const containerSelector = resultsSelector[category];
    const cardSelector = itemSelector[category];
    const container = containerSelector && document.querySelector(containerSelector);
    // Если страница имеет неожиданную структуру, сохраняем обычный submit формы.
    if ((category !== 'publications' && (!container || !cardSelector)) || loading) {
      if (loading) event.preventDefault();
      return;
    }
    event.preventDefault();
    loading = true;
    const button = loadMoreForm.querySelector('button[type="submit"]');
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = 'Загружаем результаты…';

    try {
      const url = new URL(loadMoreForm.action, window.location.href);
      new FormData(loadMoreForm).forEach((value, key) => url.searchParams.set(key, value));
      const response = await fetch(url, { headers: { Accept: 'text/html' } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const page = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (page.querySelector('.notice.error')) throw new Error('Сервер вернул ошибку поиска');
      const nextContainer = page.querySelector(containerSelector);
      if (category !== 'publications' && !nextContainer) throw new Error('Не найден блок результатов в ответе');

      if (category === 'publications') {
        const sectionTitle = section => section.querySelector('h2')?.textContent?.trim();
        const currentSections = Array.from(document.querySelectorAll('.results-section'));
        const freshSections = Array.from(page.querySelectorAll('.results-section'));
        for (const fresh of freshSections) {
          const heading = sectionTitle(fresh);
          if (!['Об исполнителе', 'Свежие новости'].includes(heading)) continue;
          const current = currentSections.find(section => sectionTitle(section) === heading);
          const freshStack = fresh.querySelector('.stack');
          if (!freshStack) continue;
          if (!current) {
            const anchor = document.querySelector('form.load-more');
            anchor.before(document.importNode(fresh, true));
            continue;
          }
          const currentStack = current.querySelector('.stack');
          if (!currentStack) {
            const existingNotice = current.querySelector('.news-info');
            if (existingNotice) existingNotice.remove();
            current.appendChild(document.importNode(freshStack, true));
            continue;
          }
          const alreadyShown = currentStack.querySelectorAll(':scope > .feed-result').length;
          Array.from(freshStack.querySelectorAll(':scope > .feed-result'))
            .slice(alreadyShown)
            .forEach(card => currentStack.appendChild(document.importNode(card, true)));
        }
      } else {
        const alreadyShown = container.querySelectorAll(cardSelector).length;
        const nextCards = Array.from(nextContainer.querySelectorAll(cardSelector)).slice(alreadyShown);
        if (nextCards.length === 0 && page.querySelector('form.load-more')) {
          throw new Error('Новые результаты пока недоступны');
        }
        const fragment = document.createDocumentFragment();
        nextCards.forEach((card) => fragment.appendChild(document.importNode(card, true)));
        container.appendChild(fragment);
      }

      const nextIntro = page.querySelector('.results-intro p');
      const currentIntro = document.querySelector('.results-intro p');
      if (nextIntro && currentIntro) currentIntro.textContent = nextIntro.textContent;

      const nextForm = page.querySelector('form.load-more');
      if (nextForm) {
        const nextShow = nextForm.querySelector('input[name="show"]')?.value;
        if (nextShow) loadMoreForm.querySelector('input[name="show"]').value = nextShow;
      } else {
        loadMoreForm.remove();
      }
      // Не меняем адрес страницы и не вызываем scrollTo: прокрутка остаётся прежней.
    } catch (error) {
      console.error('PopSearch: загрузка дополнительных результатов', error);
      button.textContent = 'Не удалось загрузить. Повторить ↓';
      return;
    } finally {
      loading = false;
      button.disabled = false;
      if (button.textContent === 'Загружаем результаты…') button.textContent = originalText;
    }
  });
}


// Полноэкранная фотогалерея. Делегирование событий также поддерживает карточки, добавленные кнопкой «Показать ещё».
(() => {
  const lightbox = document.getElementById('photo-lightbox');
  if (!lightbox) return;
  const photo = lightbox.querySelector('.photo-lightbox-image');
  const source = lightbox.querySelector('.photo-lightbox-source');
  const previousButton = lightbox.querySelector('[data-photo-prev]');
  const nextButton = lightbox.querySelector('[data-photo-next]');
  const closeButton = lightbox.querySelector('[data-photo-close]');
  const counter = lightbox.querySelector('.photo-lightbox-counter');
  let index = -1;
  let previousFocus = null;
  let startX = null;

  const getPhotos = () => Array.from(document.querySelectorAll('.image-gallery [data-photo-open]'))
    .filter((button) => !button.closest('.photo-unavailable'));

  function render() {
    const items = getPhotos();
    if (!items.length) { close(); return; }
    index = Math.min(Math.max(index, 0), items.length - 1);
    const item = items[index];
    photo.src = item.dataset.fullSrc;
    photo.alt = item.dataset.photoAlt || 'Фотография';
    source.href = item.dataset.sourceUrl || item.dataset.fullSrc;
    counter.textContent = `${index + 1} / ${items.length}`;
    previousButton.disabled = index === 0;
    nextButton.disabled = index === items.length - 1;
  }

  function open(button) {
    if (button.closest('.photo-unavailable')) return;
    index = getPhotos().indexOf(button);
    if (index < 0) return;
    previousFocus = document.activeElement;
    lightbox.hidden = false;
    lightbox.setAttribute('aria-hidden', 'false');
    document.body.classList.add('photo-lightbox-active');
    render();
    closeButton.focus();
  }

  function close() {
    lightbox.hidden = true;
    lightbox.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('photo-lightbox-active');
    photo.removeAttribute('src');
    if (previousFocus?.isConnected) previousFocus.focus();
    index = -1;
  }

  function move(delta) {
    const target = index + delta;
    if (target >= 0 && target < getPhotos().length) { index = target; render(); }
  }

  document.addEventListener('click', (event) => {
    const opener = event.target.closest('[data-photo-open]');
    if (opener) open(opener);
  });
  closeButton.addEventListener('click', close);
  previousButton.addEventListener('click', () => move(-1));
  nextButton.addEventListener('click', () => move(1));
  lightbox.addEventListener('click', (event) => { if (event.target === lightbox || event.target === lightbox.querySelector('.photo-lightbox-body')) close(); });
  photo.addEventListener('error', () => { photo.alt = 'Не удалось загрузить фотографию'; });
  document.addEventListener('keydown', (event) => {
    if (lightbox.hidden) return;
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    else if (event.key === 'ArrowLeft') { event.preventDefault(); move(-1); }
    else if (event.key === 'ArrowRight') { event.preventDefault(); move(1); }
    else if (event.key === 'Tab') {
      const controls = [source, closeButton, previousButton, nextButton].filter((el) => !el.disabled);
      const current = controls.indexOf(document.activeElement);
      if (current === -1) { event.preventDefault(); closeButton.focus(); }
      else if (event.shiftKey && current === 0) { event.preventDefault(); controls[controls.length - 1].focus(); }
      else if (!event.shiftKey && current === controls.length - 1) { event.preventDefault(); controls[0].focus(); }
    }
  });
  photo.addEventListener('touchstart', (event) => { startX = event.changedTouches[0]?.screenX ?? null; }, { passive: true });
  photo.addEventListener('touchend', (event) => {
    if (startX === null) return;
    const distance = (event.changedTouches[0]?.screenX ?? startX) - startX;
    if (Math.abs(distance) > 45) move(distance < 0 ? 1 : -1);
    startX = null;
  }, { passive: true });
})();
