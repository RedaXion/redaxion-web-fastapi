// Main JS for RedaXion
console.log('RedaXion Frontend Loaded');

// Add scroll effect to header
window.addEventListener('scroll', () => {
    const header = document.querySelector('header');
    if (window.scrollY > 50) {
        header.style.background = 'rgba(20, 31, 43, 0.95)';
    } else {
        header.style.background = 'rgba(20, 31, 43, 0.8)';
    }
});
