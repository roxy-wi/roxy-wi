// Keep the existing theme preference without loading the application, its
// background requests or user settings on a potentially failing server.
try {
    if (localStorage.getItem('theme') === 'dark') {
        document.getElementById('error-dark-theme').media = 'all';
        const logo = document.querySelector('.error-brand img');
        logo.src = logo.dataset.darkSrc;
    }
} catch (error) {
    console.warn('Roxy-WI: cannot read the saved theme preference', error.name);
}
