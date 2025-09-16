document.addEventListener('DOMContentLoaded', function () {
    const backgroundOptions = document.getElementById('backgroundOptions');
    
    if (!backgroundOptions) {
        console.error("❌ Ошибка: контейнер backgroundOptions не найден!");
        return;
    }

    document.getElementById('overlay').addEventListener('click', closeSettings);

    const backgrounds = [
        'img/Степь.jpeg',
        'img/GreenField.jpg.jpg',
        'img/BigAlmaty.jpg',
        'img/MinPhoto.png'
    ];

    function setBackground(src, element) {
        localStorage.setItem('selectedBackground', src);
        document.querySelectorAll('.background-option').forEach(el => el.classList.remove('selected'));
        element.classList.add('selected');
        applySettings();
    }

    function applySettings() {
        const selectedBackground = localStorage.getItem('selectedBackground');
        if (selectedBackground) {
            document.body.style.backgroundImage = `url('${selectedBackground}')`;
            document.body.style.backgroundRepeat = "no-repeat";
            document.body.style.backgroundSize = "cover";
            document.body.style.backgroundPosition = "center";
        }
    }

    backgrounds.forEach(src => {
        const div = document.createElement('div');
        div.classList.add('background-option');
        div.innerHTML = `
            <input type="radio" name="background" value="${src}">
            <img src="${src}" alt="Фон">
        `;
        div.onclick = () => setBackground(src, div);
        backgroundOptions.appendChild(div);
    });

    // Применяем сохранённые настройки при загрузке страницы
    applySettings();
});