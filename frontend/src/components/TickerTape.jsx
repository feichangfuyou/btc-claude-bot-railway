import { memo, useMemo, useCallback, useRef, useEffect } from "react";
import TickerItem from "../TickerItem.jsx";

export const FALLBACK_SYMBOL_TO_COINGECKO = {
  BTC: "bitcoin", ETH: "ethereum", SOL: "solana", BNB: "binancecoin", XRP: "ripple", ADA: "cardano", AVAX: "avalanche-2",
  LINK: "chainlink", DOT: "polkadot", PEPE: "pepe", DOGE: "dogecoin", SHIB: "shiba-inu", UNI: "uniswap", AAVE: "aave",
  MATIC: "matic-network", POL: "polygon-ecosystem-token", LTC: "litecoin", ATOM: "cosmos", XLM: "stellar", BCH: "bitcoin-cash",
  NEAR: "near", APE: "apecoin", FIL: "filecoin", ARB: "arbitrum", OP: "optimism", INJ: "injective-protocol", SUI: "sui",
  SEI: "sei-network", STX: "blockstack", TIA: "celestia", RUNE: "thorchain", TRX: "tron", APT: "aptos", ETC: "ethereum-classic",
  WLD: "worldcoin-wld", FET: "fetch-ai", JUP: "jupiter-exchange-solana", ORDI: "ordinals", PENDLE: "pendle", STRK: "starknet",
  EIGEN: "eigenlayer", IMX: "immutable-x", RENDER: "render-token", GRT: "the-graph", SAND: "the-sandbox", MANA: "decentraland",
  AXS: "axie-infinity", GMT: "stepn", CRV: "curve-dao-token", MKR: "maker", COMP: "compound-governance-token", SNX: "havven",
  LDO: "lido-dao", ENS: "ethereum-name-service", GMX: "gmx", MAGIC: "magic", BONK: "bonk", FLOKI: "floki", WIF: "dogwifcoin",
  MEME: "memecoin", "1000PEPE": "1000pepe", "1000SATS": "1000sats-ordinals", "1000BONK": "1000bonk", PYTH: "pyth-network",
  JTO: "jito-governance-token", DYM: "dymension", TAO: "bittensor", JASMY: "jasmycoin", ZRO: "layerzero", ENA: "ethena",
  EDU: "edu-coin", BLUR: "blur", ID: "spaceland", RDNT: "radiant-capital", CFX: "conflux-token", CORE: "core-dao",
  MASK: "mask-network", SKL: "skale", MINA: "mina-protocol", ASTR: "astar", KAVA: "kava", ONE: "harmony", FTM: "fantom",
  CELO: "celo", KSM: "kusama", ZIL: "zilliqa", THETA: "theta-token", SUSHI: "sushi", "1INCH": "1inch", YFI: "yearn-finance",
  BAL: "balancer", UMA: "uma", HNT: "helium", RPL: "rocket-pool", RSR: "reserve-rights-token", LQTY: "liquity",
  OCEAN: "ocean-protocol", API3: "api3", AGLD: "adventure-gold", PERP: "perpetual-protocol", GNO: "gnosis",
  FXS: "frax-share", FRAX: "frax", DAI: "dai", USDC: "usd-coin", USDT: "tether", TUSD: "true-usd", BUSD: "binance-usd",
  TON: "the-open-network", HBAR: "hedera-hashgraph", VET: "vechain", ALGO: "algorand", ICP: "internet-computer",
  XTZ: "tezos", EGLD: "elrond", ROSE: "oasis-network", FLOW: "flow", AUDIO: "audius", CHZ: "chiliz", XEC: "ecash", EOS: "eos",
  WAVES: "waves", NEO: "neo", ONT: "ontology", ICX: "icon",
  NOT: "notcoin", W: "wormhole", BRETT: "based-brett", POPCAT: "popcat", BOME: "book-of-meme",
  ACE: "fusionist", ALT: "altlayer", ARKM: "arkham", COMBO: "combo",
  TRUMP: "official-trump", ONDO: "ondo-finance", VIRTUAL: "virtual-protocol", TURBO: "turbo",
  FARTCOIN: "fartcoin", KAS: "kaspa", RNDR: "render-token",
  PIXEL: "pixels", PORTAL: "portal-2", MANTA: "manta-network", ZK: "zksync",
  BEAM: "beam-2", GALA: "gala", SUPER: "superverse", ACH: "alchemy-pay",
  LOOM: "loom-network", BAKE: "bakerytoken", CELR: "celer-network", DENT: "dent",
  DUSK: "dusk-network", LEVER: "lever", LINA: "linear",
  STORJ: "storj", SFP: "safepal", SSV: "ssv-network", VANRY: "vanar-chain",
  REKT: "rekt", COQ: "coq-inu", SPICE: "spice", APU: "apu", MEW: "cat-in-a-dogs-world",
  DOGS: "dogs-2", WEN: "wen", TOSHI: "toshi", NEIRO: "neiro-3",
};

export const JSDELIVR_CDN = "https://cdn.jsdelivr.net/npm/cryptocurrency-icons@0.18.1/svg/color";
export const JSDELIVR_CDN_PNG = "https://cdn.jsdelivr.net/npm/cryptocurrency-icons@0.18.1/128/color";
export const CRYPTO_ICONS_CDN = "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color";

export function getTickerLogoUrl(sym) {
  return `${JSDELIVR_CDN}/${sym?.toLowerCase?.()}.svg`;
}

export function getTickerLogoFallback1(sym) {
  return `${JSDELIVR_CDN_PNG}/${sym?.toLowerCase?.()}.png`;
}

