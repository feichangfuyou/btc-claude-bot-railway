if (window.Capacitor) {
  import("@capacitor/status-bar").then(({ StatusBar, Style }) => {
    StatusBar.setStyle({ style: Style.Dark }).catch(() => {});
    StatusBar.setBackgroundColor({ color: "#0A0A0A" }).catch(() => {});
  }).catch(() => {});
  import("@capacitor/keyboard").then(({ Keyboard }) => {
    Keyboard.setAccessoryBarVisible({ isVisible: false }).catch(() => {});
  }).catch(() => {});
}
