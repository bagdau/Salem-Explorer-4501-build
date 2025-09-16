document.addEventListener("DOMContentLoaded", function () {
    const toggle = document.getElementById("toggleNotifications");

    // Проверяем сохраненное состояние уведомлений
    let notificationsEnabled = localStorage.getItem("notifications") === "true";
    toggle.checked = notificationsEnabled;

    toggle.addEventListener("change", function () {
        notificationsEnabled = this.checked;
        localStorage.setItem("notifications", notificationsEnabled);
    });

    function showToast(message) {
        if (!notificationsEnabled) return;

        let toastContainer = document.getElementById("toastContainer");

        let toast = document.createElement("div");
        toast.classList.add("toast");
        toast.innerHTML = `
            <span>${message}</span>
            <button onclick="this.parentElement.remove()">✖</button>
        `;

        toastContainer.appendChild(toast);

        // Воспроизведение звука
        let sound = document.getElementById("notificationSound");
        sound.play();

        // Автоматическое скрытие через 4 секунды
        setTimeout(() => {
            toast.style.animation = "fadeOut 0.5s ease-in-out forwards";
            setTimeout(() => toast.remove(), 500);
        }, 4000);
    }

    // Тестовое уведомление через 2 секунды
    setTimeout(() => showToast("🔔 Уведомление: Новости обновлены!"), 2000);
});