export function getTickerLogoFallback2(sym) {
  return `${CRYPTO_ICONS_CDN}/${sym?.toLowerCase?.()}.png`;
}

export function getTickerLogoPlaceholder(sym) {
  const letter = (sym || "?")[0];
  const hue = ((sym || "").charCodeAt(0) * 37 + (sym || "").charCodeAt(1 % (sym || " ").length) * 59) % 360;
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">` +
    `<circle cx="20" cy="20" r="20" fill="hsl(${hue},45%,25%)"/>` +
    `<text x="20" y="26" text-anchor="middle" fill="#D4D4D4" font-family="sans-serif" font-size="18" font-weight="700">${letter}</text>` +
    `</svg>`
  )}`;
}

export const TICKER_TAPE_LIMIT = 50;

// ─── Smooth rAF-driven ticker ────────────────────────────────────────────────
// Pixels per second — tune this one number to change overall speed.
const SCROLL_SPEED_PX_PER_SEC = 55;

export const TickerTape = memo(function TickerTape({ marketTickers, activeCoins, coins, price, selectedCoin, positions, onSelectCoin }) {
  // Build base set (no duplication yet — we duplicate in the DOM for the loop)
  const baseItems = useMemo(() => {
    return marketTickers.length > 0
      ? marketTickers.slice(0, TICKER_TAPE_LIMIT)
      : activeCoins.map(sym => ({ sym, price: 0, chg24h: null, image: null }));
  }, [marketTickers, activeCoins]);

  // Render the set twice so the loop is seamless
  const items = useMemo(() => [...baseItems, ...baseItems], [baseItems]);

  const positionSyms = useMemo(
    () => new Set(positions.map(p => p.symbol)),
    [positions],
  );

  // ── rAF loop drives scroll — never touches React state ──────────────────────
  const trackRef = useRef(null);
  const rafRef = useRef(null);
  const offsetRef = useRef(0);       // current X offset in pixels
  const lastTsRef = useRef(null);    // last rAF timestamp
  const pausedRef = useRef(false);   // paused by hover
  const halfWidthRef = useRef(0);    // half the track scrollWidth — reset point

  // Kick off the rAF loop — runs once on mount, stays alive forever
  useEffect(() => {
    function tick(ts) {
      rafRef.current = requestAnimationFrame(tick);

      const track = trackRef.current;
      if (!track) { lastTsRef.current = ts; return; }

      // Measure half-width lazily (needed for seamless loop reset)
      if (!halfWidthRef.current) {
        const tw = track.scrollWidth;
        if (tw > 0) halfWidthRef.current = tw / 2;
      }

      const dt = lastTsRef.current != null ? ts - lastTsRef.current : 0;
      lastTsRef.current = ts;

      if (!pausedRef.current && halfWidthRef.current > 0 && dt > 0) {
        // Cap delta (avoid huge jumps after tab becomes active again)
        const safeDt = Math.min(dt, 100);
        offsetRef.current += (SCROLL_SPEED_PX_PER_SEC / 1000) * safeDt;

        // Seamless loop: once we've scrolled one full copy, reset
        if (offsetRef.current >= halfWidthRef.current) {
          offsetRef.current -= halfWidthRef.current;
        }
      }

      // Direct DOM write — bypasses React entirely, no layout thrash
      track.style.transform = `translate3d(${-offsetRef.current}px, 0, 0)`;
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []); // empty deps — loop is permanent, never restarts

  // When items change, re-measure half-width on next tick
  useEffect(() => {
    halfWidthRef.current = 0;
  }, [baseItems.length]);

  const handleImgError = useCallback((e) => {
    const img = e.target;
    const sym = img.dataset.sym;
    const tier = parseInt(img.dataset.fallbackTier || "0", 10);
    if (tier === 0) {
      img.dataset.fallbackTier = "1";
      img.src = getTickerLogoFallback1(sym);
    } else if (tier === 1) {
      img.dataset.fallbackTier = "2";
      img.src = getTickerLogoFallback2(sym);
    } else if (tier === 2) {
      img.dataset.fallbackTier = "3";
      img.src = getTickerLogoPlaceholder(sym);
    }
  }, []);

  const handleMouseEnter = useCallback(() => { pausedRef.current = true; }, []);
  const handleMouseLeave = useCallback(() => { pausedRef.current = false; }, []);

  return (
    <div
      className="ticker-tape"
      style={{ marginBottom: "8px" }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div
        ref={trackRef}
        className="ticker-track"
        style={{
          display: "flex",
          alignItems: "center",
          willChange: "transform",
          // NO animation property — rAF drives transform directly
          transform: "translate3d(0,0,0)",
        }}
      >
        {items.map((item, i) => {
          const sym = item.sym || item;
          const liveCoin = coins[sym];
          const coinPrice = (sym === selectedCoin && price > 0 ? price : null) ?? liveCoin?.price ?? item.price ?? 0;
          const chg24h = liveCoin?.price_change24h ?? item.chg24h ?? null;
          const logoUrl = item.image || getTickerLogoUrl(sym);
          const isSelected = sym === selectedCoin;
          const hasPosition = positionSyms.has(sym);
          return (
            <TickerItem
              key={`${sym}-${i}`}
              sym={sym}
              coinPrice={coinPrice}
              chg24h={chg24h}
              logoUrl={logoUrl}
              isSelected={isSelected}
              hasPosition={hasPosition}
              onClick={() => onSelectCoin(sym)}
              onImgError={handleImgError}
              imgDataSym={sym}
            />
          );
        })}
      </div>
    </div>
  );
});
