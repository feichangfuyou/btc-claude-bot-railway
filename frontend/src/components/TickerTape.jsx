import { memo, useMemo, useCallback, useRef } from "react";
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
  NOT: "notcoin", W: "wormhole", BRETT: "based-brett", POPCAT: "popcat", NEIRO: "neiro", BOME: "book-of-meme",
  ACE: "fusionist", ALT: "altlayer", ARKM: "arkham", COMBO: "combo",
  TRUMP: "official-trump", ONDO: "ondo-finance", VIRTUAL: "virtual-protocol", TURBO: "turbo",
  FARTCOIN: "fartcoin", KAS: "kaspa", RNDR: "render-token",
  PIXEL: "pixels", PORTAL: "portal-2", MANTA: "manta-network", ZK: "zksync",
  BEAM: "beam-2", GALA: "gala", SUPER: "superverse", ACH: "alchemy-pay",
  LOOM: "loom-network", BAKE: "bakerytoken", CELR: "celer-network", DENT: "dent",
  DUSK: "dusk-network", LEVER: "lever", LINA: "linear",
  STORJ: "storj", SFP: "safepal", SSV: "ssv-network", VANRY: "vanar-chain",
};

export const COINCAP_CDN = "https://assets.coincap.io/assets/icons";
export const COIN_LOGOS_CDN = "https://cdn.jsdelivr.net/gh/simplr-sh/coin-logos/images";
export const COINCAP_SYM_MAP = { POL: "matic", MATIC: "matic", APT: "apt", "1000PEPE": "pepe", "1000SATS": "sats", "1000BONK": "bonk", RNDR: "render", RENDER: "render" };

export function getTickerLogoUrl(sym) {
  const capId = COINCAP_SYM_MAP[sym] || sym?.toLowerCase?.();
  return `${COINCAP_CDN}/${capId}@2x.png`;
}

export function getTickerLogoFallback1(sym) {
  const cgId = FALLBACK_SYMBOL_TO_COINGECKO[sym] || sym?.toLowerCase?.()?.replace(/\s/g, "-");
  return `${COIN_LOGOS_CDN}/${cgId}/small.png`;
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

export const TickerTape = memo(function TickerTape({ marketTickers, activeCoins, coins, price, selectedCoin, positions, onSelectCoin }) {
  const items = useMemo(() => {
    const base = marketTickers.length > 0
      ? marketTickers.slice(0, TICKER_TAPE_LIMIT)
      : activeCoins.map(sym => ({ sym, price: 0, chg24h: null, image: null }));
    return [...base, ...base];
  }, [marketTickers, activeCoins]);

  const positionSyms = useMemo(
    () => new Set(positions.map(p => p.symbol)),
    [positions],
  );

  const handleImgError = useCallback((e) => {
    const img = e.target;
    const sym = img.dataset.sym;
    const tier = parseInt(img.dataset.fallbackTier || "0", 10);
    if (tier === 0) {
      img.dataset.fallbackTier = "1";
      img.src = getTickerLogoFallback1(sym);
    } else if (tier === 1) {
      img.dataset.fallbackTier = "2";
      img.src = getTickerLogoPlaceholder(sym);
    }
  }, []);

  const clickHandlers = useRef({});
  const getClickHandler = useCallback((sym) => {
    if (!clickHandlers.current[sym]) {
      clickHandlers.current[sym] = () => onSelectCoin(sym);
    }
    return clickHandlers.current[sym];
  }, [onSelectCoin]);

  return (
    <div className="ticker-tape" style={{ marginBottom: "14px" }}>
      <div
        className="ticker-track"
        style={{ display: "flex", gap: "24px", alignItems: "center" }}
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
              onClick={getClickHandler(sym)}
              onImgError={handleImgError}
              imgDataSym={sym}
            />
          );
        })}
      </div>
    </div>
  );
});
