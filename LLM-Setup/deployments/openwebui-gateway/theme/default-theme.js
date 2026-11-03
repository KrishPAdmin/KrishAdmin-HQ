/* Set a first-visit preference only. Existing user theme choices are preserved. */
try {
  if (localStorage.getItem('theme') === null) localStorage.setItem('theme', 'dark');
} catch (_) { /* Native Open WebUI retains its own fallback. */ }
