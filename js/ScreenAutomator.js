function adjustLayout() {
    let screenWidth = window.innerWidth;
    let container = document.querySelector('.container');
    
    if (screenWidth < 768) {
        container.style.flexDirection = 'column';
        container.style.height = 'auto';
    } else {
        container.style.flexDirection = 'column';
        container.style.height = '100vh';
    }
}

window.addEventListener('resize', adjustLayout);
window.addEventListener('load', adjustLayout);