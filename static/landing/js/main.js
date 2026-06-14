document.addEventListener('DOMContentLoaded', () => {
    // 1. NAVBAR SCROLL EFFECT
    const navbar = document.getElementById('navbar');
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            navbar.classList.add('bg-paper/80', 'backdrop-blur-xl', 'border-b', 'border-borderColor');
            navbar.classList.remove('bg-transparent');
        } else {
            navbar.classList.remove('bg-paper/80', 'backdrop-blur-xl', 'border-b', 'border-borderColor');
            navbar.classList.add('bg-transparent');
        }
    });

    // 2. REVEAL ON SCROLL (IntersectionObserver)
    const revealElements = document.querySelectorAll('.reveal-on-scroll, .animate-reveal');
    const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('reveal-active');
                revealObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    revealElements.forEach(el => revealObserver.observe(el));

    // 3. MOBILE MENU
    const mBtn = document.getElementById('mobileMenuBtn');
    const mMenu = document.getElementById('mobileMenu');
    const mClose = document.getElementById('mobileMenuClose');
    function setMobileMenu(open) {
        if (!mMenu || !mBtn) return;
        mMenu.classList.toggle('hidden', !open);
        mMenu.classList.toggle('flex', open);
        mBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
        document.body.style.overflow = open ? 'hidden' : '';
    }
    if (mBtn) mBtn.addEventListener('click', () => setMobileMenu(true));
    if (mClose) mClose.addEventListener('click', () => setMobileMenu(false));
    document.querySelectorAll('.mobile-link').forEach(l => l.addEventListener('click', () => setMobileMenu(false)));

    // 4. BUTTON ACTIVE EFFECT
    const buttons = document.querySelectorAll('a, button');
    buttons.forEach(btn => {
        btn.addEventListener('mousedown', () => btn.style.transform = 'scale(0.98)');
        btn.addEventListener('mouseup', () => btn.style.transform = '');
        btn.addEventListener('mouseleave', () => btn.style.transform = '');
    });
});
