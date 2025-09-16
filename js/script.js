async function fetchNews() {
    let rssUrl = "https://news.google.com/rss/search?q=Казахстан&hl=ru&gl=KZ&ceid=KZ:ru";
    let apiUrl = `https://api.allorigins.win/get?url=${encodeURIComponent(rssUrl)}`;

    try {
        let response = await fetch(apiUrl);
        let data = await response.json();
        let parser = new DOMParser();
        let xml = parser.parseFromString(data.contents, "text/xml");

        let items = xml.querySelectorAll("item");
        let newsContainer = document.getElementById("newsContainer");
        newsContainer.innerHTML = "";

        items.forEach((item, index) => {
            if (index < 10) { // Показываем 10 новостей
                let title = item.querySelector("title").textContent;
                let link = item.querySelector("link").textContent;
                let description = item.querySelector("description")?.textContent || "";
                let imageUrl = "img/default-news.jpg"; // Фон по умолчанию
                
                let enclosure = item.querySelector("enclosure");
                if (enclosure && enclosure.getAttribute("type").startsWith("image")) {
                    imageUrl = enclosure.getAttribute("url");
                }

                let card = document.createElement("div");
                card.className = "news-card";
                card.innerHTML = `
                    <img src="${imageUrl}" alt="News">
                    <h3>${title}</h3>
                    <p>${description}</p>
                    <a href="${link}" target="_blank">Читать далее</a>
                `;
                newsContainer.appendChild(card);
            }
        });
    } catch (error) {
        console.error("Ошибка загрузки новостей:", error);
    }
}

fetchNews();
setInterval(fetchNews, 30000); // Автообновление каждые 5 минут
