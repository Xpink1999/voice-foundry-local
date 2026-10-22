// Apply before the stylesheet paints. System/browser changes remain live in automatic mode.
(() => {
  const key = 'voice-foundry-theme';
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const modes = new Set(['system', 'light', 'dark']);
  let preference = 'system';
  try {
    const stored = localStorage.getItem(key);
    if (modes.has(stored)) preference = stored;
  } catch { /* Storage may be disabled; theme still works for this page. */ }
  function render() {
    document.documentElement.dataset.theme = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference;
    document.documentElement.dataset.themePreference = preference;
    window.dispatchEvent(new CustomEvent('voice-theme-change', {detail:{preference, theme:document.documentElement.dataset.theme}}));
  }
  window.voiceTheme = {
    get preference() { return preference; },
    set(mode) {
      if (!modes.has(mode)) return;
      preference = mode;
      try { localStorage.setItem(key, mode); } catch { /* Keep session preference. */ }
      render();
    }
  };
  media.addEventListener('change', () => { if (preference === 'system') render(); });
  window.addEventListener('storage', event => {
    if (event.key === key) {
      preference = modes.has(event.newValue) ? event.newValue : 'system';
      render();
    }
  });
  render();
})();
