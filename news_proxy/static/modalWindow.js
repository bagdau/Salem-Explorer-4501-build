// Открыть модалку по клику на addButton
document.getElementById('addButton').onclick = function(e) {
  e.stopPropagation();
  document.getElementById('addModal').style.display = 'flex';
  // Сброс полей
  document.getElementById('newAppName').value = '';
  document.getElementById('newAppUrl').value = '';
  document.getElementById('newAppIcon').value = '';
  document.getElementById('newAppName').focus();
};

// Закрыть модалку
function closeAddModal() {
  document.getElementById('addModal').style.display = 'none';
}

// Добавить новое приложение
function addCustomApp() {
  const name = document.getElementById('newAppName').value.trim();
  const url = document.getElementById('newAppUrl').value.trim();
  const icon = document.getElementById('newAppIcon').value.trim() || 'https://officialcorporationsalem.kz/iconsSalemBrowser/app-default.svg';
  if (!name || !url) {
    alert('Атауын және сілтемесін толтырыңыз!');
    return;
  }

  // Добавляем ярлык в DOM (icons)
  const iconsBlock = document.querySelector('.icons');
  const a = document.createElement('a');
  a.className = 'icon-btn';
  a.href = url;
  a.target = '_blank';

  const img = document.createElement('img');
  img.src = icon;
  img.alt = name;
  a.appendChild(img);

  // Текст под иконкой (опционально)
  // const span = document.createElement('span');
  // span.textContent = name;
  // span.style = "display:block;color:#fff;font-size:0.95em;margin-top:5px;text-align:center;";
  // a.appendChild(span);

  iconsBlock.appendChild(a);

  closeAddModal();
}

// Клик вне модалки закрывает её
document.getElementById('addModal').addEventListener('click', function(e){
  if (e.target === this) closeAddModal();
});

// Не даём исчезнуть addButton
// (Кнопка "➕" всегда на месте)
