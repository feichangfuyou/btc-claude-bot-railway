const _warn = console.warn;
console.warn = (...args) => {
  if (args[0]?.includes?.("defineLocale") && args[0]?.includes?.("updateLocale")) return;
  if (args[0]?.includes?.("Lit is in dev mode")) return;
  if (args[0]?.includes?.("CORS")) return;
  _warn.apply(console, args);
};

const _error = console.error;
console.error = (...args) => {
  if (args[0]?.includes?.("locales.getpip.com")) return;
  if (args[0]?.includes?.("Failed to load resource: the server responded with a status of 404")) return;
  if (args[0]?.includes?.("403")) return;
  _error.apply(console, args);
};
