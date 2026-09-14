document.querySelectorAll('.doc h2').forEach((heading) => {
  if (heading.id) return;
  const text = heading.textContent || '';
  const id = text.trim().toLowerCase().replace(/\s+/g, '-').replace(/[^\w\u4e00-\u9fff-]/g, '');
  if (id) heading.id = id;
});
