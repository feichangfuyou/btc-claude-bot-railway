const _warn = console.warn;
console.warn = (...args) => {
  if (args[0]?.includes?.("defineLocale") && args[0]?.includes?.("updateLocale")) return;
  _warn.apply(console, args);
};
