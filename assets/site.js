const year = document.getElementById('year');
if (year) year.textContent = new Date().getFullYear();

const nav = document.getElementById('mainNav');
document.querySelectorAll('#mainNav a:not(.dropdown-toggle)').forEach((link) => {
  link.addEventListener('click', () => {
    if (nav?.classList.contains('show')) bootstrap.Collapse.getOrCreateInstance(nav).hide();
  });
});
