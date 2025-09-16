const apiKey = 'api_live_ZOcy7l5KQhnKaCKedaAj7fpXfe0G0DW79WmNgIHftp1P8mmh0vX';  // Вставьте ваш реальный ключ API сюда

async function fetchNews() {
    try {
        const response = await fetch(`https://newsapi.org/v2/top-headlines?country=ru&apiKey=${apiKey}`);
        const data = await response.json();
        
        if (data.status === 'ok' && data.articles.length > 0) {
            displayNews(data.articles);
        } else {
            newsContainer.innerHTML = '<p>Нет новостей для отображения.</p>';
        }
    } catch (error) {
        newsContainer.innerHTML = '<p>Ошибка при загрузке новостей. Пожалуйста, попробуйте снова.</p>';
        console.error('Ошибка загрузки новостей:', error);
    }
}
