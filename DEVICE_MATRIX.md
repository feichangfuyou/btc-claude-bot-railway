# Device Matrix: App Store & Play Store Readiness

Research-backed coverage for **all major devices** (Apple, Android, tablets, foldables) so ClaudeBot works **on the go**.

---

## Breakpoint Strategy (3 Sizes)

| Breakpoint | Width | Target Devices |
|------------|-------|----------------|
| **Desktop** | > 1024px | Laptops, desktops, iPad Pro landscape |
| **Tablet** | 601–1024px | iPad, iPad Mini, iPad Air, Android tablets, Z Fold inner |
| **Phone** | ≤ 600px | iPhones, Android phones, Z Fold/Z Flip cover |
| **Narrow** | ≤ 400px | Z Fold cover (323px), Galaxy S25 (360px), legacy |

---

## Apple (App Store / Add to Home Screen)

### iPhones (CSS viewport width)

| Model | Viewport | Notes |
|-------|----------|-------|
| iPhone 17 Pro Max | 440 × 956 | Largest |
| iPhone 17 / 16 | 402 × 874 | |
| iPhone 16e | 390 × 844 | |
| iPhone 16 Plus | 428 × 926 | |
| iPhone SE (3rd gen) | 375 × 667 | Smallest width |
| iPhone 12/13 mini | 375 × 812 | |

**Range:** 375px – 440px width. All covered by phone layout (≤600px).

### iPads

| Model | Portrait | Landscape | Notes |
|-------|----------|-----------|-------|
| iPad Pro 12.9" | 1024 × 1366 | 1366 × 1024 | Tablet/Desktop |
| iPad Air 10.9" | 820 × 1180 | 1180 × 820 | Tablet |
| iPad Mini (7th gen) | 744 × 1133 | 1133 × 744 | Tablet |

**Note:** Apple App Store does **not** accept PWAs. Use **Add to Home Screen** from Safari for app-like install on iPhone/iPad.

---

## Android (Play Store / Add to Home Screen)

### Phones (CSS viewport width)

| Model | Viewport | Notes |
|-------|----------|-------|
| Pixel 10 Pro XL | 414 × 921 | |
| Pixel 10 / 9 | 412 × 923 | |
| Samsung S25 Ultra | 412 × 891 | |
| Samsung S25 / S24 | 360 × 780 | Smallest flagship |
| Samsung S23+ | 384 × 854 | |
| Z Fold6 cover | **323 × 792** | Narrowest modern phone |
| Z Flip6 | 393 × 960 | |
| Legacy minimum | **320px** | Android CDD floor |

**Range:** 320px – 414px. Phone layout + narrow tweaks cover this.

### Foldables

| Device | Cover Screen | Inner Screen | Notes |
|--------|-------------|-------------|-------|
| Samsung Z Fold6 | 323 × 792 | 619 × 720 | Cover = phone, inner = tablet |
| Pixel 10 Pro Fold | 412 × 923 | 692 × 717 | Both layouts supported |

### Tablets

| Type | Width | Notes |
|------|-------|-------|
| 7"–8" | ~600–768px | Tablet breakpoint |
| 10"+ | 768–1024px+ | Tablet/Desktop |

---

## Store Distribution Reality

| Store | PWA Support | How to Publish |
|-------|------------|----------------|
| **Apple App Store** | ❌ No | Add to Home Screen from Safari, or use native wrapper (e.g. PWABuilder → Capacitor) |
| **Google Play Store** | ✅ Yes (TWA) | Use [PWABuilder](https://www.pwabuilder.com) to package as Trusted Web Activity |
| **Add to Home Screen** | ✅ Both | Works with manifest + icons (already configured) |

---

## PWA Requirements (Met ✓)

- [x] **Manifest** (`/manifest.json`) – name, icons, display, theme
- [x] **Icons** – 192×192 and 512×512 PNG
- [x] **Apple Touch Icon** – for Add to Home Screen
- [x] **Viewport** – `viewport-fit=cover` for notches
- [x] **Safe areas** – `env(safe-area-inset-*)`
- [x] **Touch targets** – 44px minimum on mobile
- [x] **HTTPS** – required in production

---

## Testing Checklist

1. **iPhone** (Safari): Add to Home Screen → opens in standalone
2. **Android** (Chrome): Install prompt or menu → Add to Home Screen
3. **Z Fold**: Test cover (323px) and inner (619px) in portrait and landscape
4. **iPad**: Portrait and landscape tablet layout
5. **Narrow** (320px): DevTools device emulation for Z Fold cover

---

## Regenerating Icons

After editing `public/icon.svg`:

```bash
cd frontend
npx pwa-asset-generator public/icon.svg public/ --icon-only
cp public/manifest-icon-192.maskable.png public/icon-192.png
cp public/manifest-icon-512.maskable.png public/icon-512.png
```

---

## References

- [iPhone Viewport Sizes](https://screensizechecker.com/devices/iphone-viewport-sizes.html)
- [Android Viewport Sizes](https://screensizechecker.com/en/devices/android-viewport-sizes.html)
- [Android Window Size Classes](https://developer.android.com/develop/ui/views/layout/use-window-size-classes)
- [PWA Install Criteria](https://web.dev/articles/pwas-in-app-stores)
- [Making PWAs Installable](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable)
