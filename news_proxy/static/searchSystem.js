// === Search Redirect Method ===
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-button');

searchBtn.onclick = function() {
  const query = searchInput.value.trim();
  if (query) {
    window.location.href = "https://www.google.com/search?q=" + encodeURIComponent(query);
  }
};

searchInput.addEventListener('keypress', function(e) {
  if (e.key === 'Enter') searchBtn.onclick();
});
