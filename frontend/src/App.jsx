import { useState, useEffect, useLayoutEffect, useRef, useCallback, useMemo, memo, Component } from "react";
import { useNavigate } from "react-router-dom";
import confetti from "canvas-confetti";
import { useAuth } from "./contexts/AuthContext.jsx";
import TradingViewChart from "./TradingViewChart.jsx";
import AnimatedNumber from "./AnimatedNumber.jsx";
import FetchingPrice from "./FetchingPrice.jsx";
import Skeleton from "./Skeleton.jsx";
import TickerItem from "./TickerItem.jsx";
import { staggerIn } from "./animations.js";

// ─── Trading Quotes (rotating) ──────────────────────────────────────────────────
const TRADE_QUOTES = [
  "The market rewards patience and punishes greed.",
  "Risk what you can afford, protect what you can't.",
  "Discipline is the bridge between goals and results.",
  "Trade the plan, not the emotion.",
  "In markets, conviction without evidence is just gambling.",
];
function TradeQuote() {
  const [idx, setIdx] = useState(0);
  const [fade, setFade] = useState(true);
  useEffect(() => {
    const timer = setInterval(() => {
      setFade(false);
      setTimeout(() => { setIdx(i => (i + 1) % TRADE_QUOTES.length); setFade(true); }, 400);
    }, 8000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div style={{ fontFamily:"'Playfair Display',serif", fontSize:"11px", color:"#D4AF37", letterSpacing:"0.5px", fontStyle:"italic", maxWidth:"300px", lineHeight:"1.5", opacity:fade?1:0, transition:"opacity 0.4s ease" }}>
      &ldquo;{TRADE_QUOTES[idx]}&rdquo;
    </div>
  );
}

// ─── Error Boundary ────────────────────────────────────────────────────────────
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ fontFamily:"'Space Mono',monospace", background:"#0A0A0A", color:"#D4D4D4", minHeight:"100vh", display:"flex", alignItems:"center", justifyContent:"center", flexDirection:"column", gap:"16px", padding:"20px", textAlign:"center" }}>
          <div style={{ fontSize:"48px" }}>🥊</div>
          <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"28px", fontWeight:"400", color:"#C0392B", letterSpacing:"4px" }}>DOWN FOR THE COUNT</div>
          <div style={{ fontSize:"12px", color:"#5C5C5C", maxWidth:"500px", lineHeight:"1.8" }}>
            {this.state.error?.message || "An unexpected error occurred."}
          </div>
          <button
            onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload(); }}
            style={{ fontFamily:"'Oswald',sans-serif", fontSize:"12px", fontWeight:"600", letterSpacing:"2px", padding:"10px 24px", border:"none", borderRadius:"3px", cursor:"pointer", background:"linear-gradient(180deg,#D4AF37,#B8860B)", color:"#0A0A0A" }}
          >
            GET BACK UP
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// ─── Indicator math (demo mode only — backend computes when connected) ────────
function calcEMA(prices, period) {
  if (prices.length < 2) return null;
  const n = Math.min(period, prices.length), k = 2 / (n + 1);
  let v = prices.slice(0, n).reduce((a, b) => a + b, 0) / n;
  for (let i = n; i < prices.length; i++) v = prices[i] * k + v * (1 - k);
  return +v.toFixed(2);
}
function calcRSI(prices, period = 14) {
  if (prices.length < period + 1) return 50;
  let g = 0, l = 0;
  for (let i = prices.length - period; i < prices.length; i++) {
    const d = prices[i] - prices[i - 1];
    d > 0 ? (g += d) : (l += Math.abs(d));
  }
  return +(100 - 100 / (1 + (g / period) / (l / period + 1e-9))).toFixed(2);
}
function calcATR(prices, period = 14) {
  if (prices.length < 2) return 0;
  const trs = prices.slice(1).map((p, i) => Math.abs(p - prices[i]));
  const r = trs.slice(-period);
  return +(r.reduce((a, b) => a + b, 0) / r.length).toFixed(2);
}
function calcBB(prices, period = 20) {
  const r = prices.slice(-Math.min(period, prices.length));
  const mid = r.reduce((a, b) => a + b, 0) / r.length;
  const std = Math.sqrt(r.reduce((s, p) => s + (p - mid) ** 2, 0) / r.length);
  const width = mid ? +((4 * std / mid) * 100).toFixed(4) : 0;
  return { upper: +(mid + 2 * std).toFixed(2), middle: +mid.toFixed(2), lower: +(mid - 2 * std).toFixed(2), width };
}

// ─── Unique ID generator for logs ─────────────────────────────────────────────
let _logSeq = 0;
function logId() { return `log_${Date.now()}_${++_logSeq}`; }

const API_SECRET = import.meta.env.VITE_BOT_API_SECRET || "";

function authHeaders() {
  const h = {};
  if (API_SECRET) h["x-bot-secret"] = API_SECRET;
  return h;
}

// Direct backend connection by default (no proxy). More reliable for WebSocket + API.
const BACKEND_BASE = import.meta.env.VITE_BACKEND_URL
  || (import.meta.env.DEV ? "http://localhost:8000" : "");

function getBackendWsUrl() {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL + (API_SECRET ? `?secret=${encodeURIComponent(API_SECRET)}` : "");
  if (BACKEND_BASE) {
    try {
      const u = new URL(BACKEND_BASE.replace(/\/$/, ""));
      const proto = u.protocol === "https:" ? "wss:" : "ws:";
      return `${proto}//${u.host}/ws` + (API_SECRET ? `?secret=${encodeURIComponent(API_SECRET)}` : "");
    } catch {}
  }
  return (window.location.protocol === "https:" ? "wss:" : "ws:") + "//" + window.location.host + "/ws"
    + (API_SECRET ? `?secret=${encodeURIComponent(API_SECRET)}` : "");
}
const DEFAULT_ROUND_TRIP_FEE = 0.012;  // fallback: 0.6% taker × 2 sides
const DEFAULT_COINS = ["BTC","ETH","SOL","DOGE","LINK","AVAX","UNI","AAVE"];

const PRESETS_FALLBACK = [
  { id: "default", name: "Default (Balanced)", trader: "Bot default", category: "General" },
  { id: "turtle", name: "Turtle Traders", trader: "Richard Dennis", category: "Trend Following" },
  { id: "seykota", name: "Ed Seykota", trader: "Ed Seykota", category: "Trend Following" },
  { id: "trend_dunn", name: "Dunn Capital Trend", trader: "Bill Dunn", category: "Trend Following" },
  { id: "trend_henry", name: "John W. Henry", trader: "John W. Henry", category: "Trend Following" },
  { id: "trend_harding", name: "Winton Trend", trader: "David Harding", category: "Trend Following" },
  { id: "trend_abraham", name: "Abraham Trading", trader: "Salem Abraham", category: "Trend Following" },
  { id: "trend_millburn", name: "Millburn Ridgefield", trader: "Millburn Ridgefield", category: "Trend Following" },
  { id: "donchian", name: "Donchian Channel", trader: "Richard Donchian", category: "Trend Following" },
  { id: "soros", name: "Soros Reflexivity", trader: "George Soros", category: "Macro" },
  { id: "ptj", name: "Paul Tudor Jones", trader: "Paul Tudor Jones", category: "Macro" },
  { id: "druckenmiller", name: "Druckenmiller Macro", trader: "Stanley Druckenmiller", category: "Macro" },
  { id: "kovner", name: "Kovner Conservative", trader: "Bruce Kovner", category: "Macro" },
  { id: "bacon", name: "Louis Bacon Macro", trader: "Louis Bacon", category: "Macro" },
  { id: "dalio", name: "Dalio All-Weather", trader: "Ray Dalio", category: "Macro" },
  { id: "robertson", name: "Julian Robertson", trader: "Julian Robertson", category: "Macro" },
  { id: "steinhardt", name: "Michael Steinhardt", trader: "Michael Steinhardt", category: "Macro" },
  { id: "tudor_bvi", name: "Tudor BVI Macro", trader: "Tudor Investment Corp", category: "Macro" },
  { id: "gross", name: "Bill Gross Bond King", trader: "Bill Gross", category: "Macro" },
  { id: "gundlach", name: "Gundlach DoubleLine", trader: "Jeffrey Gundlach", category: "Macro" },
  { id: "livermore", name: "Livermore Pivots", trader: "Jesse Livermore", category: "Stock Legends" },
  { id: "minervini", name: "Minervini Momentum", trader: "Mark Minervini", category: "Stock Legends" },
  { id: "oneil", name: "William O'Neil CANSLIM", trader: "William O'Neil", category: "Stock Legends" },
  { id: "darvas", name: "Nicolas Darvas Box", trader: "Nicolas Darvas", category: "Stock Legends" },
  { id: "zanger", name: "Dan Zanger Breakout", trader: "Dan Zanger", category: "Stock Legends" },
  { id: "weinstein", name: "Weinstein Stage", trader: "Stan Weinstein", category: "Stock Legends" },
  { id: "lefevre", name: "Reminiscences Classic", trader: "Edwin Lefèvre / Livermore", category: "Stock Legends" },
  { id: "simons", name: "Renaissance Quant", trader: "Jim Simons", category: "Quantitative" },
  { id: "shannon", name: "Shannon Rebalance", trader: "Claude Shannon", category: "Quantitative" },
  { id: "thorp", name: "Ed Thorp Kelly", trader: "Ed Thorp", category: "Quantitative" },
  { id: "aqr", name: "AQR Factor", trader: "Cliff Asness / AQR", category: "Quantitative" },
  { id: "two_sigma", name: "Two Sigma Systematic", trader: "David Siegel / John Overdeck", category: "Quantitative" },
  { id: "de_shaw", name: "D.E. Shaw Quant", trader: "David Shaw", category: "Quantitative" },
  { id: "citadel", name: "Citadel Multi-Strat", trader: "Ken Griffin", category: "Quantitative" },
  { id: "man_ahl", name: "Man AHL Systematic", trader: "Man Group / AHL", category: "Quantitative" },
  { id: "blackbox", name: "Black Box Quant", trader: "Quantitative firms", category: "Quantitative" },
  { id: "buffett", name: "Buffett Value", trader: "Warren Buffett", category: "Value / Contrarian" },
  { id: "icahn", name: "Carl Icahn Activist", trader: "Carl Icahn", category: "Value / Contrarian" },
  { id: "klarman", name: "Seth Klarman Value", trader: "Seth Klarman", category: "Value / Contrarian" },
  { id: "marks", name: "Howard Marks Cycles", trader: "Howard Marks", category: "Value / Contrarian" },
  { id: "templeton", name: "Templeton Contrarian", trader: "John Templeton", category: "Value / Contrarian" },
  { id: "neff", name: "John Neff Low P/E", trader: "John Neff", category: "Value / Contrarian" },
  { id: "burry", name: "Michael Burry Deep Value", trader: "Michael Burry", category: "Value / Contrarian" },
  { id: "driehaus", name: "Driehaus Momentum", trader: "Richard Driehaus", category: "Momentum / Growth" },
  { id: "lynch", name: "Peter Lynch Growth", trader: "Peter Lynch", category: "Momentum / Growth" },
  { id: "ryan", name: "David Ryan CANSLIM", trader: "David Ryan", category: "Momentum / Growth" },
  { id: "wood", name: "Cathie Wood Innovation", trader: "Cathie Wood", category: "Momentum / Growth" },
  { id: "raschke", name: "Raschke Short-Term", trader: "Linda Raschke", category: "Short-Term / Swing" },
  { id: "williams_balanced", name: "Williams Balanced", trader: "Larry Williams", category: "Short-Term / Swing" },
  { id: "williams_swing", name: "Williams Swing", trader: "Larry Williams", category: "Short-Term / Swing" },
  { id: "douglas", name: "Mark Douglas Zone", trader: "Mark Douglas", category: "Short-Term / Swing" },
  { id: "elder", name: "Alexander Elder", trader: "Alexander Elder", category: "Short-Term / Swing" },
  { id: "schwartz", name: "Marty Schwartz Pit Bull", trader: "Martin Schwartz", category: "Short-Term / Swing" },
  { id: "jones_crt", name: "CRT Bond Arb", trader: "Paul Tudor Jones (CRT era)", category: "Short-Term / Swing" },
  { id: "taleb", name: "Taleb Barbell", trader: "Nassim Taleb", category: "Volatility / Tail Risk" },
  { id: "niederhoffer", name: "Niederhoffer Mean-Rev", trader: "Victor Niederhoffer", category: "Volatility / Tail Risk" },
  { id: "tail_risk", name: "Tail Risk Hunter", trader: "Universa / Spitznagel", category: "Volatility / Tail Risk" },
  { id: "vol_breakout", name: "Volatility Breakout", trader: "Toby Crabel / NR7", category: "Volatility / Tail Risk" },
  { id: "crypto_swing", name: "Crypto Swing Pro", trader: "Crypto best practices", category: "Crypto Native" },
  { id: "crypto_conservative", name: "Crypto Maximum Room", trader: "High-volatility best practices", category: "Crypto Native" },
  { id: "saylor", name: "Saylor HODL Conviction", trader: "Michael Saylor", category: "Crypto Native" },
  { id: "hayes", name: "Arthur Hayes Degen", trader: "Arthur Hayes", category: "Crypto Native" },
  { id: "su_zhu", name: "Su Zhu Supercycle", trader: "Su Zhu (pre-3AC)", category: "Crypto Native" },
  { id: "cobie", name: "Cobie CT Alpha", trader: "Cobie (Jordan Fish)", category: "Crypto Native" },
  { id: "pentoshi", name: "Pentoshi Swing", trader: "Pentoshi", category: "Crypto Native" },
  { id: "hsaka", name: "Hsaka Scalp-Swing", trader: "Hsaka", category: "Crypto Native" },
  { id: "ansem", name: "Ansem Degen Momentum", trader: "Ansem", category: "Crypto Native" },
  { id: "gainzy", name: "GCR Contrarian", trader: "GCR (Gigantic Rebirth)", category: "Crypto Native" },
  { id: "light", name: "Light Crypto Macro", trader: "Light (Crypto)", category: "Crypto Native" },
  { id: "mobius", name: "Mark Mobius EM", trader: "Mark Mobius", category: "Global / Emerging" },
  { id: "rogers", name: "Jim Rogers Commodities", trader: "Jim Rogers", category: "Global / Emerging" },
  { id: "rogers_jim", name: "Jim Rogers Adventure", trader: "Jim Rogers", category: "Global / Emerging" },
  { id: "paulson", name: "John Paulson Event", trader: "John Paulson", category: "Event-Driven" },
  { id: "tepper", name: "David Tepper Distressed", trader: "David Tepper", category: "Event-Driven" },
  { id: "einhorn", name: "David Einhorn Value", trader: "David Einhorn", category: "Event-Driven" },
  { id: "loeb", name: "Dan Loeb Activist", trader: "Daniel Loeb", category: "Event-Driven" },
  { id: "ackman", name: "Bill Ackman Conviction", trader: "Bill Ackman", category: "Event-Driven" },
  { id: "coleman", name: "Chase Coleman Tiger", trader: "Chase Coleman", category: "Tiger Cubs / Modern HF" },
  { id: "mandel", name: "Steve Mandel Lone Pine", trader: "Steve Mandel", category: "Tiger Cubs / Modern HF" },
  { id: "ainslie", name: "Lee Ainslie Maverick", trader: "Lee Ainslie", category: "Tiger Cubs / Modern HF" },
  { id: "marcus", name: "Michael Marcus", trader: "Michael Marcus", category: "Market Wizards Classic" },
  { id: "mean_rev_bollinger", name: "Bollinger Mean-Rev", trader: "John Bollinger", category: "Mean-Reversion" },
  { id: "mean_rev_connors", name: "Connors RSI Reversal", trader: "Larry Connors", category: "Mean-Reversion" },
  { id: "scalp_tight", name: "Scalper Tight", trader: "Professional scalpers", category: "Scalping" },
  { id: "scalp_momentum", name: "Momentum Scalp", trader: "Crypto scalpers", category: "Scalping" },
  { id: "market_maker", name: "Market Maker Spread", trader: "Market makers", category: "Scalping" },
  { id: "risk_parity", name: "Risk Parity", trader: "Bridgewater / Risk Parity", category: "Portfolio / Systematic" },
  { id: "grid_dca", name: "Grid DCA", trader: "Systematic DCA", category: "Portfolio / Systematic" },
  { id: "seasonal", name: "Seasonal Patterns", trader: "Seasonal traders", category: "Portfolio / Systematic" },
  { id: "sentiment", name: "Sentiment Extremes", trader: "Sentiment traders", category: "Portfolio / Systematic" },
  { id: "fib_trader", name: "Fibonacci Precision", trader: "Harmonic traders", category: "Technical Systems" },
  { id: "ichimoku", name: "Ichimoku Cloud", trader: "Goichi Hosoda", category: "Technical Systems" },
  { id: "wyckoff", name: "Wyckoff Method", trader: "Richard Wyckoff", category: "Technical Systems" },
  { id: "volume_profile", name: "Volume Profile", trader: "Market Profile traders", category: "Technical Systems" },
  { id: "elliott", name: "Elliott Wave", trader: "R.N. Elliott / Prechter", category: "Technical Systems" },
  { id: "gann", name: "W.D. Gann Geometric", trader: "W.D. Gann", category: "Technical Systems" },
  { id: "pnf", name: "Point & Figure", trader: "P&F chartists", category: "Technical Systems" },
  { id: "smc", name: "Smart Money Concepts", trader: "ICT / SMC traders", category: "Technical Systems" },
  { id: "gap_trader", name: "Gap & Go", trader: "Opening range traders", category: "Technical Systems" },
  { id: "vwap", name: "VWAP Institutional", trader: "Institutional traders", category: "Technical Systems" },
  { id: "pairs_trade", name: "Pairs Trading", trader: "Stat arb / relative value", category: "Technical Systems" },
];
const PRESETS_CATEGORIES_FALLBACK = [
  "General", "Trend Following", "Macro", "Stock Legends", "Quantitative",
  "Value / Contrarian", "Momentum / Growth", "Short-Term / Swing",
  "Volatility / Tail Risk", "Crypto Native", "Global / Emerging",
  "Event-Driven", "Tiger Cubs / Modern HF", "Market Wizards Classic",
  "Mean-Reversion", "Scalping", "Portfolio / Systematic", "Technical Systems",
];

// Fallback coin logo mapping — overridden by /api/config when backend is available
const FALLBACK_SYMBOL_TO_COINGECKO = {
  BTC:"bitcoin", ETH:"ethereum", SOL:"solana", BNB:"binancecoin", XRP:"ripple", ADA:"cardano", AVAX:"avalanche-2",
  LINK:"chainlink", DOT:"polkadot", PEPE:"pepe", DOGE:"dogecoin", SHIB:"shiba-inu", UNI:"uniswap", AAVE:"aave",
  MATIC:"matic-network", POL:"polygon-ecosystem-token", LTC:"litecoin", ATOM:"cosmos", XLM:"stellar", BCH:"bitcoin-cash",
  NEAR:"near", APE:"apecoin", FIL:"filecoin", ARB:"arbitrum", OP:"optimism", INJ:"injective-protocol", SUI:"sui",
  SEI:"sei-network", STX:"blockstack", TIA:"celestia", RUNE:"thorchain", TRX:"tron", APT:"aptos", ETC:"ethereum-classic",
  WLD:"worldcoin-wld", FET:"fetch-ai", JUP:"jupiter-exchange-solana", ORDI:"ordinals", PENDLE:"pendle", STRK:"starknet",
  EIGEN:"eigenlayer", IMX:"immutable-x", RENDER:"render-token", GRT:"the-graph", SAND:"the-sandbox", MANA:"decentraland",
  AXS:"axie-infinity", GMT:"stepn", CRV:"curve-dao-token", MKR:"maker", COMP:"compound-governance-token", SNX:"havven",
  LDO:"lido-dao", ENS:"ethereum-name-service", GMX:"gmx", MAGIC:"magic", BONK:"bonk", FLOKI:"floki", WIF:"dogwifcoin",
  MEME:"memecoin", "1000PEPE":"1000pepe", "1000SATS":"1000sats-ordinals", "1000BONK":"1000bonk", PYTH:"pyth-network",
  JTO:"jito-governance-token", DYM:"dymension", TAO:"bittensor", JASMY:"jasmycoin", ZRO:"layerzero", ENA:"ethena",
  EDU:"edu-coin", BLUR:"blur", ID:"spaceland", RDNT:"radiant-capital", CFX:"conflux-token", CORE:"core-dao",
  MASK:"mask-network", SKL:"skale", MINA:"mina-protocol", ASTR:"astar", KAVA:"kava", ONE:"harmony", FTM:"fantom",
  CELO:"celo", KSM:"kusama", ZIL:"zilliqa", THETA:"theta-token", SUSHI:"sushi", "1INCH":"1inch", YFI:"yearn-finance",
  BAL:"balancer", UMA:"uma", HNT:"helium", RPL:"rocket-pool", RSR:"reserve-rights-token", LQTY:"liquity",
  OCEAN:"ocean-protocol", API3:"api3", AGLD:"adventure-gold", PERP:"perpetual-protocol", GNO:"gnosis",
  FXS:"frax-share", FRAX:"frax", DAI:"dai", USDC:"usd-coin", USDT:"tether", TUSD:"true-usd", BUSD:"binance-usd",
  TON:"the-open-network", HBAR:"hedera-hashgraph", VET:"vechain", ALGO:"algorand", ICP:"internet-computer",
  XTZ:"tezos", EGLD:"elrond", ROSE:"oasis-network", FLOW:"flow", AUDIO:"audius", CHZ:"chiliz", XEC:"ecash", EOS:"eos",
  WAVES:"waves", NEO:"neo", ONT:"ontology", ICX:"icon",
  NOT:"notcoin", W:"wormhole", BRETT:"based-brett", POPCAT:"popcat", NEIRO:"neiro", BOME:"book-of-meme",
  ACE:"fusionist", ALT:"altlayer", ARKM:"arkham", COMBO:"combo",
  TRUMP:"official-trump", ONDO:"ondo-finance", VIRTUAL:"virtual-protocol", TURBO:"turbo",
    FARTCOIN:"fartcoin", KAS:"kaspa", RNDR:"render-token",
  PIXEL:"pixels", PORTAL:"portal-2", MANTA:"manta-network", ZK:"zksync",
  BEAM:"beam-2", GALA:"gala", SUPER:"superverse", ACH:"alchemy-pay",
  LOOM:"loom-network", BAKE:"bakerytoken", CELR:"celer-network", DENT:"dent",
    DUSK:"dusk-network", LEVER:"lever", LINA:"linear",
  STORJ:"storj", SFP:"safepal", SSV:"ssv-network", VANRY:"vanar-chain",
};
const COINCAP_CDN = "https://assets.coincap.io/assets/icons";
const COIN_LOGOS_CDN = "https://cdn.jsdelivr.net/gh/simplr-sh/coin-logos/images";
const COINCAP_SYM_MAP = { POL:"matic", MATIC:"matic", APT:"apt", "1000PEPE":"pepe", "1000SATS":"sats", "1000BONK":"bonk" };

function getTickerLogoUrl(sym) {
  const capId = COINCAP_SYM_MAP[sym] || sym?.toLowerCase?.();
  return `${COINCAP_CDN}/${capId}@2x.png`;
}
function getTickerLogoFallback1(sym) {
  const cgId = FALLBACK_SYMBOL_TO_COINGECKO[sym] || sym?.toLowerCase?.()?.replace(/\s/g, "-");
  return `${COIN_LOGOS_CDN}/${cgId}/small.png`;
}
function getTickerLogoPlaceholder(sym) {
  const letter = (sym || "?")[0];
  const hue = ((sym || "").charCodeAt(0) * 37 + (sym || "").charCodeAt(1 % (sym || " ").length) * 59) % 360;
  return `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">` +
    `<circle cx="20" cy="20" r="20" fill="hsl(${hue},45%,25%)"/>` +
    `<text x="20" y="26" text-anchor="middle" fill="#D4D4D4" font-family="sans-serif" font-size="18" font-weight="700">${letter}</text>` +
    `</svg>`
  )}`;
}

const TICKER_TAPE_LIMIT = 50;

const TickerTape = memo(function TickerTape({ marketTickers, activeCoins, coins, price, selectedCoin, positions, onSelectCoin }) {
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

function StrategyDropdown({ tradingPreset, presets, presetCategories, onPresetChange }) {
  const currentPreset = presets.find(p => p.id === tradingPreset);
  const grouped = presetCategories.length > 0;
  const sections = grouped
    ? presetCategories.map(cat => ({ cat, items: presets.filter(p => p.category === cat) })).filter(s => s.items.length > 0)
    : [{ cat: null, items: presets.length ? presets : [{ id: tradingPreset, name: tradingPreset, trader: "" }] }];

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
      <span style={{ fontSize: "7px", color: "#5C5C5C", letterSpacing: "1px", fontFamily: "'Space Mono',monospace" }}>STRAT</span>
      <select
        value={tradingPreset}
        onChange={e => onPresetChange(e.target.value)}
        title={currentPreset?.description}
        style={{
          fontFamily: "'Space Mono',monospace",
          fontSize: "9px",
          padding: "3px 20px 3px 6px",
          borderRadius: "4px",
          backgroundColor: "rgba(0,0,0,0.4)",
          backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='4' viewBox='0 0 10 6'%3E%3Cpath fill='%23D4AF37' d='M0 0l5 6 5-6z'/%3E%3C/svg%3E\")",
          backgroundRepeat: "no-repeat",
          backgroundPosition: "right 6px center",
          color: "#D4AF37",
          border: "1px solid #D4AF3722",
          cursor: "pointer",
          outline: "none",
          appearance: "none",
          minWidth: "120px",
          maxWidth: "180px",
        }}
        aria-label="Select strategy preset"
      >
        {sections.map((sec) =>
          sec.cat ? (
            <optgroup key={sec.cat} label={sec.cat}>
              {sec.items.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </optgroup>
          ) : (
            sec.items.map(p => <option key={p.id} value={p.id}>{p.name}</option>)
          )
        )}
      </select>
    </div>
  );
}

function Dashboard() {
  const navigate = useNavigate();
  const { user, profile, signOut } = useAuth();

  // ── Connection ──────────────────────────────────────────────────────────────
  const [connected,   setConnected]   = useState(false);
  const [cbLive,      setCbLive]      = useState(false);
  const [krakenEnabled, setKrakenEnabled] = useState(false);
  const [hasClaude,   setHasClaude]   = useState(false);
  const [paperMode,   setPaperMode]   = useState(true);
  const [agentKit,    setAgentKit]    = useState({ agentkit_ready:false, wallet_address:null, network:null, error:null });
  const [wsRetrying,  setWsRetrying]  = useState(false);

  // ── Multi-coin ──────────────────────────────────────────────────────────────
  const [coins,       setCoins]       = useState({});
  const [activeCoins, setActiveCoins] = useState(DEFAULT_COINS);
  const [selectedCoin, setSelectedCoin] = useState("BTC");
  const selectedCoinRef = useRef("BTC");
  const [chartSymbol, setChartSymbol] = useState("BTC");  // What's shown on the main chart (can be any ticker/exchange)
  const [marketTickers, setMarketTickers] = useState([]);  // Exchange top tickers for ticker tape
  const [tickerSearch, setTickerSearch] = useState("");
  const [tickerSearchOpen, setTickerSearchOpen] = useState(false);
  const [multiExchangePrices, setMultiExchangePrices] = useState({});  // { BTC: { binance, coinbase, kraken } }
  const tickerSearchRef = useRef(null);

  // ── Market (derived from selected coin) ───────────────────────────────────
  const [price,       setPrice]       = useState(0);
  const [prevPrice,   setPrevPrice]   = useState(0);
  const [change24h,   setChange24h]   = useState(0);
  const [priceSource, setPriceSource] = useState("coinbase");  // "coinbase" | "coingecko" — chart matches only when coinbase
  const [history,     setHistory]     = useState([]);
  const [indic,       setIndic]       = useState({ ema9:null, ema21:null, rsi:50, atr:0, bb_upper:0, bb_middle:0, bb_lower:0, bb_width:0, vwap:null });
  const [regime,      setRegime]      = useState("ranging");
  const [fearGreed,   setFearGreed]   = useState({ value: 50, label: "Neutral" });
  const [candles,     setCandles]     = useState([]);

  // ── Account ─────────────────────────────────────────────────────────────────
  const [startBal,    setStartBal]    = useState(1000);
  const [targetBal,   setTargetBal]   = useState(5000);
  const [account,     setAccount]     = useState({ balance: 1000, daily_pnl: 0, total_pnl: 0 });

  // ── Trading ─────────────────────────────────────────────────────────────────
  const [position,    setPosition]    = useState(null);
  const [positions,   setPositions]   = useState([]);
  const [maxPositions, setMaxPositions] = useState(3);
  const [maxFuturesPositions, setMaxFuturesPositions] = useState(0);
  const [enableFutures, setEnableFutures] = useState(false);
  const [trades,      setTrades]      = useState([]);
  const [decision,    setDecision]    = useState(null);
  const [lastAiBlockReason, setLastAiBlockReason] = useState(null);
  const [thinking,    setThinking]    = useState(false);
  const [botOn,       setBotOn]       = useState(false);
  const [lastCall,    setLastCall]    = useState("--");
  const [countdown,   setCountdown]   = useState(180);
  const [priceAge,    setPriceAge]    = useState(0);

  // ── Claude model ───────────────────────────────────────────────────────────
  const [claudeModel, setClaudeModel] = useState("claude-opus-4-20250514");

  // ── Confirm dialogs ────────────────────────────────────────────────────────
  const [confirmAction, setConfirmAction] = useState(null);

  // ── Approval mode & pending trade ───────────────────────────────────────────
  const [pendingDecision, setPendingDecision] = useState(null);
  const [pendingExpiresAt, setPendingExpiresAt] = useState(0);
  const [requireTradeApproval, setRequireTradeApproval] = useState(false);
  const [directionBias, setDirectionBias] = useState("both");
  const [pendingCountdown, setPendingCountdown] = useState(0);

  // ── Toast (loss notification) ──────────────────────────────────────────────
  const [lossToast, setLossToast] = useState(null);

  // ── Trading preset (top 100 trader strategies) ────────────────────────────
  const [tradingPreset, setTradingPreset] = useState("turtle");
  const [presets, setPresets] = useState(PRESETS_FALLBACK);
  const [presetCategories, setPresetCategories] = useState(PRESETS_CATEGORIES_FALLBACK);

  // ── Profit goal (configurable target, progress bar) ────────────────────────
  const [profitGoal, setProfitGoal] = useState(() => {
    try { const v = localStorage.getItem("claudebot_profit_goal"); return v ? Math.max(0, +v) : 4000; } catch { return 4000; }
  });
  useEffect(() => { if (profitGoal > 0) try { localStorage.setItem("claudebot_profit_goal", String(profitGoal)); } catch {} }, [profitGoal]);
  const profitGoalSyncRef = useRef(false);
  useEffect(() => {
    if (!profitGoalSyncRef.current) { profitGoalSyncRef.current = true; return; }
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ cmd: "set_profit_goal", profit_goal: profitGoal }));
    }
  }, [profitGoal]);

  // ── Backend config (fetched on mount, hardcoded fallbacks) ─────────────────
  const [roundTripFee, setRoundTripFee] = useState(DEFAULT_ROUND_TRIP_FEE);
  const roundTripFeeRef = useRef(DEFAULT_ROUND_TRIP_FEE);
  roundTripFeeRef.current = roundTripFee;
  useEffect(() => {
    const base = window.location.origin;
    const url = `${base}/api/config${API_SECRET ? `?secret=${encodeURIComponent(API_SECRET)}` : ""}`;
    fetch(url).then(r => r.ok ? r.json() : null).then(cfg => {
      if (!cfg) return;
      if (cfg.round_trip_fee) setRoundTripFee(cfg.round_trip_fee);
      if (cfg.symbol_to_coingecko) Object.assign(FALLBACK_SYMBOL_TO_COINGECKO, cfg.symbol_to_coingecko);
    }).catch(() => {});
  }, []);

  // ── Logs ────────────────────────────────────────────────────────────────────
  const [logs, setLogs] = useState([{ id: logId(), msg: "Connecting to backend...", type: "info", ts: "--:--:--" }]);
  const log = useCallback((msg, type = "info") =>
    setLogs(prev => [{ id: logId(), msg, type, ts: new Date().toLocaleTimeString() }, ...prev].slice(0, 60)), []);

  // ── Refs (always current, no stale closures) ─────────────────────────────────
  const wsRef        = useRef(null);
  const priceRef     = useRef(price);
  const accountRef   = useRef(account);
  const posRef       = useRef(position);
  const positionsRef = useRef(positions);
  const indicRef     = useRef(indic);
  const regimeRef    = useRef(regime);
  const tradesRef    = useRef(trades);
  const fearGreedRef = useRef(fearGreed);
  const botTimerRef  = useRef(null);
  const priceAgeRef  = useRef(null);
  const lastResetRef = useRef("");
  const thinkingRef  = useRef(false);
  const lastGoalReachedRef = useRef(false);
  const profitGoalRef = useRef(profitGoal);
  const change24hRef = useRef(change24h);
  const priceTimestampRef = useRef(0);
  const logsContainerRef = useRef(null);
  const tradesContainerRef = useRef(null);
  const lastStaggeredLogsRef = useRef(0);
  const lastStaggeredTradesRef = useRef(0);

  priceRef.current         = price;
  accountRef.current       = account;
  posRef.current           = position;
  positionsRef.current     = positions;
  indicRef.current         = indic;
  regimeRef.current        = regime;
  tradesRef.current        = trades;
  fearGreedRef.current     = fearGreed;
  thinkingRef.current      = thinking;
  change24hRef.current     = change24h;
  selectedCoinRef.current  = selectedCoin;
  profitGoalRef.current    = profitGoal;

  // ── Send to backend ──────────────────────────────────────────────────────────
  const send = useCallback((cmd, extra) => {
    if (wsRef.current?.readyState === WebSocket.OPEN)
      wsRef.current.send(JSON.stringify({ cmd, ...extra }));
  }, []);

  // ── Backend WebSocket ────────────────────────────────────────────────────────
  useEffect(() => {
    let ws, retryTimer, pingTimer, connectTimeout, disposed = false;
    let retryDelay = 2000;
    const MAX_RETRY = 30000;
    let hadConnection = false;

    function connect() {
      if (disposed) return;
      if (ws && ws.readyState !== WebSocket.CLOSED && ws.readyState !== WebSocket.CLOSING) {
        try { ws.close(); } catch {}
      }
      setWsRetrying(true);
      ws = new WebSocket(getBackendWsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        if (disposed) { ws.close(); return; }
        retryDelay = 2000;
        hadConnection = true;
        setConnected(true);
        setWsRetrying(false);
        try { ws.send(JSON.stringify({ cmd: "set_profit_goal", profit_goal: profitGoalRef.current })); } catch {}
        if (botTimerRef.current){ clearInterval(botTimerRef.current); botTimerRef.current = null; }
        if (priceAgeRef.current){ clearInterval(priceAgeRef.current); priceAgeRef.current = null; }
        priceAgeRef.current = setInterval(() => setPriceAge(p => p + 1), 1000);
        log("Backend connected — real-time data active", "success");
        if (pingTimer) clearInterval(pingTimer);
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try { ws.send(JSON.stringify({ cmd: "ping" })); } catch {}
          }
        }, 25000);
      };

      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data);
          if (m.type === "pong") return;
          if (m.coins) {
            setCoins(prev => {
              const updated = { ...prev };
              for (const [sym, data] of Object.entries(m.coins)) {
                updated[sym] = { ...(prev[sym] || {}), ...data };
              }
              return updated;
            });
            // Sync header to selected coin's price + age whenever coins update
            const sel = selectedCoinRef.current;
            const cd = m.coins[sel];
            if (cd?.price != null) {
              setPrevPrice(priceRef.current);
              setPrice(cd.price);
              setPriceAge(cd.price_age_sec ?? 0);
              priceTimestampRef.current = Date.now();
              setPriceSource("coinbase");  // Backend uses Coinbase — matches TradingView
            }
            if (cd?.price_change24h != null) setChange24h(cd.price_change24h);
          }
          if (m.active_coins) setActiveCoins(m.active_coins);
          if (m.type === "full_state" && Array.isArray(m.market_tickers) && m.market_tickers.length > 0) {
            setMarketTickers(m.market_tickers.map((c) => ({
              sym: (c.sym || c.symbol || "").toUpperCase(),
              price: c.price ?? 0,
              chg24h: c.chg24h ?? null,
              image: c.image || null,
            })).filter((x) => x.sym));
          }

          const isBtcSelected = selectedCoinRef.current === "BTC";
          if (isBtcSelected) {
            if (m.price != null)            { setPrevPrice(priceRef.current); setPrice(m.price); setPriceAge(m.coins?.BTC?.price_age_sec ?? 0); priceTimestampRef.current = Date.now(); setPriceSource("coinbase"); }
            if (m.price_change24h != null)  setChange24h(m.price_change24h);
            if (m.history)                  setHistory(m.history);
            if (m.indicators)               setIndic(m.indicators);
            if (m.market_condition)         setRegime(m.market_condition);
            if (m.candles) {
              setCandles(prev => {
                if (m.type === "full_state") return m.candles;
                const merged = [...prev];
                for (const c of m.candles) {
                  const idx = merged.findIndex(x => x.time === c.time);
                  if (idx >= 0) merged[idx] = c;
                  else merged.push(c);
                }
                merged.sort((a, b) => a.time - b.time);
                return merged.slice(-300);
              });
            }
          }
          if (m.account) {
            setAccount(m.account);
            // Celebrate when hitting your configured profit goal
            const pnl = m.account.total_pnl;
            const goal = profitGoalRef.current || 0;
            if (goal > 0 && pnl >= goal && !lastGoalReachedRef.current) {
              lastGoalReachedRef.current = true;
              confetti({ particleCount: 150, spread: 100, origin: { y: 0.6 }, colors: ["#D4AF37", "#B8860B", "#FFD700", "#C0392B"] });
              setTimeout(() => confetti({ particleCount: 100, spread: 80, origin: { y: 0.5, x: 0.3 }, colors: ["#D4AF37", "#B8860B", "#FFD700"] }), 150);
              setTimeout(() => confetti({ particleCount: 100, spread: 80, origin: { y: 0.5, x: 0.7 }, colors: ["#D4AF37", "#B8860B", "#FFD700"] }), 300);
            }
            if (pnl < goal) lastGoalReachedRef.current = false;
          }
          if (m.open_position !== undefined) setPosition(m.open_position);
          if (m.open_positions !== undefined) setPositions(m.open_positions);
          if (m.max_positions != null)    setMaxPositions(m.max_positions);
          if (m.max_futures_positions != null) setMaxFuturesPositions(m.max_futures_positions);
          if (m.enable_futures != null)  setEnableFutures(m.enable_futures);
          if (m.trades) {
            setTrades(m.trades);
            if (m.type === "trade_update" && m.trades?.length > 0) {
              const latest = m.trades[0];
              const prevLatest = tradesRef.current[0];
              const isNewTrade = !prevLatest || latest.id !== prevLatest.id;
              if (isNewTrade && latest.win) {
                confetti({ particleCount: 100, spread: 100, origin: { y: 0.6 }, colors: ["#D4AF37", "#B8860B", "#FFD700", "#00E676"] });
                setTimeout(() => confetti({ particleCount: 60, spread: 80, origin: { y: 0.5, x: 0.3 }, colors: ["#D4AF37", "#FFD700"] }), 120);
                setTimeout(() => confetti({ particleCount: 60, spread: 80, origin: { y: 0.5, x: 0.7 }, colors: ["#D4AF37", "#FFD700"] }), 240);
              } else if (isNewTrade && !latest.win) {
                const sym = latest.symbol || "Position";
                setLossToast({ msg: `${sym} closed — $${Math.abs(latest.pnl).toFixed(2)} loss` });
                setTimeout(() => setLossToast(null), 4000);
              }
            }
          }
          if (m.claude_decision)          setDecision(m.claude_decision);
          if (m.last_ai_block_reason !== undefined) setLastAiBlockReason(m.last_ai_block_reason);
          if (m.pending_decision !== undefined) setPendingDecision(m.pending_decision);
          if (m.pending_expires_at != null)    setPendingExpiresAt(m.pending_expires_at);
          if (m.require_trade_approval != null) setRequireTradeApproval(m.require_trade_approval);
          if (m.direction_bias)                 setDirectionBias(m.direction_bias);
          if (m.trading_preset)                 setTradingPreset(m.trading_preset);
          if (m.type === "preset_changed")       setTradingPreset(m.trading_preset);
          if (m.type === "pending_trade") {
            setPendingDecision(m.pending_decision ?? null);
            if (m.pending_expires_at != null) setPendingExpiresAt(m.pending_expires_at);
          }
          if (m.bot_running  != null)     setBotOn(m.bot_running);
          if (m.claude_thinking != null)  setThinking(m.claude_thinking);
          if (m.last_claude_call)         setLastCall(m.last_claude_call);
          if (m.countdown != null)        setCountdown(m.countdown);
          if (m.has_claude_key != null)   setHasClaude(m.has_claude_key);
          if (m.paper_trading  != null)   setPaperMode(m.paper_trading);
          if (m.coinbase_connected != null) setCbLive(m.coinbase_connected);
          if (m.kraken_enabled != null) setKrakenEnabled(m.kraken_enabled);
          if (m.fear_greed)               setFearGreed(m.fear_greed);
          if (m.agentkit)                 setAgentKit(m.agentkit);
          if (m.start_balance != null)    setStartBal(m.start_balance);
          if (m.target_balance != null)   setTargetBal(m.target_balance);
          if (m.profit_goal != null && m.profit_goal > 0) setProfitGoal(m.profit_goal);
          else if (m.profit_to_target != null && profitGoalRef.current === 0) setProfitGoal(m.profit_to_target);
          if (m.claude_model)             setClaudeModel(m.claude_model);
          if (m.logs)                     setLogs(m.logs.map((l, i) => ({ ...l, id: l.id || `srv_${i}` })));
          if (m.type === "wallet_status") setAgentKit(prev => ({ ...prev, ...m }));
          if (m.type === "log" && m.entry) setLogs(prev => [{ ...m.entry, id: logId() }, ...prev].slice(0, 60));
        } catch { /* ignore parse errors */ }
      };

      ws.onerror = () => {};
      ws.onclose = (ev) => {
        if (disposed) return;
        if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
        if (priceAgeRef.current) { clearInterval(priceAgeRef.current); priceAgeRef.current = null; }
        setConnected(false);
        setCbLive(false);
        setKrakenEnabled(false);
        setWsRetrying(true);
        if (hadConnection) {
          log("Backend disconnected — reconnecting...", "warning");
        } else {
          log("Backend offline — start backend.py for live trading.", "warning");
        }
        retryTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 1.5, MAX_RETRY);
      };
    }

    // Defer connect to avoid React Strict Mode double-mount: cleanup runs before deferred connect
    connectTimeout = setTimeout(() => {
      connectTimeout = null;
      if (!disposed) connect();
    }, 0);

    return () => {
      disposed = true;
      if (connectTimeout) clearTimeout(connectTimeout);
      clearTimeout(retryTimer);
      if (pingTimer) clearInterval(pingTimer);
      if (ws && ws.readyState !== WebSocket.CLOSED && ws.readyState !== WebSocket.CLOSING) {
        try { ws.close(); } catch {}
      }
      wsRef.current = null;
    };
  }, [log]);

  // ── Periodic account sync (failsafe so balance/P&L always reflect backend) ───
  useEffect(() => {
    if (!connected) return;
    const apiBase = BACKEND_BASE;
    const url = apiBase ? `${apiBase.replace(/\/$/, "")}/account` : "/account";
    const headers = {};
    if (API_SECRET) headers["x-bot-secret"] = API_SECRET;
    const sync = async () => {
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 5000);
        const r = await fetch(url, { headers, signal: ctrl.signal });
        clearTimeout(to);
        if (!r.ok) return;
        const d = await r.json();
        setAccount(a => ({
          ...a,
          balance:   d.balance ?? a.balance,
          daily_pnl: d.daily_pnl ?? a.daily_pnl,
          total_pnl: d.total_pnl ?? a.total_pnl,
        }));
        if (d.start_balance != null) setStartBal(d.start_balance);
        if (d.target_balance != null) setTargetBal(d.target_balance);
      } catch {}
    };
    sync(); // immediate sync on connect
    const id = setInterval(sync, 10000); // 10s — WS pushes account; REST is backup only
    return () => clearInterval(id);
  }, [connected]);

  // ── Price fetch: backend first (Coinbase), then direct CoinGecko when backend fails ─
  const CG_IDS = { BTC:"bitcoin", ETH:"ethereum", SOL:"solana", DOGE:"dogecoin", LINK:"chainlink", AVAX:"avalanche-2", UNI:"uniswap", AAVE:"aave", XRP:"ripple", ADA:"cardano" };
  const fetchCoinGeckoDirect = async (sel) => {
    const cgId = CG_IDS[sel] || "bitcoin";
    const r = await fetch(`https://api.coingecko.com/api/v3/simple/price?ids=${cgId}&vs_currencies=usd&include_24hr_change=true`);
    if (!r.ok) return false;
    const d = await r.json();
    const v = d[cgId];
    if (v?.usd > 0) {
      setPrevPrice(priceRef.current);
      setPrice(v.usd);
      setPriceAge(0);
      priceTimestampRef.current = Date.now();
      setChange24h(v.usd_24h_change ?? 0);
      setCoins(prev => ({ ...prev, [sel]: { price: v.usd, price_change24h: v.usd_24h_change ?? 0 } }));
      setPriceSource("coingecko");  // Backend down — doesn't match TradingView
      return true;
    }
    return false;
  };

  useEffect(() => {
    const apiBase = BACKEND_BASE;
    const base = apiBase ? apiBase.replace(/\/$/, "") : "";
    const tickersUrl = base ? `${base}/api/coinbase/tickers` : "/api/coinbase/tickers";
    const headers = {};
    if (API_SECRET) headers["x-bot-secret"] = API_SECRET;
    const PRICE_FALLBACK_MS = 2000;  // 2s — keeps header moving in real time; WS provides sub-second when Coinbase connected
    const STALE_THRESHOLD_MS = 10000;  // Force refresh if no update in 10s (WS likely stalled)

    const fetchPrice = async () => {
      const sel = selectedCoinRef.current;
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 5000);
        const r = await fetch(`${tickersUrl}?symbols=${encodeURIComponent(activeCoins.join(","))}`, { headers, signal: ctrl.signal });
        clearTimeout(to);
        if (r.ok) {
          const d = await r.json();
          let coinData = d?.coins;
          if (!coinData?.BTC && d?.bitcoin?.usd) {
            coinData = { BTC: { price: d.bitcoin.usd, price_change24h: d.bitcoin.usd_24h_change || 0 } };
          }
          if (coinData && Object.keys(coinData).length > 0) {
            setCoins(prev => ({ ...prev, ...coinData }));
          }
          const cd = coinData?.[sel];
          if (cd?.price != null && cd.price > 0) {
            setPrevPrice(priceRef.current);
            setPrice(cd.price);
            setPriceAge(0);
            priceTimestampRef.current = Date.now();
            if (cd.price_change24h != null) setChange24h(cd.price_change24h);
            setPriceSource("coinbase");  // Backend uses Coinbase — matches TradingView
            return;
          }
        }
      } catch { /* backend unreachable */ }
      if (priceRef.current <= 0) await fetchCoinGeckoDirect(sel);
    };

    fetchPrice(); // immediate
    const pollId = setInterval(fetchPrice, PRICE_FALLBACK_MS);
    // Staleness check (only when connected): if WS stops pushing, trigger immediate refresh
    const staleId = connected ? setInterval(() => {
      if (priceTimestampRef.current <= 0) return;
      const age = Date.now() - priceTimestampRef.current;
      if (age > STALE_THRESHOLD_MS && priceRef.current > 0) {
        fetchPrice(); // Force refresh — WS likely stalled
      }
    }, 5000) : null;
    return () => {
      clearInterval(pollId);
      if (staleId) clearInterval(staleId);
    };
  }, [connected, activeCoins, cbLive]);

  // ── Coinbase WebSocket — real-time price stream matching TradingView ─────────
  useEffect(() => {
    let ws, disposed = false, reconnectTimer;
    const CB_WS = "wss://ws-feed.exchange.coinbase.com";
    const productId = `${selectedCoinRef.current}-USD`;

    function connect() {
      if (disposed) return;
      try { ws = new WebSocket(CB_WS); } catch { scheduleReconnect(); return; }

      ws.onopen = () => {
        if (disposed) { ws.close(); return; }
        ws.send(JSON.stringify({
          type: "subscribe",
          product_ids: [productId],
          channels: ["ticker"],
        }));
      };

      ws.onmessage = (evt) => {
        try {
          const m = JSON.parse(evt.data);
          if (m.type !== "ticker" || m.product_id !== `${selectedCoinRef.current}-USD`) return;
          const p = parseFloat(m.price);
          if (!p || p <= 0) return;
          setPrevPrice(priceRef.current);
          setPrice(p);
          setPriceAge(0);
          priceTimestampRef.current = Date.now();
          setPriceSource("coinbase");
          const open24 = parseFloat(m.open_24h);
          if (open24 > 0) setChange24h(((p - open24) / open24) * 100);
        } catch {}
      };

      ws.onclose = () => { if (!disposed) scheduleReconnect(); };
      ws.onerror = () => { try { ws.close(); } catch {} };
    }

    function scheduleReconnect() {
      if (disposed) return;
      reconnectTimer = setTimeout(connect, 3000);
    }

    connect();

    return () => {
      disposed = true;
      clearTimeout(reconnectTimer);
      if (ws && ws.readyState !== WebSocket.CLOSED && ws.readyState !== WebSocket.CLOSING) {
        try { ws.close(); } catch {}
      }
    };
  }, [selectedCoin]);

  // ── Market tickers for ticker tape — exchange top 50 by volume ───
  useEffect(() => {
    const base = (BACKEND_BASE || "").replace(/\/$/, "");
    const url = base ? `${base}/api/exchange/tickers` : "/api/exchange/tickers";
    const headers = {};
    if (API_SECRET) headers["x-bot-secret"] = API_SECRET;
    async function fetchMarkets() {
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 15000);
        const r = await fetch(`${url}?limit=500`, { headers, signal: ctrl.signal });
        clearTimeout(to);
        if (!r.ok) return;
        const arr = await r.json();
        if (Array.isArray(arr) && arr.length > 0) {
          const mapped = arr.map((c) => ({
            sym: (c.sym || c.symbol || "").toUpperCase(),
            price: c.price ?? 0,
            chg24h: c.chg24h ?? null,
            image: c.image || null,
          })).filter((x) => x.sym);
          if (mapped.length > 0) {
            setMarketTickers(mapped);
          }
        }
      } catch { /* non-critical, ticker works with coins/activeCoins fallback */ }
    }
    fetchMarkets();
    const t = setInterval(fetchMarkets, 120000);
    return () => clearInterval(t);
  }, []);

  // ── Ticker search: click outside to close dropdown ─────────────────────────
  useEffect(() => {
    if (!tickerSearchOpen) return;
    const handler = (e) => {
      if (tickerSearchRef.current && !tickerSearchRef.current.contains(e.target)) setTickerSearchOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [tickerSearchOpen]);

  // ── Multi-exchange prices for arbitrage (when search dropdown opens) ───────
  useEffect(() => {
    if (!tickerSearchOpen) return;
    const q = tickerSearch.trim().toUpperCase();
    const matches = q
      ? marketTickers.filter(t => (t.sym || "").toUpperCase().includes(q)).slice(0, 8)
      : marketTickers.slice(0, 6);
    let syms = [...new Set(matches.map(t => (t.sym || "").toUpperCase()).filter(Boolean))];
    if (q && !syms.includes(q)) syms.push(q);
    if (syms.length === 0) syms = ["BTC", "ETH", "SOL", "XRP", "DOGE"];
    const base = (BACKEND_BASE || "").replace(/\/$/, "");
    const url = base ? `${base}/api/prices/multi` : "/api/prices/multi";
    const headers = {};
    if (API_SECRET) headers["x-bot-secret"] = API_SECRET;
    fetch(`${url}?symbols=${encodeURIComponent(syms.join(","))}`, { headers })
      .then(r => r.ok && r.json())
      .then(d => d && typeof d === "object" && setMultiExchangePrices(d))
      .catch(() => {});
  }, [tickerSearchOpen, tickerSearch, marketTickers]);

  // ── Fear & Greed index ─────────────────────────────────────────────────────
  useEffect(() => {
    async function fetchFG() {
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 5000);
        const r = await fetch("/api/alternative/fng/", { signal: ctrl.signal });
        clearTimeout(to);
        const d = await r.json();
        setFearGreed({ value: +d.data[0].value, label: d.data[0].value_classification });
      } catch { /* non-critical */ }
    }
    fetchFG();
    const t = setInterval(fetchFG, 3600000);
    return () => clearInterval(t);
  }, []);

  // ── Pending trade countdown ─────────────────────────────────────────────────
  useEffect(() => {
    if (!pendingDecision || pendingExpiresAt <= 0) return;
    const update = () => setPendingCountdown(Math.max(0, Math.ceil(pendingExpiresAt - Date.now() / 1000)));
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [pendingDecision, pendingExpiresAt]);

  // ── Fetch trading presets when connected ───────────────────────────────────
  useEffect(() => {
    if (!connected) return;
    const url = BACKEND_BASE ? `${BACKEND_BASE}/api/presets` : "/api/presets";
    fetch(url, { headers: authHeaders() }).then(r => r.ok && r.json()).then(d => {
      if (d?.presets?.length) {
        setPresets(d.presets);
        setPresetCategories(d.categories || []);
      }
    }).catch(() => {});
  }, [connected]);

  // ── Midnight P&L reset (display) ────────────────────────────────────────────
  useEffect(() => {
    const t = setInterval(() => {
      const now   = new Date();
      const today = now.toDateString();
      if (now.getHours() === 0 && now.getMinutes() === 0 && lastResetRef.current !== today) {
        lastResetRef.current = today;
        setAccount(a => ({ ...a, daily_pnl: 0 }));
        log("Daily P&L reset (midnight)", "info");
      }
    }, 60000);
    return () => clearInterval(t);
  }, [log]);

  const callClaude = useCallback(async () => {
    if (thinkingRef.current) return;
    setThinking(true);
    setLastCall(new Date().toLocaleTimeString());
    log("Claude analyzing live market data...", "claude");

    try {
      const backendBase = BACKEND_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;
      const headers = {};
      if (API_SECRET) headers["x-bot-secret"] = API_SECRET;
      const res = await fetch(`${backendBase}/ask_claude`, { method: "POST", headers });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `Backend returned ${res.status}`);
      }

      const dec = await res.json();
      setDecision(dec);
      log(`Claude: ${dec.action?.toUpperCase()} — ${dec.reasoning?.slice(0, 80) || ""}`, dec.action === "wait" ? "dim" : "claude");
    } catch (e) {
      if (e.message?.toLowerCase().includes("failed to fetch") || e.message?.toLowerCase().includes("networkerror")) {
        log("Backend offline — cannot reach Claude. Start python backend.py", "warning");
        setDecision({ reasoning: "Backend offline. Start backend.py for AI trading.", action: "wait", confidence: 0, market_condition: regimeRef.current });
      } else {
        log(`Claude error: ${e.message}`, "error");
      }
    } finally {
      setThinking(false);
    }
  }, [log]);

  // ── Handlers ─────────────────────────────────────────────────────────────────
  const handleStart = () => {
    if (connected) { send("start_bot"); }
    else { log("Start backend.py first", "warning"); }
  };
  const handleStop = () => {
    if (connected) { send("stop_bot"); }
    else { log("Backend offline", "warning"); }
  };
  const handleAsk = () => {
    if (connected) send("ask_claude", { direct: true });
    else callClaude();  // callClaude will show "Backend offline" if unreachable
  };
  const handleModelChange = (model) => {
    setClaudeModel(model);
    if (connected) send("set_model", { model });
    log(`Model switched to ${model}`, "info");
  };
  const handlePresetChange = (presetId) => {
    setTradingPreset(presetId);
    if (connected) send("set_preset", { preset: presetId });
    const preset = presets.find(p => p.id === presetId);
    log(`Strategy: ${preset?.name || presetId}`, "info");
  };

  const handleApprovePending = () => {
    if (connected && pendingDecision) send("approve_pending");
    else log("No pending trade or backend offline", "warning");
  };
  const handleRejectPending = () => {
    if (connected && pendingDecision) send("reject_pending");
    else if (!connected) setPendingDecision(null);
    log("Pending trade rejected", "dim");
  };

  const handleClose = (posToClose) => {
    if (!positions.length && !connected) return;
    const sym = posToClose?.symbol || "ALL";
    const label = posToClose
      ? `Close ${posToClose.side?.toUpperCase()} ${posToClose.symbol} position? Unrealized P&L will be realized at current price.`
      : "Close ALL open positions?";
    setConfirmAction({ type: "close", label, pos: posToClose });
  };
  const handleReset = () => {
    setConfirmAction({ type: "reset", label: `Reset account to $${startBal}? All positions and local trade history will be cleared.` });
  };
  const confirmYes = () => {
    const act = confirmAction;
    setConfirmAction(null);
    if (!act) return;
    if (act.type === "close") {
      if (connected) {
        const extra = {};
        if (act.pos?.id) extra.pos_id = act.pos.id;
        else if (act.pos?.symbol) extra.symbol = act.pos.symbol;
        send("close_position", extra);
        return;
      }
      const closeTargets = act.pos ? [act.pos] : positionsRef.current;
      if (!closeTargets.length) return;
      let totalNet = 0;
      const newTrades = [];
      for (const pos of closeTargets) {
        const coinPrice = coins[pos.symbol]?.price || priceRef.current;
        const closeSz = pos.coin_size || pos.btc_size || 0;
        const pnl = pos.side==="buy" ? (coinPrice-pos.entry)*closeSz : (pos.entry-coinPrice)*closeSz;
        const net = +(pnl - pos.usd_size * roundTripFeeRef.current).toFixed(2);
        totalNet += net;
        newTrades.push({ id:Date.now()+Math.random(), symbol:pos.symbol, side:pos.side, entry:pos.entry, exit:coinPrice, pnl:net, reason:"MANUAL CLOSE", ts:new Date().toLocaleTimeString(), win:net>0 });
        setAccount(a => ({ balance:+(a.balance+pos.usd_size+net).toFixed(2), daily_pnl:+(a.daily_pnl+net).toFixed(2), total_pnl:+(a.total_pnl+net).toFixed(2) }));
      }
      setTrades(p => [...newTrades, ...p].slice(0,30));
      if (act.pos) {
        setPositions(prev => prev.filter(p => p.id !== act.pos.id));
      } else {
        setPositions([]);
      }
      setPosition(null);
      log(`MANUAL CLOSE | Net: ${totalNet>=0?"+":""}$${totalNet.toFixed(2)}`, totalNet>=0?"success":"warning");
    } else if (act.type === "reset") {
      if (connected) { send("reset_account"); return; }
      lastGoalReachedRef.current = false;
      setAccount({ balance:startBal, daily_pnl:0, total_pnl:0 });
      setPosition(null);
      setPositions([]);
      setTrades([]);
      setDecision(null);
      log(`Account reset to $${startBal}`, "warning");
    }
  };

  // ── Full Trade History (from database) ──────────────────────────────────────
  const [historyTrades,   setHistoryTrades]   = useState([]);
  const [historyTotal,    setHistoryTotal]    = useState(0);
  const [historyStats,    setHistoryStats]    = useState({ wins:0, losses:0, win_rate:0, total_pnl:0 });
  const [historyLoading,  setHistoryLoading]  = useState(false);
  const [historyPage,     setHistoryPage]     = useState(0);
  const [historyLimit]                        = useState(50);
  const [historyFilters,  setHistoryFilters]  = useState({ date_from:"", date_to:"", symbol:"", side:"", result:"", product_type:"" });
  const [showHistory,     setShowHistory]     = useState(false);

  // ── Trade Detail Modal (chart screenshots) ──────────────────────────────────
  const [tradeDetail,     setTradeDetail]     = useState(null);
  const [tradeDetailLoading, setTradeDetailLoading] = useState(false);
  const [tradeDetailTab,  setTradeDetailTab]  = useState("exit");

  const openTradeDetail = useCallback(async (tr) => {
    setTradeDetail({ trade: tr, screenshots: null, context: null, audit: null });
    setTradeDetailLoading(true);
    setTradeDetailTab("exit");
    try {
      const backendBase = BACKEND_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;
      const res = await fetch(`${backendBase}/api/trade/${tr.id}/context`, { headers: authHeaders() });
      if (res.ok) {
        const data = await res.json();
        setTradeDetail(prev => ({ ...prev, ...data, trade: data.trade || tr }));
      }
    } catch (e) {
      log(`Failed to load trade detail: ${e.message}`, "dim");
    } finally {
      setTradeDetailLoading(false);
    }
  }, [log]);

  const closeTradeDetail = useCallback(() => {
    setTradeDetail(null);
  }, []);

  const fetchHistory = useCallback(async (page = 0, filters = historyFilters) => {
    setHistoryLoading(true);
    try {
      const backendBase = BACKEND_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;
      const params = new URLSearchParams();
      params.set("limit", historyLimit);
      params.set("offset", page * historyLimit);
      if (filters.date_from) params.set("date_from", filters.date_from);
      if (filters.date_to)   params.set("date_to", filters.date_to);
      if (filters.symbol)    params.set("symbol", filters.symbol);
      if (filters.side)      params.set("side", filters.side);
      if (filters.result)    params.set("result", filters.result);
      if (filters.product_type) params.set("product_type", filters.product_type);
      const res = await fetch(`${backendBase}/trades/history?${params}`, { headers: authHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setHistoryTrades(data.trades || []);
      setHistoryTotal(data.total || 0);
      setHistoryStats({ wins: data.wins||0, losses: data.losses||0, win_rate: data.win_rate||0, total_pnl: data.total_pnl||0 });
      setHistoryPage(page);
    } catch (e) {
      log(`Failed to load history: ${e.message}`, "error");
    } finally {
      setHistoryLoading(false);
    }
  }, [historyFilters, historyLimit, log]);

  const applyHistoryFilter = (key, value) => {
    const next = { ...historyFilters, [key]: value };
    setHistoryFilters(next);
    fetchHistory(0, next);
  };

  const clearHistoryFilters = () => {
    const blank = { date_from:"", date_to:"", symbol:"", side:"", result:"", product_type:"" };
    setHistoryFilters(blank);
    fetchHistory(0, blank);
  };

  const tradeTypeBadge = (tr) => {
    const exBadge = tr.exchange === "kraken"
      ? <span className="tag" style={{ background:"#7b61ff18", color:"#7b61ff", fontSize:"9px", marginLeft:"3px" }}>KRAKEN</span>
      : tr.exchange === "coinbase"
      ? <span className="tag" style={{ background:"#0052ff18", color:"#4d8ffa", fontSize:"9px", marginLeft:"3px" }}>COINBASE</span>
      : null;
    if (tr.onchain) return <><span className="tag" style={{ background:"#D4AF3718", color:"#D4AF37", fontSize:"9px" }}>ON-CHAIN</span>{exBadge}</>;
    if (tr.product_type === "futures") return <><span className="tag" style={{ background:"#D4AF3718", color:"#D4AF37", fontSize:"9px" }}>FUTURES{tr.leverage ? ` ${tr.leverage}x` : ""}</span>{exBadge}</>;
    return <><span className="tag" style={{ background:"#2a2a2a", color:"#64748b", fontSize:"9px" }}>SPOT</span>{exBadge}</>;
  };

  // ── Export trades as CSV ───────────────────────────────────────────────────────
  const exportTrades = (tradeList) => {
    const list = tradeList || trades;
    if (list.length === 0) return;
    const typeLabel = (t) => t.onchain ? "ON-CHAIN" : (t.product_type === "futures" ? `FUTURES ${t.leverage || 1}x` : "SPOT");
    const header = "Date,Time,Symbol,Side,Type,Entry,Exit,PnL,Reason,Win\n";
    const rows = list.map(t =>
      `${t.created_at||""},${t.ts},${t.symbol||"BTC"},${t.side},${typeLabel(t)},${t.entry},${t.exit},${t.pnl},"${t.reason}",${t.win}`
    ).join("\n");
    const blob = new Blob([header + rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `claudebot_trades_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    log("Trade history exported as CSV", "info");
  };

  // ── Stagger-in animations for logs & trades (Anime.js) — only new items to avoid flash
  useLayoutEffect(() => {
    const container = logsContainerRef.current;
    if (!container) return;
    const prev = lastStaggeredLogsRef.current;
    const n = logs.length;
    if (n < prev) lastStaggeredLogsRef.current = 0;
    if (n === 0) return;
    const newCount = Math.min(Math.max(0, n - lastStaggeredLogsRef.current), 8);
    if (newCount > 0) {
      staggerIn(container, ".logrow", { start: 0, limit: newCount, delay: 40, duration: 140 });
      lastStaggeredLogsRef.current = n;
    } else if (lastStaggeredLogsRef.current === 0 && n > 0) {
      staggerIn(container, ".logrow", { limit: 8, delay: 35, duration: 140 });
      lastStaggeredLogsRef.current = n;
    }
  }, [logs]);
  useLayoutEffect(() => {
    const container = tradesContainerRef.current;
    if (!container) return;
    const prev = lastStaggeredTradesRef.current;
    const n = trades.length;
    if (n < prev) lastStaggeredTradesRef.current = 0;
    if (n === 0) return;
    const newCount = Math.min(Math.max(0, n - lastStaggeredTradesRef.current), 6);
    if (newCount > 0) {
      staggerIn(container, ".trow", { start: 0, limit: newCount, delay: 50, duration: 150 });
      lastStaggeredTradesRef.current = n;
    } else if (lastStaggeredTradesRef.current === 0 && n > 0) {
      staggerIn(container, ".trow", { limit: 8, delay: 45, duration: 150 });
      lastStaggeredTradesRef.current = n;
    }
  }, [trades]);

  // ── Coin switching: update view when selected coin changes or its data updates
  useEffect(() => {
    const cd = coins[selectedCoin];
    if (!cd) return;
    if (cd.price != null)           { setPrevPrice(priceRef.current); setPrice(cd.price); setPriceAge(cd.price_age_sec ?? 0); priceTimestampRef.current = Date.now(); }
    if (cd.price_change24h != null) setChange24h(cd.price_change24h);
    if (cd.history)                 setHistory(cd.history);
    if (cd.indicators)              setIndic(cd.indicators);
    if (cd.market_condition)        setRegime(cd.market_condition);
    if (cd.candles)                 setCandles(cd.candles);
  }, [selectedCoin, coins, connected]); // eslint-disable-line

  // ── Derived (memoized to avoid cascade re-renders) ──────────────────────────────
  const priceUp = useMemo(
    () => price >= prevPrice && prevPrice > 0,
    [price, prevPrice]
  );
  const winRate = useMemo(
    () => trades.length ? Math.round(trades.filter(t => t.win).length / trades.length * 100) : 0,
    [trades]
  );
  const totalUnrealized = useMemo(
    () => positions.reduce((sum, pos) => {
      const cp = coins[pos.symbol]?.price || price;
      const sz = pos.coin_size || pos.btc_size || 0;
      return sum + (pos.side === "buy" ? (cp - pos.entry) * sz : (pos.entry - cp) * sz);
    }, 0),
    [positions, coins, price]
  );
  const unrealized = useMemo(() => +totalUnrealized.toFixed(2), [totalUnrealized]);
  const condColor = useMemo(() => ({ ranging:"#D4AF37", trending_up:"#00E676", trending_down:"#FF1744", chaotic:"#ff9900" }[regime] || "#5C5C5C"), [regime]);
  const condLabel = useMemo(() => ({ ranging:"RANGING", trending_up:"TRENDING UP", trending_down:"TRENDING DOWN", chaotic:"CHAOTIC" }[regime] || regime), [regime]);
  const condIcon = useMemo(() => ({ ranging:"\u25C8", trending_up:"\u25B2", trending_down:"\u25BC", chaotic:"\u26A1" }[regime] || ""), [regime]);
  const dailyLossPct = useMemo(() => Math.abs(Math.min(0, account.daily_pnl) / Math.max(account.balance, 1) * 100), [account.daily_pnl, account.balance]);
  const fgColor = useMemo(() => fearGreed.value < 25 ? "#FF1744" : fearGreed.value < 50 ? "#ff9900" : fearGreed.value < 75 ? "#D4AF37" : "#00E676", [fearGreed.value]);
  const isLiveMode = !paperMode;

  const priceFormat = useCallback((v) => {
    if (v < 10) return v.toFixed(4);
    if (v < 1000) return v.toFixed(2);
    return v.toLocaleString();
  }, []);

  return (
    <div className="app-root" style={{ fontFamily:"'Space Mono',monospace", background:"#0A0A0A", color:"#D4D4D4",  padding:"20px 24px 40px", fontSize:"12px" }}>
      <style>{`
        *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
        ::-webkit-scrollbar{width:3px;height:3px}::-webkit-scrollbar-track{background:#0A0A0A}::-webkit-scrollbar-thumb{background:#2a2a2a;border-radius:2px}
        *{scrollbar-width:thin;scrollbar-color:#2a2a2a #0A0A0A}
        .card{background:#111111;border:1px solid #1e1e1e;border-radius:8px;padding:16px;position:relative}
        .card::before,.card::after{content:'';position:absolute;width:12px;height:12px;pointer-events:none}
        .card::before{top:-1px;left:-1px;border-top:2px solid #D4AF37;border-left:2px solid #D4AF37;border-radius:8px 0 0 0}
        .card::after{bottom:-1px;right:-1px;border-bottom:2px solid #D4AF37;border-right:2px solid #D4AF37;border-radius:0 0 8px 0}
        .grid{display:grid;grid-template-columns:260px 1fr 260px;gap:14px}
        .grid-bottom{display:grid;grid-template-columns:300px 1fr 300px;gap:16px;margin-top:16px}
        .col{display:flex;flex-direction:column;gap:14px}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
        @keyframes fadein{from{opacity:0;transform:translateY(-3px)}to{opacity:1;transform:translateY(0)}}
        @keyframes skeleton-shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
        @keyframes punchImpact{0%{box-shadow:0 0 0 0 rgba(212,175,55,0.6)}50%{box-shadow:0 0 40px 10px rgba(212,175,55,0.3)}100%{box-shadow:0 0 0 0 transparent}}
        .pulse{animation:pulse 2s infinite}.blink{animation:pulse 0.7s infinite}.fadein{animation:fadein 0.3s ease}
        .btn{font-family:'Oswald',sans-serif;font-size:11px;font-weight:600;letter-spacing:2px;text-transform:uppercase;padding:8px 16px;border:none;border-radius:3px;cursor:pointer;transition:all 0.15s;touch-action:manipulation;min-height:36px}
        .btn:disabled{opacity:.4;cursor:not-allowed}
        .btn:focus-visible{outline:2px solid #D4AF37;outline-offset:2px}
        .btn-g{background:linear-gradient(180deg,#D4AF37,#B8860B);color:#0A0A0A;font-weight:700}.btn-g:hover:not(:disabled){background:linear-gradient(180deg,#E5C04B,#D4AF37);transform:translateY(-1px);box-shadow:0 4px 16px rgba(212,175,55,0.3)}
        .btn-r{background:#C0392B;color:#fff}.btn-r:hover:not(:disabled){background:#E74C3C;box-shadow:0 4px 16px rgba(192,57,43,0.3)}
        .btn-p{background:transparent;color:#D4AF37;border:1px solid #D4AF3744}.btn-p:hover:not(:disabled){background:#D4AF3711;box-shadow:0 0 12px rgba(212,175,55,0.15)}
        .btn-d{background:transparent;color:#5C5C5C;border:1px solid #2a2a2a;font-size:9px;padding:6px 12px}.btn-d:hover:not(:disabled){background:#1a1a1a}
        .row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #1a1a1a}
        .tag{display:inline-block;padding:3px 8px;border-radius:3px;font-size:9px;font-weight:700;letter-spacing:.5px}
        .logrow{padding:4px 0;border-bottom:1px solid #141414}
        .trow{padding:6px 0;border-bottom:1px solid #1a1a1a;display:flex;justify-content:space-between;align-items:center}
        .dot{width:7px;height:7px;border-radius:50%;display:inline-block;flex-shrink:0}
        .section-label{font-family:'Oswald',sans-serif;font-size:11px;font-weight:600;letter-spacing:3px;text-transform:uppercase;color:#D4AF37;border-left:3px solid #D4AF37;padding-left:8px}
        .confirm-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.8);display:flex;align-items:center;justify-content:center;z-index:9999;animation:fadein 0.15s ease;padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)}
        .confirm-box{background:#111111;border:1px solid #D4AF3744;border-radius:8px;padding:24px 28px;max-width:400px;text-align:center}
        select option,select optgroup{background:#111111;color:#D4D4D4;font-family:'Space Mono',monospace;font-size:10px}
        select optgroup{color:#5C5C5C;font-weight:700}
        .live-banner{background:linear-gradient(90deg,#C0392B22,#ff990022);border:1px solid #C0392B44;border-radius:6px;padding:8px 16px;margin-bottom:14px;display:flex;align-items:center;justify-content:center;gap:10px}
        .app-root{min-height:100vh;min-height:100dvh}
        .brand-ticker-row{display:flex;align-items:center;margin-bottom:14px;position:relative;overflow:hidden;background:#111111;border:1px solid #1e1e1e;border-radius:6px;box-shadow:0 2px 20px rgba(0,0,0,0.5)}
        .brand-ticker-row::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#D4AF37,#C0392B,#D4AF37);z-index:20}
        .brand-ticker-row::after{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,#D4AF3744,transparent);z-index:20}
        .ironmike-brand{display:flex;align-items:center;gap:14px;padding:10px 0 10px 16px;position:relative;z-index:10;flex-shrink:0;background:#111111}
        .ironmike-brand::after{content:'';position:absolute;top:0;bottom:0;right:-48px;width:48px;background:linear-gradient(90deg,#111111 0%,transparent 100%);z-index:6;pointer-events:none}
        .ticker-wrapper{flex:1;min-width:0;overflow:hidden;position:relative;z-index:1;display:flex;align-items:center}
        .ticker-wrapper .ticker-tape{margin-bottom:0;border:none;border-radius:0;box-shadow:none;background:transparent;padding:0;flex:1;min-width:0}
        .ticker-wrapper .ticker-tape::before{display:none}
        .ticker-tape{margin-bottom:14px;overflow:hidden;position:relative;background:#111111;border:1px solid #1e1e1e;border-radius:4px;padding:10px 0;box-shadow:0 4px 24px rgba(0,0,0,0.5);z-index:1}
        .ticker-tape::before,.ticker-tape::after{content:'';position:absolute;top:0;bottom:0;width:48px;z-index:2;pointer-events:none}
        .ticker-tape::before{left:0;background:linear-gradient(90deg,#111111 0%,transparent 100%)}
        .ticker-tape::after{right:0;background:linear-gradient(270deg,#111111 0%,transparent 100%)}
        .ticker-tape:hover .ticker-track{animation-play-state:paused}
        .ticker-track{display:flex;align-items:center;gap:32px;will-change:transform;animation:tickerScroll 90s linear infinite;width:max-content;backface-visibility:hidden;-webkit-backface-visibility:hidden}
        @keyframes tickerScroll{0%{transform:translate3d(0,0,0)}100%{transform:translate3d(-50%,0,0)}}
        @keyframes lossToastIn{from{opacity:0;transform:translateX(-50%) translateY(16px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}
        /* TABLET 601–1024px: iPad, Android tablets */
        @media(max-width:1024px){
          .app-root{padding:16px 18px}
          .grid{grid-template-columns:1fr 1fr!important}
          .grid>.col:first-child{order:2}.grid>.col:nth-child(2){order:1;grid-column:1/-1}.grid>.col:last-child{order:3}
          .grid-bottom{grid-template-columns:1fr 1fr!important}
          .grid-bottom>.col:nth-child(2){grid-column:1/-1}
          .card{border-radius:12px;padding:18px}
          .btn{min-height:44px;padding:10px 18px}
          .chart-card{height:60vh!important;min-height:400px!important;max-height:600px!important}
          .control-panel{max-width:100%!important}
          .cp-row1{gap:3px!important;flex-wrap:wrap!important}
          .cp-row1 .btn{min-height:28px!important;padding:3px 10px!important}
        }
        /* PHONE ≤600px: iPhone, Android phones, Z Fold cover */
        @media(max-width:600px){
          .app-root{padding:12px 14px;margin:0;max-width:100%;border-radius:0}
          .grid{grid-template-columns:1fr!important}
          .grid>.col{order:unset!important;grid-column:unset!important}
          .grid-bottom{grid-template-columns:1fr!important}
          .grid-bottom>.col{grid-column:unset!important}
          .header-main{grid-template-columns:1fr!important;grid-template-rows:auto!important;gap:14px!important}
          .header-main>*{grid-column:1!important;grid-row:auto!important;justify-self:stretch!important}
          .header-price{justify-self:center!important}
          .control-panel{padding:8px 10px!important;max-width:100%!important}
          .cp-row1{gap:3px!important;justify-content:center!important;flex-wrap:wrap!important}
          .cp-row1 .btn{min-height:32px!important;padding:4px 10px!important;font-size:9px!important}
          .cp-row2{justify-content:center!important;gap:3px!important;flex-wrap:wrap!important}
          .status-bar{flex-wrap:wrap!important;gap:4px!important;padding:5px 10px!important}
          .pos-grid{grid-template-columns:repeat(2,1fr)!important}
          .card{border-radius:16px;padding:16px 18px}
          .btn{min-height:44px;padding:12px 20px;font-size:11px;border-radius:10px}
          .live-banner{border-radius:12px}
          .brand-ticker-row{flex-direction:column;overflow:visible}
          .ironmike-brand{padding:10px 14px 6px}
          .ironmike-brand::after{display:none}
          .ticker-wrapper{width:100%}
          .ticker-wrapper .ticker-tape{border-top:1px solid #1e1e1e}
          .ironmike-brand img{width:44px!important;height:44px!important}
          .coin-btn{min-height:44px;padding:12px 16px;-webkit-tap-highlight-color:transparent}
          .chart-card{height:55vh!important;min-height:320px!important;max-height:500px!important}
        }
        /* NARROW 320–400px: Z Fold cover (323px), Galaxy S25 (360px), legacy Android */
        @media(max-width:400px){
          .app-root{padding:10px 12px}
        }
      `}</style>

      {/* ══ LIVE MODE WARNING BANNER ══ */}
      {isLiveMode && (
        <div className="live-banner" role="alert">
          <span style={{ fontSize:"14px" }}>&#9888;</span>
          <span style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"14px", color:"#C0392B", letterSpacing:"3px" }}>LIVE TRADING MODE</span>
          <span style={{ fontSize:"10px", color:"#ff9900" }}>Real funds at risk — trades execute on-chain</span>
        </div>
      )}

      {/* ══ BRAND + TICKER — horizontal row, ticker fades behind brand ══ */}
      <div className="brand-ticker-row">
        <div className="ironmike-brand">
          <img src="/Bravo.svg" alt="DoYou.trade" style={{ width:"80px", height:"80px", flexShrink:0 }} />
          <div>
            <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"36px", color:"transparent", letterSpacing:"6px", lineHeight:"1", background:"linear-gradient(180deg,#D4AF37,#B8860B)", WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent" }}>DOYOU.TRADE</div>
            <div style={{ width:"100%", height:"1px", background:"linear-gradient(90deg,#D4AF37,#C0392B,transparent)", margin:"4px 0" }} />
            <TradeQuote />
          </div>
        </div>
        <div className="ticker-wrapper">
          <TickerTape
            marketTickers={marketTickers}
            activeCoins={activeCoins}
            coins={coins}
            price={price}
            selectedCoin={selectedCoin}
            positions={positions}
            onSelectCoin={(sym) => { setSelectedCoin(sym); setChartSymbol(sym); if (!activeCoins.includes(sym)) setActiveCoins(prev => [...prev, sym]); }}
          />
        </div>
      </div>

      {/* ══ HEADER ══ */}
      <div className="header-main" style={{ display:"grid", gridTemplateColumns:"1fr", gridTemplateRows:"auto auto", alignItems:"center", marginBottom:"16px", gap:"12px 16px" }}>
        {/* Price — always centered */}
        <div className="header-price" style={{ gridColumn:"1", gridRow:"1", justifySelf:"center", textAlign:"center", contain:"layout paint", minWidth:0 }}>
          {price > 0 ? (
            <>
              <div style={{ fontFamily:"'Oswald',sans-serif", fontSize:"11px", color:"#D4AF37", letterSpacing:"3px", fontWeight:"600", marginBottom:"2px" }}>{selectedCoin}</div>
              <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"36px", letterSpacing:"2px", color: priceUp?"#00E676":"#FF1744" }}>
                $<AnimatedNumber value={price} format={(v) => priceFormat(v)} duration={50} />
              </div>
              <div style={{ fontSize:"10px", color: change24h>=0?"#00E676":"#FF1744", marginTop:"2px" }}>
                {change24h>=0?"\u25B2":"\u25BC"} <AnimatedNumber value={Math.abs(change24h)} format={(v) => `${v.toFixed(2)}%`} duration={200} /> 24h
              </div>
              <div style={{ fontSize:"8px", color:"#5C5C5C", marginTop:"2px", letterSpacing:"1px" }}>{priceSource === "coinbase" ? "COINBASE · real-time" : "COINGECKO · may differ from chart"}</div>
            </>
          ) : (
            <FetchingPrice />
          )}
        </div>

        {/* ══ POWER PANEL — compact card-style control panel ══ */}
        <div className="header-stats control-panel" style={{
          gridColumn:"1 / -1", gridRow:"2", justifySelf:"center",
          width:"100%", maxWidth:"680px",
          background:"linear-gradient(180deg, #141414 0%, #0e0e0e 100%)",
          borderRadius:"10px",
          border:"1px solid #2a2a2a",
          boxShadow:"0 4px 24px rgba(0,0,0,0.5), 0 0 12px rgba(212,175,55,0.06), inset 0 1px 0 rgba(255,255,255,0.03)",
          padding:"10px 14px",
          display:"flex", flexDirection:"column", gap:"0",
          position:"relative", overflow:"hidden",
        }}>
          {/* Canvas texture overlay */}
          <div style={{ position:"absolute", inset:0, background:"repeating-linear-gradient(45deg, transparent, transparent 2px, rgba(212,175,55,0.008) 2px, rgba(212,175,55,0.008) 4px)", pointerEvents:"none", zIndex:1 }} />

          {/* Top edge glow — gold rope */}
          <div style={{ position:"absolute", top:0, left:"10%", right:"10%", height:"1px", background:"linear-gradient(90deg, transparent, #D4AF3766, #C0392B44, #D4AF3766, transparent)", zIndex:2 }} />

          {/* Bottom edge glow */}
          <div style={{ position:"absolute", bottom:0, left:"20%", right:"20%", height:"1px", background:"linear-gradient(90deg, transparent, #D4AF3722, transparent)", zIndex:2 }} />

          {/* ── Row 1: Stats readout ── */}
          <div className="cp-row1" style={{ display:"flex", alignItems:"center", justifyContent:"center", gap:"3px", position:"relative", zIndex:3, paddingBottom:"7px" }}>
            {[
              { label:"BAL", val:account.balance, fmt:(v)=>`$${v.toFixed(0)}`, color:"#D4D4D4", glow:"none" },
              { label:"P&L", val:account.total_pnl, fmt:(v)=>`${v>=0?"+":""}$${v.toFixed(0)}`, color:account.total_pnl>=0?"#00E676":"#FF1744", glow:account.total_pnl>=0?"0 0 8px #00E67644":"0 0 8px #FF174444" },
              { label:"24H", val:account.daily_pnl, fmt:(v)=>`${v>=0?"+":""}$${v.toFixed(0)}`, color:account.daily_pnl>=0?"#00E676":"#FF1744", glow:account.daily_pnl>=0?"0 0 8px #00E67644":"0 0 8px #FF174444" },
              { label:"WIN", val:winRate, fmt:(v)=>`${v}%`, color:winRate>=50?"#00E676":"#FF1744", glow:"none" },
            ].map(s => (
              <div key={s.label} style={{
                textAlign:"center", padding:"3px 10px", flex:"1 1 0",
                background:"rgba(0,0,0,0.4)", borderRadius:"4px",
                borderBottom:`1px solid ${s.color}22`,
              }}>
                <div style={{ fontSize:"7px", color:"#5C5C5C", letterSpacing:"1.2px", lineHeight:1, marginBottom:"2px", fontFamily:"'Space Mono',monospace" }}>{s.label}</div>
                <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"16px", color:s.color, lineHeight:1, textShadow:s.glow, whiteSpace:"nowrap" }}>
                  <AnimatedNumber value={s.val} format={s.fmt} duration={150} />
                </div>
              </div>
            ))}

            {/* Paper wallet tag */}
            <div style={{
              textAlign:"center", padding:"3px 8px", flex:"0 0 auto",
              background:"rgba(0,0,0,0.4)", borderRadius:"4px",
              border:"1px solid #2a2a2a",
            }}>
              <div style={{ fontSize:"7px", color:"#5C5C5C", letterSpacing:"1.2px", lineHeight:1, marginBottom:"2px", fontFamily:"'Space Mono',monospace" }}>PAPER</div>
              <div style={{ fontSize:"9px", color:"#5C5C5C", fontFamily:"'Space Mono',monospace", fontWeight:"600", lineHeight:1, whiteSpace:"nowrap" }}>
                ${startBal?.toLocaleString?.() || startBal}{"\u2192"}${targetBal?.toLocaleString?.() || targetBal}
              </div>
            </div>
          </div>

          {/* ── Separator line — gold rope ── */}
          <div style={{ height:"1px", background:"linear-gradient(90deg, transparent, #D4AF3744, #C0392B33, #D4AF3744, transparent)", marginBottom:"7px", position:"relative", zIndex:3 }} />

          {/* ── Row 2: Model + Strategy + Goal ── */}
          <div style={{ display:"flex", alignItems:"center", justifyContent:"center", gap:"10px", position:"relative", zIndex:3, paddingBottom:"8px", flexWrap:"wrap" }}>
            {/* Model selector */}
            <div style={{ display:"flex", alignItems:"center", gap:"4px" }}>
              <span style={{ fontSize:"7px", color:"#5C5C5C", letterSpacing:"1px", fontFamily:"'Space Mono',monospace" }}>MDL</span>
              <select
                value={claudeModel}
                onChange={e => handleModelChange(e.target.value)}
                disabled={thinking}
                style={{
                  fontFamily:"'Space Mono',monospace", fontSize:"9px", fontWeight:"700",
                  padding:"3px 20px 3px 6px", borderRadius:"4px",
                  backgroundColor: thinking ? "#1a1a1a" : "rgba(0,0,0,0.4)",
                  backgroundImage: thinking ? "none" : "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='4' viewBox='0 0 10 6'%3E%3Cpath fill='%23D4AF37' d='M0 0l5 6 5-6z'/%3E%3C/svg%3E\")",
                  backgroundRepeat:"no-repeat", backgroundPosition:"right 6px center",
                  color: thinking ? "#3a3a3a" : "#D4AF37",
                  border: thinking ? "1px solid #2a2a2a22" : "1px solid #D4AF3722",
                  cursor: thinking ? "not-allowed" : "pointer",
                  outline:"none", appearance:"none",
                  opacity: thinking ? 0.5 : 1,
                }}
                aria-label="Select Claude model"
              >
                <option value="claude-opus-4-6">Opus 4.6</option>
                <option value="claude-sonnet-4-6">Sonnet 4.6</option>
                <option value="claude-opus-4-5-20251101">Opus 4.5</option>
                <option value="claude-sonnet-4-5-20250929">Sonnet 4.5</option>
                <option value="claude-haiku-4-5-20251001">Haiku 4.5</option>
                <option value="claude-opus-4-1-20250805">Opus 4.1</option>
                <option value="claude-opus-4-20250514">Opus 4</option>
                <option value="claude-sonnet-4-20250514">Sonnet 4</option>
                <option value="claude-3-haiku-20240307">Haiku 3</option>
              </select>
              {thinking && <span style={{ fontSize:"6px", color:"#ff9900", letterSpacing:"0.3px" }}>LCK</span>}
            </div>

            <div style={{ width:"1px", height:"18px", background:"linear-gradient(180deg, transparent, #D4AF3733, transparent)", flexShrink:0 }} />

            {/* Strategy */}
            {connected && (
              <StrategyDropdown
                tradingPreset={tradingPreset}
                presets={presets}
                presetCategories={presetCategories}
                onPresetChange={handlePresetChange}
              />
            )}

            {connected && <div style={{ width:"1px", height:"18px", background:"linear-gradient(180deg, transparent, #D4AF3733, transparent)", flexShrink:0 }} />}

            {/* Goal picker */}
            <div className="cp-row2" style={{ display:"flex", gap:"4px", alignItems:"center" }}>
              <span style={{ fontSize:"8px", color:"#5C5C5C", letterSpacing:"1px", fontFamily:"'Space Mono',monospace" }}>TGT</span>
              {[100, 500, 1000, 2500, 4000].map(g => (
                <button
                  key={g}
                  onClick={() => setProfitGoal(profitGoal === g ? 0 : g)}
                  style={{
                    fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"3px 7px", borderRadius:"3px",
                    border: profitGoal === g ? "1px solid #D4AF37" : "1px solid #2a2a2a",
                    background: profitGoal === g ? "#D4AF3718" : "rgba(0,0,0,0.25)",
                    color: profitGoal === g ? "#D4AF37" : "#5C5C5C",
                    cursor:"pointer", fontWeight:"600", lineHeight:1,
                  }}
                >
                  ${g >= 1000 ? `${g/1000}k` : g}
                </button>
              ))}
              <input
                type="number"
                min="0"
                step="10"
                placeholder="Custom"
                value={profitGoal > 0 && ![100,500,1000,2500,4000].includes(profitGoal) ? profitGoal : ""}
                onChange={e => setProfitGoal(Math.max(0, +e.target.value || 0))}
                style={{
                  width:"56px", fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"3px 5px",
                  background:"rgba(0,0,0,0.25)", border:"1px solid #2a2a2a", borderRadius:"3px", color:"#D4D4D4",
                  outline:"none",
                }}
              />
              {profitGoal > 0 && ![100,500,1000,2500,4000].includes(profitGoal) && (
                <button
                  onClick={() => setProfitGoal(0)}
                  style={{ fontSize:"10px", color:"#5C5C5C", background:"none", border:"none", cursor:"pointer", padding:"2px 3px", lineHeight:1 }}
                  title="Clear goal"
                >{"\u2715"}</button>
              )}
            </div>
          </div>

          {/* ── Goal progress bar (only when goal set) ── */}
          {profitGoal > 0 && (
            <div style={{ display:"flex", alignItems:"center", gap:"8px", paddingBottom:"6px", position:"relative", zIndex:3 }}>
              <div style={{ flex:1, height:"8px", background:"#1a1a1a", borderRadius:"4px", overflow:"hidden", border:"1px solid #2a2a2a" }}>
                <div style={{
                  height:"100%", width:`${Math.min(100, Math.max(0, (account.total_pnl / profitGoal) * 100))}%`,
                  background: account.total_pnl >= profitGoal ? "linear-gradient(90deg,#00E676,#00C853)" : "linear-gradient(90deg,#D4AF37,#B8860B)",
                  borderRadius:"3px", transition:"width 0.4s ease",
                  boxShadow: account.total_pnl >= profitGoal ? "0 0 8px #00E67666" : "0 0 6px #D4AF3744",
                }} />
              </div>
              <span style={{ fontSize:"9px", color:"#5C5C5C", whiteSpace:"nowrap", fontFamily:"'Space Mono',monospace", fontWeight:"600" }}>
                $<AnimatedNumber value={Math.max(0, account.total_pnl)} format={(v)=>v.toFixed(0)} duration={200} />
                <span style={{ color:"#3a3a3a" }}>/</span>
                {profitGoal >= 1000 ? `$${profitGoal/1000}k` : `$${profitGoal}`}
              </span>
            </div>
          )}

          {/* ── Row 3: Action buttons — centered ── */}
          <div style={{ display:"flex", alignItems:"center", justifyContent:"center", gap:"6px", position:"relative", zIndex:3 }}>
            {!botOn
              ? <button className="btn btn-g" onClick={handleStart} aria-label="Start bot" style={{
                  padding:"4px 16px", minHeight:"28px", fontSize:"10px", borderRadius:"3px",
                  boxShadow:"0 0 14px rgba(212,175,55,0.3), inset 0 1px 0 rgba(255,255,255,0.1)",
                }}>🥊 ENTER THE RING</button>
              : <button className="btn btn-r" onClick={handleStop} aria-label="Stop bot" style={{
                  padding:"4px 16px", minHeight:"28px", fontSize:"10px", borderRadius:"3px",
                  boxShadow:"0 0 14px rgba(192,57,43,0.3), inset 0 1px 0 rgba(255,255,255,0.1)",
                }}>🏳 THROW IN THE TOWEL</button>}
            <button className="btn btn-p" onClick={handleAsk} disabled={thinking} aria-label="Ask Claude AI for analysis" style={{
              padding:"4px 14px", minHeight:"28px", fontSize:"10px", borderRadius:"3px",
              boxShadow: thinking ? "none" : "0 0 12px rgba(212,175,55,0.15)",
            }}>
              {thinking ? <span className="blink" style={{ fontSize:"9px" }}>ANALYZING</span> : "📣 CALL THE CORNER"}
            </button>
            <button className="btn btn-d" onClick={handleReset} aria-label="Reset paper trading balance" style={{
              padding:"4px 10px", minHeight:"28px", fontSize:"9px", borderRadius:"3px",
            }}>{"\u21BA"} RESET</button>
          </div>
        </div>
      </div>

      {/* ══ FULL-WIDTH CHART ══ */}
      <div className="card chart-card" style={{ height:"65vh", minHeight:"500px", maxHeight:"700px", display:"flex", flexDirection:"column", marginBottom:"16px", padding:"12px", position:"relative", zIndex:1, overflow:"hidden" }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"10px", padding:"0 4px", flexWrap:"wrap", gap:"10px" }}>
          <div style={{ display:"flex", alignItems:"center", gap:"10px", flexWrap:"wrap" }}>
            <span style={{ fontFamily:"'Oswald',sans-serif", fontSize:"14px", color:"#D4D4D4", fontWeight:"600", letterSpacing:"3px" }}>
              {chartSymbol.includes(":")
                ? (() => { const [, pair] = chartSymbol.split(":"); const base = (pair || "").replace(/USDT?$/i,""); return `${base} / ${(pair||"").includes("USDT") ? "USDT" : "USD"}`; })()
                : `${chartSymbol} / USD`}
            </span>
            <span style={{ fontSize:"9px", color:"#5C5C5C", letterSpacing:"1px" }}>TRADINGVIEW PRO</span>
            {/* Ticker search — search any symbol across exchanges */}
            <div ref={tickerSearchRef} style={{ position:"relative" }}>
              <div style={{ display:"flex", alignItems:"center", background:"#111111", border:"1px solid #1e1e1e", borderRadius:"6px", padding:"2px 8px", gap:"6px" }}>
                <span style={{ fontSize:"10px", color:"#5C5C5C" }}>🔍</span>
                <input
                  type="text"
                  placeholder="Search ticker..."
                  value={tickerSearch}
                  onChange={(e) => { setTickerSearch(e.target.value); setTickerSearchOpen(true); }}
                  onFocus={() => setTickerSearchOpen(true)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      const q = tickerSearch.trim().toUpperCase();
                      if (q.includes(":")) setChartSymbol(q);
                      else if (q) setChartSymbol(`BINANCE:${q}USDT`);
                      setTickerSearchOpen(false);
                      setTickerSearch("");
                    } else if (e.key === "Escape") { setTickerSearchOpen(false); setTickerSearch(""); }
                  }}
                  style={{ width:"140px", fontFamily:"'Space Mono',monospace", fontSize:"11px", background:"transparent", border:"none", color:"#D4D4D4", outline:"none" }}
                />
              </div>
              {tickerSearchOpen && (
                <div
                  style={{
                    position:"absolute", top:"100%", left:0, marginTop:"4px", minWidth:"300px", maxHeight:"320px", overflowY:"auto",
                    background:"#111111", border:"1px solid #1a1f2e", borderRadius:"6px", boxShadow:"0 8px 24px rgba(0,0,0,0.4)", zIndex:100,
                  }}
                >
                  {(() => {
                    const q = tickerSearch.trim().toUpperCase();
                    const matches = q
                      ? marketTickers.filter(t => (t.sym || "").toUpperCase().includes(q)).slice(0, 8)
                      : marketTickers.slice(0, 6);
                    const opts = [];
                    for (const t of matches) {
                      const sym = (t.sym || "").toUpperCase();
                      if (!sym) continue;
                      opts.push({ label: `${sym} — Binance`, symbol: `BINANCE:${sym}USDT`, exchange: "binance", sym });
                      opts.push({ label: `${sym} — Coinbase`, symbol: `COINBASE:${sym}USD`, exchange: "coinbase", sym });
                      opts.push({ label: `${sym} — Kraken`, symbol: `KRAKEN:${sym}USD`, exchange: "kraken", sym });
                    }
                    if (q && !matches.some(t => (t.sym || "").toUpperCase() === q)) {
                      opts.push({ label: `${q} — Binance`, symbol: `BINANCE:${q}USDT`, exchange: "binance", sym: q });
                      opts.push({ label: `${q} — Coinbase`, symbol: `COINBASE:${q}USD`, exchange: "coinbase", sym: q });
                      opts.push({ label: `${q} — Kraken`, symbol: `KRAKEN:${q}USD`, exchange: "kraken", sym: q });
                    }
                    if (opts.length === 0) {
                      for (const sym of ["BTC", "ETH", "SOL", "XRP", "DOGE"]) {
                        opts.push({ label: `${sym} — Binance`, symbol: `BINANCE:${sym}USDT`, exchange: "binance", sym });
                        opts.push({ label: `${sym} — Coinbase`, symbol: `COINBASE:${sym}USD`, exchange: "coinbase", sym });
                        opts.push({ label: `${sym} — Kraken`, symbol: `KRAKEN:${sym}USD`, exchange: "kraken", sym });
                      }
                    }
                    return opts;
                  })().map((opt) => {
                    const px = multiExchangePrices[opt.sym]?.[opt.exchange];
                    const priceStr = px != null && px > 0
                      ? (px < 0.0001 ? px.toFixed(8) : px < 0.01 ? px.toFixed(6) : px < 10 ? px.toFixed(4) : px < 1000 ? px.toFixed(2) : px.toLocaleString())
                      : null;
                    return (
                      <button
                        key={opt.symbol}
                        type="button"
                        onClick={() => { setChartSymbol(opt.symbol); setTickerSearch(""); setTickerSearchOpen(false); }}
                        style={{
                          display:"flex", width:"100%", justifyContent:"space-between", alignItems:"center", padding:"8px 12px",
                          fontFamily:"'Space Mono',monospace", fontSize:"10px", background:"transparent", border:"none",
                          color:"#D4D4D4", cursor:"pointer", whiteSpace:"nowrap", gap:"12px",
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = "#1e1e1e"; e.currentTarget.style.color = "#fff"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#D4D4D4"; }}
                      >
                        <span>{opt.label}</span>
                        <span style={{ color: priceStr ? "#D4AF37" : "#5C5C5C", fontSize:"11px", fontWeight: priceStr ? "700" : "400" }}>
                          {priceStr != null ? `$${priceStr}` : "—"}
                        </span>
                      </button>
                    );
                  })}
                  {tickerSearch && (
                    <div style={{ padding:"6px 12px", fontSize:"9px", color:"#5C5C5C", borderTop:"1px solid #1e1e1e" }}>
                      Available on Binance, Coinbase & Kraken — pick your exchange
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
          {positions.length > 0 && (
            <div style={{ display:"flex", gap:"10px", fontSize:"9px", alignItems:"center", flexWrap:"wrap" }}>
              {positions.filter(p => p.symbol === selectedCoin).map(pos => (
                <div key={pos.id} style={{ display:"flex", gap:"8px", padding:"2px 6px", borderRadius:"3px", background: pos.side==="buy"?"#00E67608":"#FF174408" }}>
                  <span style={{ color: pos.side==="buy"?"#00E676":"#FF1744", fontWeight:"700" }}>{pos.side?.toUpperCase()}</span>
                  <span style={{ color:"#D4AF37" }}>E $<AnimatedNumber value={pos.entry||0} format={(v)=>v.toLocaleString()} duration={150} /></span>
                  <span style={{ color:"#00E676" }}>TP $<AnimatedNumber value={pos.tp||0} format={(v)=>v.toLocaleString()} duration={150} /></span>
                  <span style={{ color:"#FF1744" }}>SL $<AnimatedNumber value={pos.sl||0} format={(v)=>v.toLocaleString()} duration={150} /></span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <TradingViewChart symbol={chartSymbol} />
        </div>
      </div>

      {/* ══ OPEN POSITIONS (full width) ══ */}
      {positions.length > 0 ? (
        <div style={{ marginBottom:"16px", position:"relative", zIndex:2 }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"8px" }}>
            <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
              <span style={{ fontSize:"9px", color:"#3a3a3a", letterSpacing:"2px" }}>
                OPEN POSITIONS ({positions.length}/{enableFutures ? maxPositions + maxFuturesPositions : maxPositions})
              </span>
              {unrealized !== 0 && (
                <span style={{ fontSize:"10px", fontWeight:"700", color: unrealized >= 0 ? "#00E676" : "#FF1744" }}>
                  Total: <AnimatedNumber value={unrealized} format={(v)=>`${v>=0?"+":""}$${v.toFixed(2)}`} duration={180} />
                </span>
              )}
            </div>
            {positions.length > 1 && (
              <button className="btn btn-d" onClick={() => handleClose()} style={{ padding:"4px 10px", fontSize:"9px", color:"#ff9900", borderColor:"#ff990033" }}>CLOSE ALL</button>
            )}
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:"10px" }}>
            {positions.map(pos => {
              const cp = coins[pos.symbol]?.price || price;
              const sz = pos.coin_size || pos.btc_size || 0;
              const posUnrealized = +((pos.side === "buy" ? cp - pos.entry : pos.entry - cp) * sz).toFixed(2);
              const range = Math.abs(pos.tp - pos.sl);
              let progress = 50;
              if (range > 0) {
                progress = pos.side === "buy"
                  ? ((cp - pos.sl) / range) * 100
                  : ((pos.sl - cp) / range) * 100;
                progress = Math.max(0, Math.min(100, progress));
              }
              return (
                <div key={pos.id || pos.symbol} className="card fadein" style={{ border:`1px solid ${pos.side==="buy"?"#00E67622":"#FF174422"}`, boxShadow:`0 0 20px ${pos.side==="buy"?"#00E67611":"#FF174411"}` }}>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"10px" }}>
                    <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
                      <span className="dot pulse" style={{ background:pos.side==="buy"?"#00E676":"#FF1744" }} />
                      <span style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"11px", color:pos.side==="buy"?"#00E676":"#FF1744", fontWeight:"700", letterSpacing:"2px" }}>
                        {pos.onchain ? "\u26D3 " : ""}{pos.side?.toUpperCase()} {pos.symbol || "BTC"}
                      </span>
                      {pos.onchain && <span className="tag" style={{ background:"#D4AF3718", color:"#D4AF37", fontSize:"9px" }}>ON-CHAIN</span>}
                      {pos.product_type === "futures" && <span className="tag" style={{ background:"#D4AF3718", color:"#D4AF37", fontSize:"9px" }}>FUTURES{pos.leverage ? ` ${pos.leverage}x` : ""}</span>}
                      {pos.exchange === "kraken" && <span className="tag" style={{ background:"#7b61ff18", color:"#7b61ff", fontSize:"9px" }}>KRAKEN</span>}
                      {pos.exchange === "coinbase" && <span className="tag" style={{ background:"#0052ff18", color:"#4d8ffa", fontSize:"9px" }}>COINBASE</span>}
                    </div>
                    <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
                      <span style={{ fontSize:"9px", color:"#3a3a3a" }}>since {pos.open_ts}</span>
                      <button className="btn btn-d" onClick={() => handleClose(pos)} style={{ padding:"4px 8px", fontSize:"9px", color:"#ff9900", borderColor:"#ff990033" }}>{"\u2715"}</button>
                    </div>
                  </div>
                  <div className="pos-grid" style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:"8px" }}>
                    {[
                      { label:"ENTRY",       num:pos.entry||0,       fmt:(v)=>`$${v.toLocaleString()}`,                          color:"#D4D4D4" },
                      { label:"TAKE PROFIT", num:pos.tp||0,          fmt:(v)=>`$${v.toLocaleString()}`,                          color:"#00E676" },
                      { label:"STOP LOSS",   num:pos.sl||0,          fmt:(v)=>`$${v.toLocaleString()}`,                          color:"#FF1744" },
                      { label:"SIZE",        num:pos.usd_size||0,    fmt:(v)=>`$${v.toFixed(2)}`,                                color:"#D4AF37" },
                      { label:"UNREALIZED",  num:posUnrealized,      fmt:(v)=>`${v>=0?"+":""}$${v.toFixed(2)}`,                  color:posUnrealized>=0?"#00E676":"#FF1744" },
                    ].map(s => (
                      <div key={s.label} style={{ background:"#0A0A0A", borderRadius:"5px", padding:"8px 6px", textAlign:"center" }}>
                        <div style={{ fontSize:"8px", color:"#3a3a3a", marginBottom:"3px" }}>{s.label}</div>
                        <div style={{ fontSize:"10px", fontWeight:"700", color:s.color }}>
                          <AnimatedNumber value={s.num} format={s.fmt} duration={180} />
                        </div>
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop:"8px" }}>
                    <div style={{ display:"flex", justifyContent:"space-between", fontSize:"8px", color:"#3a3a3a", marginBottom:"4px" }}>
                      <span>SL <AnimatedNumber value={(Math.abs(pos.entry-pos.sl)/Math.max(pos.entry,1))*100} format={(v)=>`${v.toFixed(2)}%`} duration={180} /></span>
                      <span>TP <AnimatedNumber value={(Math.abs(pos.tp-pos.entry)/Math.max(pos.entry,1))*100} format={(v)=>`${v.toFixed(2)}%`} duration={180} /></span>
                    </div>
                    <div style={{ height:"3px", background:"#1e1e1e", borderRadius:"2px", overflow:"hidden" }}>
                      <div style={{ height:"100%", width:`${progress}%`, background:posUnrealized>=0?"#00E676":"#FF1744", transition:"width 0.5s", borderRadius:"2px" }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="card" style={{ textAlign:"center", padding:"16px", color:"#3a3a3a", fontSize:"11px", letterSpacing:"1.5px", marginBottom:"16px", position:"relative", zIndex:2 }}>
          {"\u25CB"} NO OPEN POSITIONS — {botOn ? `Scanning (0/${enableFutures ? maxPositions + maxFuturesPositions : maxPositions} slots)...` : "Start bot to begin"}
        </div>
      )}

      {/* ══ 3-COL GRID (panels below chart) ══ */}
      <div className="grid-bottom">

        {/* ═══ LEFT ═══ */}
        <div className="col">

          {/* Claude Brain */}
          <div className="card" style={{ border:"1px solid #D4AF3722", boxShadow: thinking?"0 0 30px #D4AF3744":"0 0 12px #D4AF3710" }}>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:"14px" }}>
              <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
                <span className="dot" style={{ background: thinking?"#D4AF37":botOn?"#00E676":"#3a3a3a", animation:(thinking||botOn)?"pulse 1.5s infinite":"none", boxShadow:`0 0 8px ${thinking?"#D4AF37":botOn?"#00E676":"transparent"}` }} />
                <span className="section-label">THE GAMEPLAN</span>
              </div>
              {botOn && !thinking && <span style={{ fontSize:"10px", color:"#3a3a3a" }}>next: <AnimatedNumber value={countdown} format={(v)=>`${Math.round(v)}s`} duration={150} /></span>}
              {thinking         && <span className="blink" style={{ fontSize:"10px", color:"#D4AF37" }}>analyzing...</span>}
            </div>

            {/* ══ PENDING TRADE (approval required) ══ */}
            {pendingDecision && (
              <div className="card fadein" style={{ border:"2px solid #ff9900", background:"#ff990008", marginBottom:"14px" }}>
                <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"16px", color:"#ff9900", letterSpacing:"3px", marginBottom:"12px" }}>
                  PENDING TRADE — AWAITING YOUR CALL
                </div>
                <div style={{ display:"flex", alignItems:"center", gap:"10px", marginBottom:"10px" }}>
                  <span className="tag" style={{
                    background: pendingDecision.action === "buy" ? "#00E67620" : "#FF174420",
                    color: pendingDecision.action === "buy" ? "#00E676" : "#FF1744",
                    fontSize:"12px", padding:"4px 12px"
                  }}>
                    {pendingDecision.action === "buy" ? "\u25B2 BUY" : "\u25BC SELL"} {pendingDecision.symbol || ""}
                  </span>
                  {pendingExpiresAt > 0 && (
                    <span style={{ fontSize:"10px", color:"#ff9900" }}>
                      Expires in <AnimatedNumber value={pendingCountdown} format={(v)=>`${Math.round(v)}s`} duration={150} />
                    </span>
                  )}
                </div>
                {pendingDecision.reasoning && (
                  <div style={{ fontSize:"11px", color:"#999999", lineHeight:"1.6", marginBottom:"12px", fontStyle:"italic" }}>
                    &ldquo;{String(pendingDecision.reasoning).slice(0, 120)}&rdquo;
                  </div>
                )}
                {pendingDecision.order && (
                  <div style={{ background:"#0A0A0A", borderRadius:"5px", padding:"10px 12px", border:"1px solid #1e1e1e", marginBottom:"12px" }}>
                    {[
                      { label:"ENTRY", val:`$${(pendingDecision.order.entry_price||0).toLocaleString()}`, color:"#D4AF37" },
                      { label:"TP", val:`$${(pendingDecision.order.take_profit||0).toLocaleString()}`, color:"#00E676" },
                      { label:"SL", val:`$${(pendingDecision.order.stop_loss||0).toLocaleString()}`, color:"#FF1744" },
                      { label:"SIZE", val:`${pendingDecision.order.size_percent||0}%`, color:"#999999" },
                    ].map(r => (
                      <div key={r.label} className="row" style={{ fontSize:"11px" }}>
                        <span style={{ color:"#3a3a3a" }}>{r.label}</span>
                        <span style={{ color:r.color, fontWeight:"700" }}>{r.val}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div style={{ display:"flex", gap:"10px" }}>
                  <button className="btn btn-g" onClick={handleApprovePending} style={{ flex:1 }}>APPROVE</button>
                  <button className="btn btn-r" onClick={handleRejectPending} style={{ flex:1 }}>REJECT</button>
                </div>
              </div>
            )}

            {decision ? (
              <div className="fadein">
                <div style={{ display:"flex", alignItems:"center", gap:"10px", marginBottom:"12px" }}>
                  <span className="tag" style={{
                    background:{buy:"#00E67620",sell:"#FF174420",wait:"#ffffff10",close_all:"#ff990020"}[decision.action]||"#ffffff10",
                    color:{buy:"#00E676",sell:"#FF1744",wait:"#5C5C5C",close_all:"#ff9900"}[decision.action]||"#5C5C5C",
                    fontSize:"12px", padding:"4px 12px", fontFamily:"'Oswald',sans-serif", letterSpacing:"2px"
                  }}>
                    {{buy:"👊 BUY",sell:"💥 SELL",wait:"🛡 WAIT",close_all:"⚡ CLOSE ALL"}[decision.action]||decision.action?.toUpperCase()}
                    {decision.symbol && decision.action !== "wait" && <span style={{ marginLeft:"4px" }}>{decision.symbol}</span>}
                  </span>
                  {decision.confidence != null && (
                    <div style={{ flex:1 }}>
                      <div style={{ height:"6px", background:"#1a1a1a", borderRadius:"3px", overflow:"hidden", border:"1px solid #2a2a2a" }}>
                        <div style={{ height:"100%", width:`${decision.confidence*100}%`, background: decision.confidence>0.7?"linear-gradient(90deg,#D4AF37,#00E676)":decision.confidence>0.5?"linear-gradient(90deg,#D4AF37,#ff9900)":"linear-gradient(90deg,#C0392B,#FF1744)", transition:"width 0.6s", borderRadius:"2px" }} />
                      </div>
                      <div style={{ fontSize:"10px", color:"#5C5C5C", marginTop:"2px", fontFamily:"'Oswald',sans-serif", letterSpacing:"1px" }}><AnimatedNumber value={decision.confidence*100} format={(v)=>`${v.toFixed(0)}%`} duration={250} /> POWER</div>
                    </div>
                  )}
                </div>
                <div style={{ fontFamily:"'Playfair Display',serif", fontSize:"11px", color:"#D4D4D4", lineHeight:"1.8", borderLeft:"3px solid #D4AF3744", paddingLeft:"10px", marginBottom:"14px", fontStyle:"italic" }}>
                  &ldquo;{decision.reasoning}&rdquo;
                </div>
                {lastAiBlockReason && (
                  <div style={{ fontSize:"10px", color:"#ff9900", lineHeight:"1.5", background:"#ff990008", border:"1px solid #ff990033", borderRadius:"5px", padding:"8px 10px", marginBottom:"14px" }}>
                    ⚠ {lastAiBlockReason}
                  </div>
                )}
                {decision.order && (
                  <div style={{ background:"#0A0A0A", borderRadius:"5px", padding:"10px 12px", border:"1px solid #1e1e1e" }}>
                    {[
                      { label:"ENTRY",       val:`$${(decision.order.entry_price||0).toLocaleString()}`,  color:"#D4AF37" },
                      { label:"TAKE PROFIT", val:`$${(decision.order.take_profit||0).toLocaleString()}`,  color:"#00E676" },
                      { label:"STOP LOSS",   val:`$${(decision.order.stop_loss||0).toLocaleString()}`,    color:"#FF1744" },
                      { label:"SIZE",        val:`${decision.order.size_percent||0}% of balance`,         color:"#999999" },
                    ].map(r => (
                      <div key={r.label} className="row" style={{ fontSize:"11px" }}>
                        <span style={{ color:"#3a3a3a" }}>{r.label}</span>
                        <span style={{ color:r.color, fontWeight:"700" }}>{r.val}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div style={{ fontSize:"9px", color:"#2a2a2a", marginTop:"10px", textAlign:"right" }}>LAST CALL: {lastCall}</div>
              </div>
            ) : (
              <div style={{ textAlign:"center", padding:"20px 0", color:"#3a3a3a", fontSize:"11px", lineHeight:"2.2" }}>
                {botOn
                  ? <span className="blink" style={{ color:"#D4AF37" }}>First analysis in <AnimatedNumber value={countdown} format={(v)=>`${Math.round(v)}s`} duration={150} />...</span>
                  : <span>Press <span style={{ color:"#D4AF37" }}>🥊 ENTER THE RING</span> or <span style={{ color:"#D4AF37" }}>📣 CALL THE CORNER</span></span>
                }
              </div>
            )}
          </div>

          {/* Regime + Fear/Greed */}
          <div className="card">
            <div className="section-label" style={{ marginBottom:"10px" }}>MARKET REGIME</div>
            <div style={{ padding:"12px", borderRadius:"5px", background:`${condColor}11`, border:`1px solid ${condColor}22`, textAlign:"center", marginBottom:"12px" }}>
              <span style={{ fontFamily:"'Bebas Neue',sans-serif", color:condColor, fontSize:"16px", letterSpacing:"3px" }}>{condIcon} {condLabel}</span>
            </div>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
              <span style={{ fontSize:"10px", color:"#5C5C5C" }}>FEAR & GREED</span>
              <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
                <div style={{ width:"60px", height:"3px", background:"#1e1e1e", borderRadius:"2px", overflow:"hidden" }} role="progressbar" aria-valuenow={fearGreed.value} aria-valuemin={0} aria-valuemax={100} aria-label="Fear and Greed Index">
                  <div style={{ height:"100%", width:`${fearGreed.value}%`, background:`linear-gradient(to right, #FF1744, #ff9900, #00E676)`, borderRadius:"2px" }} />
                </div>
                <span style={{ fontSize:"10px", fontWeight:"700", color:fgColor }}><AnimatedNumber value={fearGreed.value} format={(v)=>`${Math.round(v)}`} duration={300} /> {fearGreed.label}</span>
              </div>
            </div>
          </div>

          {/* AgentKit Wallet */}
          {isLiveMode && (
            <div className="card" style={{ border: agentKit.agentkit_ready ? "1px solid #D4AF3722" : "1px solid #1e1e1e", boxShadow: agentKit.agentkit_ready ? "0 0 12px #D4AF3710" : "none" }}>
              <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:"12px" }}>
                <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
                  <span className="dot" style={{ background: agentKit.agentkit_ready ? "#D4AF37" : "#3a3a3a", boxShadow: agentKit.agentkit_ready ? "0 0 8px #D4AF37" : "none" }} />
                  <span style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"11px", color:"#D4AF37", fontWeight:"700", letterSpacing:"2px" }}>AGENTKIT WALLET</span>
                </div>
                <span style={{ fontSize:"9px", color: agentKit.agentkit_ready ? "#D4AF37" : "#FF1744" }}>
                  {agentKit.agentkit_ready ? "ON-CHAIN" : "OFFLINE"}
                </span>
              </div>
              {agentKit.agentkit_ready ? (
                <div>
                  <div className="row" style={{ fontSize:"11px" }}>
                    <span style={{ color:"#3a3a3a" }}>ADDRESS</span>
                    <span style={{ color:"#D4AF37", fontFamily:"monospace", fontSize:"10px" }}>
                      {agentKit.wallet_address ? `${agentKit.wallet_address.slice(0,6)}...${agentKit.wallet_address.slice(-4)}` : "--"}
                    </span>
                  </div>
                  <div className="row" style={{ fontSize:"11px" }}>
                    <span style={{ color:"#3a3a3a" }}>NETWORK</span>
                    <span style={{ color:"#D4D4D4", fontWeight:"700" }}>{agentKit.network || "--"}</span>
                  </div>
                  {agentKit.eth_balance && (
                    <div className="row" style={{ fontSize:"11px" }}>
                      <span style={{ color:"#3a3a3a" }}>ETH</span>
                      <span style={{ color:"#D4D4D4", fontWeight:"700" }}>{agentKit.eth_balance}</span>
                    </div>
                  )}
                  {agentKit.usdc_balance && (
                    <div className="row" style={{ fontSize:"11px" }}>
                      <span style={{ color:"#3a3a3a" }}>USDC</span>
                      <span style={{ color:"#00E676", fontWeight:"700" }}>{agentKit.usdc_balance}</span>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ fontSize:"10px", color:"#3a3a3a", textAlign:"center", padding:"6px 0" }}>
                  {agentKit.error ? `${agentKit.error}` : "Set CDP keys in .env for on-chain trading"}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ═══ CENTER ═══ */}
        <div className="col">

          {/* Indicators */}
          <div className="card">
            <div className="section-label" style={{ marginBottom:"10px" }}>LIVE INDICATORS</div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"0 20px" }}>
              {[
                { label:"EMA 9",    num: indic.ema9,           prefix:"$", fmt:(v)=>`$${v.toLocaleString()}`,  fallback:"warming\u2026", color:"#00E676" },
                { label:"EMA 21",   num: indic.ema21,          prefix:"$", fmt:(v)=>`$${v.toLocaleString()}`,  fallback:"warming\u2026", color:"#D4AF37" },
                { label:"RSI 14",   num: indic.ema9 ? indic.rsi : null, fmt:(v)=>`${v.toFixed(1)}${v>70?" OB":v<30?" OS":""}`, fallback:"-", color: indic.rsi>70?"#FF1744":indic.rsi<30?"#00E676":"#D4D4D4" },
                { label:"ATR 14",   num: indic.ema9 ? indic.atr : null, fmt:(v)=>`$${v.toFixed(2)}`, fallback:"-", color: indic.atr>500?"#ff9900":"#D4D4D4" },
                { label:"BB UPPER", num: indic.bb_upper,       fmt:(v)=>`$${v.toLocaleString()}`,  fallback:"-", color:"#FF1744" },
                { label:"BB MID",   num: indic.bb_middle,      fmt:(v)=>`$${v.toLocaleString()}`,  fallback:"-", color:"#64748b" },
                { label:"BB LOWER", num: indic.bb_lower,       fmt:(v)=>`$${v.toLocaleString()}`,  fallback:"-", color:"#00E676" },
                { label:"BB WIDTH", num: indic.bb_width || null, fmt:(v)=>`${v.toFixed(4)}%`,      fallback:"-", color:"#ff9900" },
                { label:"VWAP",     num: indic.vwap,           fmt:(v)=>`$${v.toLocaleString()}`,  fallback:"-", color:"#D4AF37" },
                { label:"MACD",     num: indic.macd,           fmt:(v)=>`${v.toFixed(2)}`,         fallback:"-", color: (indic.macd||0) >= 0 ? "#00E676" : "#FF1744" },
                { label:"MACD SIG", num: indic.macd_signal,    fmt:(v)=>`${v.toFixed(2)}`,         fallback:"-", color: "#ff9900" },
                { label:"MACD HIST",num: indic.macd_histogram, fmt:(v)=>`${v.toFixed(2)}`,         fallback:"-", color: (indic.macd_histogram||0) >= 0 ? "#00E676" : "#FF1744" },
                { label:"MOMENTUM", num: indic.momentum,       fmt:(v)=>`${v.toFixed(2)}%`,        fallback:"-", color: (indic.momentum||0) >= 0 ? "#00E676" : "#FF1744" },
              ].map(ind => (
                <div key={ind.label} className="row" style={{ fontSize:"11px" }}>
                  <span style={{ color:"#3a3a3a" }}>{ind.label}</span>
                  <span style={{ color:ind.color, fontWeight:"700" }}>
                    {ind.num != null ? <AnimatedNumber value={ind.num} format={ind.fmt} duration={180} /> : ind.fallback}
                  </span>
                </div>
              ))}
            </div>
            <div style={{ marginTop:"10px", fontSize:"9px", color:"#2a2a2a", textAlign:"center" }}>
              {history.length < 9 ? `Building: ${history.length}/9 candles` : `${history.length} candles loaded`}
            </div>
          </div>

          {/* Risk Monitor */}
          <div className="card">
            <div className="section-label" style={{ marginBottom:"10px" }}>RISK MONITOR</div>
            {[
              { label:"DAILY LOSS",  num:dailyLossPct, fmt:(v)=>`${v.toFixed(1)}%`, limit:"5% limit",      pct:dailyLossPct/5*100,                                 color:"#FF1744" },
              { label:"GROWTH",      num:(account.balance/startBal-1)*100, fmt:(v)=>`${v.toFixed(1)}%`, limit:`from $${startBal}`, pct:Math.min(100,Math.max(0,(account.balance/startBal-1)*100)), color:"#00E676" },
            ].map(r => (
              <div key={r.label} style={{ marginBottom:"12px" }}>
                <div style={{ display:"flex", justifyContent:"space-between", fontSize:"10px", marginBottom:"5px" }}>
                  <span style={{ color:"#5C5C5C" }}>{r.label}</span>
                  <span style={{ color:r.pct>80?"#FF1744":r.color, fontWeight:"700" }}><AnimatedNumber value={r.num} format={r.fmt} duration={200} /> <span style={{ color:"#3a3a3a" }}>{r.limit}</span></span>
                </div>
                <div style={{ height:"3px", background:"#1e1e1e", borderRadius:"2px", overflow:"hidden" }}>
                  <div style={{ height:"100%", width:`${Math.max(0,Math.min(100,r.pct))}%`, background:r.pct>80?"#FF1744":r.color, transition:"width 0.5s", borderRadius:"2px" }} />
                </div>
              </div>
            ))}
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"8px", marginTop:"6px" }}>
              {[
                { label:"TRADES",   num:trades.length,  fmt:(v)=>`${Math.round(v)}`,                                    color:"#D4D4D4" },
                { label:"WIN RATE", num:winRate,         fmt:(v)=>`${Math.round(v)}%`,                                   color:winRate>=50?"#00E676":"#FF1744" },
                { label:"BEST",     num:trades.length?Math.max(...trades.map(t=>t.pnl)):null, fmt:(v)=>`+$${v.toFixed(2)}`, color:"#00E676" },
                { label:"WORST",    num:trades.length?Math.min(...trades.map(t=>t.pnl)):null, fmt:(v)=>`$${v.toFixed(2)}`,  color:"#FF1744" },
              ].map(s => (
                <div key={s.label} style={{ background:"#0A0A0A", padding:"8px", borderRadius:"5px" }}>
                  <div style={{ fontSize:"9px", color:"#3a3a3a", marginBottom:"2px" }}>{s.label}</div>
                  <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"13px", fontWeight:"700", color:s.color }}>
                    {s.num != null ? <AnimatedNumber value={s.num} format={s.fmt} duration={200} /> : "--"}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ═══ RIGHT ═══ */}
        <div className="col">

          {/* Trade History (recent) */}
          <div className="card" style={{ flex:"1 1 0", display:"flex", flexDirection:"column", overflow:"hidden", minHeight:"180px" }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"10px" }}>
              <span className="section-label">THE RECORD</span>
              <div style={{ display:"flex", gap:"6px" }}>
                {trades.length > 0 && (
                  <button className="btn btn-d" onClick={() => exportTrades()} style={{ padding:"2px 6px", fontSize:"9px" }} aria-label="Export trade history as CSV">{"\u21E9"} CSV</button>
                )}
                {connected && (
                  <button className="btn btn-d" onClick={() => { setShowHistory(true); fetchHistory(0); }} style={{ padding:"2px 6px", fontSize:"9px", color:"#D4AF37", borderColor:"#D4AF3733" }} aria-label="View full trade history">ALL HISTORY</button>
                )}
              </div>
            </div>
            <div ref={tradesContainerRef} style={{ flex:"1 1 0", overflowY:"auto" }}>
              {trades.length === 0
                ? <div style={{ textAlign:"center", padding:"20px", color:"#2a2a2a", fontSize:"11px" }}>No trades yet — start the bot</div>
                : trades.map(tr => (
                  <div key={tr.id} className="trow fadein" style={{ fontSize:"11px", cursor:"pointer" }}
                    onClick={() => openTradeDetail(tr)} title="Click to view trade chart">
                    <div>
                      <span className="tag" style={{ background:tr.side==="buy"?"#00E67618":"#FF174418", color:tr.side==="buy"?"#00E676":"#FF1744", marginRight:"5px" }}>
                        {tr.side==="buy"?"\u25B2":"\u25BC"} {tr.side?.toUpperCase()}
                      </span>
                      <span style={{ color:"#D4AF37", fontSize:"9px", fontWeight:"700", marginRight:"4px" }}>{tr.symbol || "BTC"}</span>
                      {tradeTypeBadge(tr)}
                      <span style={{ color:"#2a2a2a", fontSize:"9px", marginLeft:"4px" }}>{tr.ts}</span>
                    </div>
                    <div style={{ textAlign:"right" }}>
                      <div style={{ fontWeight:"700", color:tr.win?"#00E676":"#FF1744" }}>{tr.pnl>=0?"+":""}${(+tr.pnl).toFixed(2)}</div>
                      <div style={{ fontSize:"9px", color:"#3a3a3a", display:"flex", alignItems:"center", justifyContent:"flex-end", gap:"3px" }}>{tr.reason} <span style={{ color:"#D4AF3766" }}>📸</span></div>
                    </div>
                  </div>
                ))
              }
            </div>
          </div>

          {/* Activity Log */}
          <div className="card" style={{ flex:"1 1 0", display:"flex", flexDirection:"column", overflow:"hidden", minHeight:"180px" }}>
            <div style={{ display:"flex", alignItems:"center", gap:"8px", marginBottom:"10px" }}>
              <span className="section-label">RINGSIDE LOG</span>
              {(botOn||connected) && <span className="blink" style={{ fontSize:"9px", color:"#00E676" }}>LIVE</span>}
            </div>
            <div ref={logsContainerRef} style={{ flex:"1 1 0", overflowY:"auto" }} role="log" aria-label="Activity log">
              {logs.map((e) => (
                <div key={e.id} className="logrow" style={{ fontSize:"10px", lineHeight:"1.7" }}>
                  <span style={{ color:"#2a2a2a", marginRight:"5px" }}>{e.ts}</span>
                  <span style={{ color:{success:"#00E676",error:"#FF1744",warning:"#ff9900",claude:"#D4AF37",sell:"#ff6688",dim:"#3a3a3a"}[e.type]||"#5C5C5C" }}>
                    <span aria-hidden="true">{({success:"+",error:"\u2715",warning:"!",claude:"\u25C6",sell:"\u25BC",dim:"\u00B7"})[e.type]||"\u203A"} </span>
                    {e.msg}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ══ ANALYTICS ROW (equity + analytics + memory) ══ */}
      <AnalyticsSection connected={connected} log={log} lossToast={lossToast}
        cbLive={cbLive} krakenEnabled={krakenEnabled} hasClaude={hasClaude}
        isLiveMode={isLiveMode} agentKit={agentKit} paperMode={paperMode}
        directionBias={directionBias} requireTradeApproval={requireTradeApproval}
        price={price} priceAge={priceAge} wsRetrying={wsRetrying} />

      {/* ══ FULL TRADE HISTORY OVERLAY ══ */}
      {showHistory && (
        <div style={{ position:"fixed", inset:0, background:"rgba(6,6,15,0.95)", zIndex:9998, display:"flex", flexDirection:"column", animation:"fadein 0.2s ease" }}>
          {/* Header */}
          <div style={{ padding:"20px 24px 0", flexShrink:0 }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"16px" }}>
              <div style={{ display:"flex", alignItems:"center", gap:"12px" }}>
                <span style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"20px", color:"#D4AF37", letterSpacing:"4px" }}>THE RECORD</span>
                <span style={{ fontSize:"10px", color:"#5C5C5C" }}>{historyTotal} total trades in database</span>
              </div>
              <div style={{ display:"flex", gap:"8px" }}>
                {historyTrades.length > 0 && (
                  <button className="btn btn-d" onClick={() => exportTrades(historyTrades)} style={{ fontSize:"9px" }}>{"\u21E9"} EXPORT CSV</button>
                )}
                <button className="btn btn-d" onClick={() => setShowHistory(false)} style={{ fontSize:"12px", color:"#FF1744", borderColor:"#FF174433", padding:"6px 14px" }}>{"\u2715"} CLOSE</button>
              </div>
            </div>

            {/* Filters */}
            <div style={{ display:"flex", gap:"10px", flexWrap:"wrap", alignItems:"flex-end", marginBottom:"14px" }}>
              <div>
                <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>FROM</div>
                <input type="date" value={historyFilters.date_from} onChange={e => applyHistoryFilter("date_from", e.target.value)}
                  style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none" }} />
              </div>
              <div>
                <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>TO</div>
                <input type="date" value={historyFilters.date_to} onChange={e => applyHistoryFilter("date_to", e.target.value)}
                  style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none" }} />
              </div>
              <div>
                <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>COIN</div>
                <select value={historyFilters.symbol} onChange={e => applyHistoryFilter("symbol", e.target.value)}
                  style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none", appearance:"none", minWidth:"80px" }}>
                  <option value="">ALL</option>
                  {activeCoins.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>SIDE</div>
                <select value={historyFilters.side} onChange={e => applyHistoryFilter("side", e.target.value)}
                  style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none", appearance:"none", minWidth:"80px" }}>
                  <option value="">ALL</option>
                  <option value="buy">BUY</option>
                  <option value="sell">SELL</option>
                </select>
              </div>
              <div>
                <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>RESULT</div>
                <select value={historyFilters.result} onChange={e => applyHistoryFilter("result", e.target.value)}
                  style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none", appearance:"none", minWidth:"80px" }}>
                  <option value="">ALL</option>
                  <option value="win">WINS</option>
                  <option value="loss">LOSSES</option>
                </select>
              </div>
              <div>
                <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>TYPE</div>
                <select value={historyFilters.product_type} onChange={e => applyHistoryFilter("product_type", e.target.value)}
                  style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none", appearance:"none", minWidth:"90px" }}>
                  <option value="">ALL</option>
                  <option value="spot">SPOT</option>
                  <option value="futures">FUTURES</option>
                  <option value="onchain">ON-CHAIN</option>
                </select>
              </div>
              {(historyFilters.date_from || historyFilters.date_to || historyFilters.symbol || historyFilters.side || historyFilters.result || historyFilters.product_type) && (
                <button className="btn btn-d" onClick={clearHistoryFilters} style={{ fontSize:"9px", color:"#ff9900", borderColor:"#ff990033", padding:"6px 12px", alignSelf:"flex-end" }}>CLEAR FILTERS</button>
              )}
              <button className="btn btn-d" onClick={() => fetchHistory(historyPage)} style={{ fontSize:"9px", color:"#D4AF37", borderColor:"#D4AF3733", padding:"6px 12px", alignSelf:"flex-end" }}>{"\u21BB"} REFRESH</button>
            </div>

            {/* Summary stats */}
            <div style={{ display:"flex", gap:"16px", marginBottom:"14px", flexWrap:"wrap" }}>
              {[
                { label:"SHOWING", val:`${historyTrades.length} of ${historyTotal}`, color:"#D4D4D4" },
                { label:"WINS", val:historyStats.wins, color:"#00E676" },
                { label:"LOSSES", val:historyStats.losses, color:"#FF1744" },
                { label:"WIN RATE", val:`${historyStats.win_rate}%`, color:historyStats.win_rate >= 50 ? "#00E676" : "#FF1744" },
                { label:"NET P&L", val:`${historyStats.total_pnl >= 0 ? "+" : ""}$${historyStats.total_pnl.toFixed(2)}`, color:historyStats.total_pnl >= 0 ? "#00E676" : "#FF1744" },
              ].map(s => (
                <div key={s.label} style={{ background:"#111111", border:"1px solid #1e1e1e", borderRadius:"5px", padding:"8px 14px" }}>
                  <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px" }}>{s.label}</div>
                  <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"14px", fontWeight:"700", color:s.color }}>{s.val}</div>
                </div>
              ))}
            </div>

            {/* Table header */}
            <div style={{ display:"grid", gridTemplateColumns:"140px 55px 55px 55px 90px 90px 80px 70px 1fr", gap:"8px", padding:"8px 12px", background:"#111111", borderRadius:"5px 5px 0 0", border:"1px solid #1e1e1e", borderBottom:"none" }}>
              {["DATE / TIME", "COIN", "SIDE", "TYPE", "ENTRY", "EXIT", "P&L", "RESULT", "REASON"].map(h => (
                <span key={h} style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1.5px", fontWeight:"700" }}>{h}</span>
              ))}
            </div>
          </div>

          {/* Trade rows */}
          <div style={{ flex:1, overflowY:"auto", padding:"0 24px", minHeight:0 }}>
            <div style={{ border:"1px solid #1e1e1e", borderTop:"none", borderRadius:"0 0 5px 5px", background:"#111111" }}>
              {historyLoading ? (
                <div style={{ padding:"24px", display:"flex", flexDirection:"column", gap:"8px" }}>
                  {[1,2,3,4,5,6,7,8].map(i => <Skeleton key={i} width="100%" height={28} />)}
                </div>
              ) : historyTrades.length === 0 ? (
                <div style={{ textAlign:"center", padding:"40px", color:"#2a2a2a", fontSize:"11px" }}>
                  No trades found{(historyFilters.date_from || historyFilters.date_to || historyFilters.symbol || historyFilters.side || historyFilters.result) ? " matching filters" : ""}
                </div>
              ) : (
                historyTrades.map(tr => (
                  <div key={tr.id} style={{ display:"grid", gridTemplateColumns:"140px 55px 55px 55px 90px 90px 80px 70px 1fr", gap:"8px", padding:"8px 12px", borderBottom:"1px solid #1a1a1a", fontSize:"11px", transition:"background 0.1s", cursor:"pointer" }}
                    onMouseEnter={e => e.currentTarget.style.background="#1a1a1a"}
                    onMouseLeave={e => e.currentTarget.style.background="transparent"}
                    onClick={() => openTradeDetail(tr)}
                    title="Click to view trade chart screenshots">
                    <span style={{ color:"#5C5C5C", fontSize:"10px" }}>
                      {tr.created_at || tr.ts}
                    </span>
                    <span style={{ color:"#D4AF37", fontWeight:"700" }}>{tr.symbol || "BTC"}</span>
                    <span>
                      <span className="tag" style={{ background:tr.side==="buy"?"#00E67618":"#FF174418", color:tr.side==="buy"?"#00E676":"#FF1744", padding:"2px 6px" }}>
                        {tr.side==="buy"?"\u25B2":"\u25BC"} {tr.side?.toUpperCase()}
                      </span>
                    </span>
                    <span>{tradeTypeBadge(tr)}</span>
                    <span style={{ color:"#D4D4D4" }}>${(+tr.entry).toLocaleString()}</span>
                    <span style={{ color:"#D4D4D4" }}>${(+tr.exit).toLocaleString()}</span>
                    <span style={{ fontWeight:"700", color:tr.win?"#00E676":"#FF1744" }}>{tr.pnl>=0?"+":""}${(+tr.pnl).toFixed(2)}</span>
                    <span>
                      <span className="tag" style={{ background:tr.win?"#00E67618":"#FF174418", color:tr.win?"#00E676":"#FF1744", padding:"2px 6px" }}>
                        {tr.win ? "WIN" : "LOSS"}
                      </span>
                    </span>
                    <span style={{ color:"#3a3a3a", fontSize:"10px", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", display:"flex", alignItems:"center", gap:"4px" }}>
                      {tr.reason}
                      <span style={{ color:"#D4AF3766", fontSize:"9px", flexShrink:0 }}>📸</span>
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Pagination */}
          {historyTotal > historyLimit && (
            <div style={{ padding:"12px 24px", flexShrink:0, display:"flex", justifyContent:"center", alignItems:"center", gap:"12px" }}>
              <button className="btn btn-d" disabled={historyPage === 0} onClick={() => fetchHistory(historyPage - 1)}
                style={{ padding:"6px 14px", fontSize:"10px" }}>{"\u25C0"} PREV</button>
              <span style={{ fontSize:"10px", color:"#5C5C5C" }}>
                Page {historyPage + 1} of {Math.ceil(historyTotal / historyLimit)}
              </span>
              <button className="btn btn-d" disabled={(historyPage + 1) * historyLimit >= historyTotal} onClick={() => fetchHistory(historyPage + 1)}
                style={{ padding:"6px 14px", fontSize:"10px" }}>NEXT {"\u25B6"}</button>
            </div>
          )}
        </div>
      )}

      {/* ══ TRADE DETAIL MODAL (Chart Screenshots) ══ */}
      {tradeDetail && (
        <div style={{ position:"fixed", inset:0, background:"rgba(6,6,15,0.97)", zIndex:9999, display:"flex", flexDirection:"column", animation:"fadein 0.2s ease", overflow:"auto" }}
          onClick={closeTradeDetail}>
          <div style={{ maxWidth:"1100px", width:"100%", margin:"20px auto", padding:"0 20px" }} onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"20px" }}>
              <div style={{ display:"flex", alignItems:"center", gap:"12px" }}>
                <span style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"22px", color:"#D4AF37", letterSpacing:"4px" }}>TRADE REVIEW</span>
                <span className="tag" style={{ background:tradeDetail.trade?.win?"#00E67618":"#FF174418", color:tradeDetail.trade?.win?"#00E676":"#FF1744", fontSize:"11px", padding:"3px 10px" }}>
                  {tradeDetail.trade?.win ? "WIN" : "LOSS"}
                </span>
              </div>
              <button className="btn btn-d" onClick={closeTradeDetail} style={{ fontSize:"12px", color:"#FF1744", borderColor:"#FF174433", padding:"6px 14px" }}>{"\u2715"} CLOSE</button>
            </div>

            {/* Trade Summary Bar */}
            <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(120px, 1fr))", gap:"10px", marginBottom:"20px" }}>
              {[
                { label:"SYMBOL", val:tradeDetail.trade?.symbol || "BTC", color:"#D4AF37" },
                { label:"SIDE", val:tradeDetail.trade?.side?.toUpperCase(), color:tradeDetail.trade?.side==="buy"?"#00E676":"#FF1744" },
                { label:"ENTRY", val:`$${(+(tradeDetail.trade?.entry||0)).toLocaleString()}`, color:"#D4D4D4" },
                { label:"EXIT", val:`$${(+(tradeDetail.trade?.exit||tradeDetail.trade?.exit_price||0)).toLocaleString()}`, color:"#D4D4D4" },
                { label:"P&L", val:`${(tradeDetail.trade?.pnl||0)>=0?"+":""}$${(+(tradeDetail.trade?.pnl||0)).toFixed(2)}`, color:(tradeDetail.trade?.pnl||0)>=0?"#00E676":"#FF1744" },
                { label:"SIZE", val:`$${(+(tradeDetail.trade?.usd_size||0)).toFixed(2)}`, color:"#999" },
                { label:"DATE", val:tradeDetail.trade?.created_at || tradeDetail.trade?.ts || "", color:"#5C5C5C" },
              ].map(s => (
                <div key={s.label} style={{ background:"#111111", border:"1px solid #1e1e1e", borderRadius:"6px", padding:"10px 12px", textAlign:"center" }}>
                  <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>{s.label}</div>
                  <div style={{ fontSize:"13px", fontWeight:"700", color:s.color }}>{s.val}</div>
                </div>
              ))}
            </div>

            {/* Reason */}
            {tradeDetail.trade?.reason && (
              <div style={{ background:"#111111", border:"1px solid #1e1e1e", borderRadius:"6px", padding:"12px 16px", marginBottom:"20px" }}>
                <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"4px" }}>CLOSE REASON</div>
                <div style={{ fontSize:"12px", color:"#D4D4D4" }}>{tradeDetail.trade.reason}</div>
              </div>
            )}

            {/* Phase Tabs */}
            <div style={{ display:"flex", gap:"8px", marginBottom:"16px" }}>
              {["entry", "exit"].map(phase => (
                <button key={phase} className="btn" onClick={() => setTradeDetailTab(phase)}
                  style={{
                    padding:"8px 20px", fontSize:"11px", letterSpacing:"2px", fontWeight:"700",
                    background: tradeDetailTab === phase ? "#D4AF3722" : "transparent",
                    color: tradeDetailTab === phase ? "#D4AF37" : "#5C5C5C",
                    border: `1px solid ${tradeDetailTab === phase ? "#D4AF3744" : "#2a2a2a"}`,
                  }}>
                  {phase.toUpperCase()} CHART
                </button>
              ))}
            </div>

            {/* Chart Screenshots */}
            {tradeDetailLoading ? (
              <div style={{ display:"flex", flexDirection:"column", gap:"8px", padding:"40px 0" }}>
                {[1,2,3].map(i => <Skeleton key={i} width="100%" height={200} />)}
              </div>
            ) : (
              <div>
                {(() => {
                  const phase = tradeDetailTab;
                  const ss = tradeDetail.screenshots?.[phase];
                  const meta = ss?.meta;
                  const timeframes = ss?.timeframes || [];
                  const backendBase = BACKEND_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;
                  const secretParam = API_SECRET ? `?secret=${API_SECRET}` : "";

                  if (!ss || timeframes.length === 0) {
                    return (
                      <div style={{ textAlign:"center", padding:"60px 20px", color:"#2a2a2a" }}>
                        <div style={{ fontSize:"48px", marginBottom:"12px", opacity:0.3 }}>📸</div>
                        <div style={{ fontSize:"12px", color:"#3a3a3a", marginBottom:"6px" }}>No chart screenshots available for {phase}</div>
                        <div style={{ fontSize:"10px", color:"#2a2a2a" }}>
                          Screenshots are captured automatically when trades open and close.
                          {!tradeDetail.screenshots?.entry && !tradeDetail.screenshots?.exit && (
                            <span> This trade was recorded before screenshot capture was enabled.</span>
                          )}
                        </div>
                      </div>
                    );
                  }

                  return (
                    <div>
                      {/* Strategy/Context annotation above charts */}
                      {meta && (
                        <div style={{ background:"#0d0d0d", border:"1px solid #1e1e1e", borderRadius:"6px", padding:"14px 16px", marginBottom:"16px" }}>
                          <div style={{ display:"flex", flexWrap:"wrap", gap:"16px", fontSize:"10px" }}>
                            {meta.side && (
                              <div><span style={{ color:"#3a3a3a" }}>SIDE: </span><span style={{ color:meta.side==="buy"?"#00E676":"#FF1744", fontWeight:"700" }}>{meta.side.toUpperCase()}</span></div>
                            )}
                            {meta.confidence != null && (
                              <div><span style={{ color:"#3a3a3a" }}>CONFIDENCE: </span><span style={{ color:"#D4AF37", fontWeight:"700" }}>{(meta.confidence * 100).toFixed(0)}%</span></div>
                            )}
                            {meta.market_condition && (
                              <div><span style={{ color:"#3a3a3a" }}>REGIME: </span><span style={{ color:"#D4D4D4" }}>{meta.market_condition}</span></div>
                            )}
                            {meta.strategy && (
                              <div><span style={{ color:"#3a3a3a" }}>STRATEGY: </span><span style={{ color:"#D4D4D4" }}>{meta.strategy}</span></div>
                            )}
                            {meta.entry != null && (
                              <div><span style={{ color:"#3a3a3a" }}>ENTRY: </span><span style={{ color:"#D4D4D4" }}>${(+meta.entry).toLocaleString()}</span></div>
                            )}
                            {meta.tp != null && (
                              <div><span style={{ color:"#3a3a3a" }}>TP: </span><span style={{ color:"#00E676" }}>${(+meta.tp).toLocaleString()}</span></div>
                            )}
                            {meta.sl != null && (
                              <div><span style={{ color:"#3a3a3a" }}>SL: </span><span style={{ color:"#FF1744" }}>${(+meta.sl).toLocaleString()}</span></div>
                            )}
                            {meta.pnl != null && (
                              <div><span style={{ color:"#3a3a3a" }}>P&L: </span><span style={{ color:meta.pnl>=0?"#00E676":"#FF1744", fontWeight:"700" }}>{meta.pnl>=0?"+":""}${(+meta.pnl).toFixed(2)}</span></div>
                            )}
                            {meta.reason && (
                              <div><span style={{ color:"#3a3a3a" }}>REASON: </span><span style={{ color:"#D4D4D4" }}>{meta.reason}</span></div>
                            )}
                          </div>
                          {meta.reasoning && (
                            <div style={{ marginTop:"8px", fontSize:"10px", color:"#5C5C5C", lineHeight:"1.6", borderTop:"1px solid #1a1a1a", paddingTop:"8px" }}>
                              {meta.reasoning}
                            </div>
                          )}
                          {meta.patterns && meta.patterns.length > 0 && (
                            <div style={{ marginTop:"6px", display:"flex", gap:"4px", flexWrap:"wrap" }}>
                              {meta.patterns.map((p, i) => (
                                <span key={i} className="tag" style={{ background:"#D4AF3712", color:"#D4AF37", fontSize:"9px", padding:"2px 6px" }}>{p}</span>
                              ))}
                            </div>
                          )}
                          {meta.indicators && typeof meta.indicators === "object" && (
                            <div style={{ marginTop:"6px", display:"flex", gap:"12px", flexWrap:"wrap", fontSize:"9px" }}>
                              {Object.entries(meta.indicators).filter(([k,v]) => typeof v === "number").slice(0, 8).map(([k, v]) => (
                                <div key={k}><span style={{ color:"#3a3a3a" }}>{k}: </span><span style={{ color:"#5C5C5C" }}>{typeof v === "number" ? v.toFixed(2) : String(v)}</span></div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Chart images */}
                      <div style={{ display:"flex", flexDirection:"column", gap:"16px" }}>
                        {timeframes.map(tf => (
                          <div key={tf} style={{ background:"#0A0A0A", border:"1px solid #1e1e1e", borderRadius:"6px", overflow:"hidden" }}>
                            <div style={{ padding:"8px 12px", borderBottom:"1px solid #1a1a1a", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                              <span style={{ fontSize:"10px", color:"#D4AF37", fontWeight:"700", letterSpacing:"1px" }}>
                                {tf.toUpperCase()} TIMEFRAME — {phase.toUpperCase()}
                              </span>
                              <span style={{ fontSize:"9px", color:"#3a3a3a" }}>{tradeDetail.trade?.symbol || "BTC"}/USD</span>
                            </div>
                            <img
                              src={`${backendBase}/api/trade/${tradeDetail.trade?.id}/screenshot/${phase}/${tf}${secretParam}`}
                              alt={`${phase} chart ${tf}`}
                              style={{ width:"100%", display:"block" }}
                              onError={e => { e.target.style.display = "none"; e.target.nextSibling && (e.target.nextSibling.style.display = "block"); }}
                            />
                            <div style={{ display:"none", padding:"40px", textAlign:"center", color:"#2a2a2a", fontSize:"11px" }}>
                              Failed to load {tf} chart
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Trade Context (from DB) */}
            {tradeDetail.context && (
              <div style={{ marginTop:"20px", background:"#111111", border:"1px solid #1e1e1e", borderRadius:"6px", padding:"14px 16px" }}>
                <div style={{ fontSize:"9px", color:"#D4AF37", letterSpacing:"2px", fontWeight:"700", marginBottom:"10px" }}>TRADE CONTEXT</div>
                <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(140px, 1fr))", gap:"8px" }}>
                  {[
                    { label:"REGIME", val:tradeDetail.context.regime },
                    { label:"CONFIDENCE", val:tradeDetail.context.confidence ? `${(tradeDetail.context.confidence * 100).toFixed(0)}%` : null },
                    { label:"CONFLUENCE", val:tradeDetail.context.confluence_score },
                    { label:"FEAR/GREED", val:tradeDetail.context.fear_greed },
                    { label:"SIZE %", val:tradeDetail.context.size_pct ? `${tradeDetail.context.size_pct}%` : null },
                    { label:"R:R RATIO", val:tradeDetail.context.rr_ratio ? tradeDetail.context.rr_ratio.toFixed(2) : null },
                    { label:"HOLD TIME", val:tradeDetail.context.hold_duration_sec ? `${Math.round(tradeDetail.context.hold_duration_sec / 60)}m` : null },
                    { label:"HOUR", val:tradeDetail.context.hour_of_day != null ? `${tradeDetail.context.hour_of_day}:00` : null },
                  ].filter(s => s.val != null).map(s => (
                    <div key={s.label} style={{ background:"#0A0A0A", borderRadius:"4px", padding:"8px 10px" }}>
                      <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"2px" }}>{s.label}</div>
                      <div style={{ fontSize:"12px", color:"#D4D4D4", fontWeight:"600" }}>{s.val}</div>
                    </div>
                  ))}
                </div>
                {tradeDetail.context.patterns && tradeDetail.context.patterns.length > 0 && (
                  <div style={{ marginTop:"10px" }}>
                    <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"4px" }}>PATTERNS DETECTED</div>
                    <div style={{ display:"flex", gap:"4px", flexWrap:"wrap" }}>
                      {tradeDetail.context.patterns.map((p, i) => (
                        <span key={i} className="tag" style={{ background:"#D4AF3712", color:"#D4AF37", fontSize:"9px", padding:"2px 8px" }}>{p}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Audit Trail */}
            {tradeDetail.audit && (
              <div style={{ marginTop:"16px", background:"#111111", border:"1px solid #1e1e1e", borderRadius:"6px", padding:"14px 16px", marginBottom:"20px" }}>
                <div style={{ fontSize:"9px", color:"#D4AF37", letterSpacing:"2px", fontWeight:"700", marginBottom:"10px" }}>DECISION AUDIT</div>
                <div style={{ fontSize:"10px", color:"#5C5C5C", lineHeight:"1.8" }}>
                  {tradeDetail.audit.reasoning && (
                    <div style={{ marginBottom:"8px" }}><span style={{ color:"#3a3a3a" }}>Reasoning: </span>{tradeDetail.audit.reasoning}</div>
                  )}
                  {tradeDetail.audit.adversary_verdict && tradeDetail.audit.adversary_verdict !== "none" && (
                    <div style={{ marginBottom:"4px" }}>
                      <span style={{ color:"#3a3a3a" }}>Adversary: </span>
                      <span style={{ color:tradeDetail.audit.adversary_verdict==="approve"?"#00E676":"#FF1744" }}>{tradeDetail.audit.adversary_verdict.toUpperCase()}</span>
                      {tradeDetail.audit.adversary_risk_score > 0 && <span style={{ color:"#5C5C5C" }}> (risk: {tradeDetail.audit.adversary_risk_score})</span>}
                    </div>
                  )}
                  {tradeDetail.audit.vision_structure && tradeDetail.audit.vision_structure !== "" && (
                    <div><span style={{ color:"#3a3a3a" }}>Vision: </span>{tradeDetail.audit.vision_structure} (conviction: {tradeDetail.audit.vision_conviction})</div>
                  )}
                  {tradeDetail.audit.model_used && (
                    <div><span style={{ color:"#3a3a3a" }}>Model: </span>{tradeDetail.audit.model_used}</div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ══ CONFIRM DIALOG ══ */}
      {confirmAction && (
        <div className="confirm-overlay" onClick={() => setConfirmAction(null)} role="dialog" aria-modal="true" aria-label="Confirmation">
          <div className="confirm-box" onClick={e => e.stopPropagation()}>
            <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"18px", color:"#D4AF37", letterSpacing:"3px", marginBottom:"16px" }}>CONFIRM ACTION</div>
            <div style={{ fontSize:"11px", color:"#D4D4D4", lineHeight:"1.9", marginBottom:"22px" }}>{confirmAction.label}</div>
            <div style={{ display:"flex", gap:"12px", justifyContent:"center" }}>
              <button className="btn btn-r" onClick={confirmYes} style={{ minWidth:"90px" }}>YES</button>
              <button className="btn btn-d" onClick={() => setConfirmAction(null)} style={{ minWidth:"90px", color:"#D4D4D4" }}>CANCEL</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Analytics Section (Equity Curve + Trade Analytics + Memory + Backtest) ────
function AnalyticsSection({ connected, log, lossToast, cbLive, krakenEnabled, hasClaude, isLiveMode, agentKit, paperMode, directionBias, requireTradeApproval, price, priceAge, wsRetrying }) {
  const { user, profile, signOut } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("equity");
  const [equityData, setEquityData] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [memoryData, setMemoryData] = useState(null);
  const [calibrationData, setCalibrationData] = useState(null);
  const [backtestResult, setBacktestResult] = useState(null);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [btParams, setBtParams] = useState({ symbol:"BTC", days:30, tp:2.5, sl:1.0, confluence:5, rr:1.8 });
  const [loading, setLoading] = useState(false);

  const backendBase = BACKEND_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;

  const fetchData = useCallback(async (tab) => {
    if (!connected) return;
    setLoading(true);
    try {
      const headers = authHeaders();
      if (tab === "equity") {
        const r = await fetch(`${backendBase}/equity`, { headers });
        if (r.ok) setEquityData(await r.json());
      } else if (tab === "analytics") {
        const r = await fetch(`${backendBase}/memory/analysis`, { headers });
        if (r.ok) setAnalyticsData(await r.json());
      } else if (tab === "memory") {
        const [rulesR, patternsR] = await Promise.all([
          fetch(`${backendBase}/memory/rules`, { headers }),
          fetch(`${backendBase}/memory/patterns`, { headers }),
        ]);
        const rules = rulesR.ok ? await rulesR.json() : { rules: [] };
        const patterns = patternsR.ok ? await patternsR.json() : { patterns: [] };
        setMemoryData({ ...rules, ...patterns });
      } else if (tab === "calibration") {
        const r = await fetch(`${backendBase}/memory/calibration`, { headers });
        if (r.ok) setCalibrationData(await r.json());
      }
    } catch (e) {
      log?.(`Analytics fetch error: ${e.message}`, "error");
    } finally {
      setLoading(false);
    }
  }, [connected, backendBase, log]);

  useEffect(() => { fetchData(activeTab); }, [activeTab, fetchData]);

  const runBacktest = async () => {
    setBacktestLoading(true);
    try {
      const params = new URLSearchParams({
        symbol: btParams.symbol, days: btParams.days,
        tp_atr_mult: btParams.tp, sl_atr_mult: btParams.sl,
        min_confluence: btParams.confluence, min_rr: btParams.rr,
      });
      const r = await fetch(`${backendBase}/backtest?${params}`, { method: "POST", headers: authHeaders() });
      if (r.ok) {
        const data = await r.json();
        setBacktestResult(data);
        log?.(`Backtest: ${data.total_trades} trades, ${data.return_pct >= 0 ? "+" : ""}${data.return_pct}% return`, "info");
      }
    } catch (e) {
      log?.(`Backtest error: ${e.message}`, "error");
    } finally {
      setBacktestLoading(false);
    }
  };

  const tabs = [
    { id:"equity", label:"EQUITY CURVE" },
    { id:"analytics", label:"TRADE ANALYTICS" },
    { id:"memory", label:"BRAIN / MEMORY" },
    { id:"calibration", label:"CONFIDENCE" },
    { id:"backtest", label:"BACKTEST" },
  ];

  if (!connected) return null;

  return (
    <div style={{ marginTop:"16px" }}>
      <div style={{ display:"flex", gap:"6px", marginBottom:"12px", overflowX:"auto" }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            className="btn" style={{
              padding:"6px 14px", fontSize:"9px", letterSpacing:"1.5px",
              background: activeTab === t.id ? "#D4AF3711" : "transparent",
              color: activeTab === t.id ? "#D4AF37" : "#5C5C5C",
              border: `1px solid ${activeTab === t.id ? "#D4AF3733" : "#1e1e1e"}`,
            }}>{t.label}</button>
        ))}
        <button className="btn btn-d" onClick={() => fetchData(activeTab)} style={{ marginLeft:"auto", padding:"4px 10px", fontSize:"9px" }}>{"\u21BB"}</button>
      </div>

      <div className="card" style={{ minHeight:"200px" }}>
        {loading && (
          <div style={{ padding:"24px", display:"flex", flexDirection:"column", gap:"12px" }}>
            <Skeleton width="40%" height={14} />
            <Skeleton width="100%" height={80} />
            <Skeleton width="60%" height={14} />
            <Skeleton width="100%" height={60} />
          </div>
        )}

        {/* ── EQUITY CURVE ── */}
        {activeTab === "equity" && !loading && equityData && (
          <div>
            <div className="section-label" style={{ marginBottom:"12px" }}>EQUITY CURVE</div>
            {equityData.curve?.length > 0 ? (
              <div>
                <div style={{ display:"flex", gap:"16px", marginBottom:"14px", flexWrap:"wrap" }}>
                  {equityData.sessions?.slice(0, 7).map(s => (
                    <div key={s.date} style={{ background:"#0A0A0A", borderRadius:"5px", padding:"8px 12px", minWidth:"100px" }}>
                      <div style={{ fontSize:"8px", color:"#3a3a3a" }}>{s.date}</div>
                      <div style={{ fontSize:"11px", fontWeight:"700", color: s.total_pnl >= 0 ? "#00E676" : "#FF1744" }}>
                        {s.total_pnl >= 0 ? "+" : ""}${s.total_pnl?.toFixed(2)}
                      </div>
                      <div style={{ fontSize:"8px", color:"#5C5C5C" }}>{s.trades_taken} trades | {s.wins}W/{s.losses}L</div>
                    </div>
                  ))}
                </div>
                <div style={{ height:"120px", display:"flex", alignItems:"flex-end", gap:"1px", padding:"0 4px" }}>
                  {(() => {
                    const pts = equityData.curve;
                    const balances = pts.map(p => p.balance);
                    const mn = Math.min(...balances);
                    const mx = Math.max(...balances);
                    const range = mx - mn || 1;
                    const step = Math.max(1, Math.floor(pts.length / 80));
                    const sampled = pts.filter((_, i) => i % step === 0 || i === pts.length - 1);
                    return sampled.map((p, i) => {
                      const h = Math.max(2, ((p.balance - mn) / range) * 110);
                      const isUp = i > 0 ? p.balance >= sampled[i-1].balance : true;
                      return <div key={i} title={`${p.ts}: $${p.balance.toFixed(2)}`} style={{ flex:1, minWidth:"2px", maxWidth:"8px", height:`${h}px`, background: isUp ? "#00E67688" : "#FF174488", borderRadius:"1px 1px 0 0", transition:"height 0.3s" }} />;
                    });
                  })()}
                </div>
                <div style={{ display:"flex", justifyContent:"space-between", fontSize:"9px", color:"#3a3a3a", marginTop:"4px" }}>
                  <span>{equityData.curve[0]?.ts?.split(" ")[0]}</span>
                  <span>{equityData.curve[equityData.curve.length-1]?.ts?.split(" ")[0]}</span>
                </div>
              </div>
            ) : (
              <div style={{ textAlign:"center", padding:"30px", color:"#2a2a2a", fontSize:"11px" }}>
                No snapshots yet — run the bot for a few hours to build the equity curve
              </div>
            )}
          </div>
        )}

        {/* ── TRADE ANALYTICS ── */}
        {activeTab === "analytics" && !loading && analyticsData && (
          <div>
            <div className="section-label" style={{ marginBottom:"12px" }}>TRADE ANALYTICS</div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"14px" }}>
              {/* Regime performance */}
              <div>
                <div style={{ fontSize:"9px", color:"#5C5C5C", letterSpacing:"1px", marginBottom:"8px" }}>BY REGIME</div>
                {Object.entries(analyticsData.regime || {}).map(([regime, data]) => (
                  <div key={regime} className="row" style={{ fontSize:"10px" }}>
                    <span style={{ color: {trending_up:"#00E676", trending_down:"#FF1744", ranging:"#D4AF37", chaotic:"#ff9900"}[regime] || "#5C5C5C", fontWeight:"700", textTransform:"uppercase" }}>{regime}</span>
                    <span>
                      <span style={{ color: data.win_rate >= 50 ? "#00E676" : "#FF1744", fontWeight:"700" }}>{data.win_rate}%</span>
                      <span style={{ color:"#3a3a3a", marginLeft:"6px" }}>{data.total} trades</span>
                      <span style={{ color: data.total_pnl >= 0 ? "#00E676" : "#FF1744", marginLeft:"6px" }}>{data.total_pnl >= 0 ? "+" : ""}${data.total_pnl}</span>
                    </span>
                  </div>
                ))}
              </div>
              {/* Hourly performance */}
              <div>
                <div style={{ fontSize:"9px", color:"#5C5C5C", letterSpacing:"1px", marginBottom:"8px" }}>BEST HOURS (UTC)</div>
                {(analyticsData.hourly || []).slice(0, 6).map(h => (
                  <div key={h.hour_of_day} className="row" style={{ fontSize:"10px" }}>
                    <span style={{ color:"#D4D4D4" }}>{String(h.hour_of_day).padStart(2, "0")}:00</span>
                    <span>
                      <span style={{ color: h.win_rate >= 50 ? "#00E676" : "#FF1744", fontWeight:"700" }}>{h.win_rate}% WR</span>
                      <span style={{ color:"#3a3a3a", marginLeft:"6px" }}>avg ${h.avg_pnl}</span>
                    </span>
                  </div>
                ))}
              </div>
              {/* Sizing analysis */}
              <div>
                <div style={{ fontSize:"9px", color:"#5C5C5C", letterSpacing:"1px", marginBottom:"8px" }}>BY SIZE</div>
                {(analyticsData.sizing || []).map(s => (
                  <div key={s.size_band} className="row" style={{ fontSize:"10px" }}>
                    <span style={{ color:"#D4D4D4" }}>{s.size_band.replace("_"," ")}</span>
                    <span>
                      <span style={{ color: s.win_rate >= 50 ? "#00E676" : "#FF1744", fontWeight:"700" }}>{s.win_rate}% WR</span>
                      <span style={{ color:"#3a3a3a", marginLeft:"6px" }}>{s.total} trades</span>
                    </span>
                  </div>
                ))}
              </div>
              {/* Confidence analysis */}
              <div>
                <div style={{ fontSize:"9px", color:"#5C5C5C", letterSpacing:"1px", marginBottom:"8px" }}>BY CONFIDENCE</div>
                {(analyticsData.confidence || []).map(c => (
                  <div key={c.confidence_band} className="row" style={{ fontSize:"10px" }}>
                    <span style={{ color:"#D4AF37" }}>{c.confidence_band.replace("_"," ")}</span>
                    <span>
                      <span style={{ color: c.win_rate >= 50 ? "#00E676" : "#FF1744", fontWeight:"700" }}>{c.win_rate}% WR</span>
                      <span style={{ color:"#3a3a3a", marginLeft:"6px" }}>avg ${c.avg_pnl}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── BRAIN / MEMORY ── */}
        {activeTab === "memory" && !loading && memoryData && (
          <div>
            <div className="section-label" style={{ marginBottom:"12px" }}>LEARNED RULES & PATTERNS</div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"14px" }}>
              <div>
                <div style={{ fontSize:"9px", color:"#5C5C5C", letterSpacing:"1px", marginBottom:"8px" }}>
                  ACTIVE RULES ({memoryData.total_rules || 0})
                </div>
                {(memoryData.rules || []).length === 0 ? (
                  <div style={{ fontSize:"10px", color:"#2a2a2a", padding:"12px 0" }}>No rules learned yet — need 5+ trades</div>
                ) : (
                  (memoryData.rules || []).slice(0, 10).map(rule => (
                    <div key={rule.rule_key} style={{ background:"#0A0A0A", borderRadius:"5px", padding:"8px 10px", marginBottom:"6px", border:"1px solid #1e1e1e" }}>
                      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:"4px" }}>
                        <span className="tag" style={{ background: rule.rule_type === "avoid" ? "#FF174418" : "#00E67618", color: rule.rule_type === "avoid" ? "#FF1744" : "#00E676", fontSize:"8px" }}>
                          {rule.rule_type?.toUpperCase()}
                        </span>
                        <span style={{ fontSize:"8px", color:"#3a3a3a" }}>
                          {rule.sample_size} samples | {rule.win_rate}% WR
                        </span>
                      </div>
                      <div style={{ fontSize:"10px", color:"#999999", lineHeight:"1.6" }}>{rule.description}</div>
                    </div>
                  ))
                )}
              </div>
              <div>
                <div style={{ fontSize:"9px", color:"#5C5C5C", letterSpacing:"1px", marginBottom:"8px" }}>
                  PATTERN PERFORMANCE ({memoryData.total_trades || 0} trades analyzed)
                </div>
                {(memoryData.patterns || []).length === 0 ? (
                  <div style={{ fontSize:"10px", color:"#2a2a2a", padding:"12px 0" }}>No pattern data yet</div>
                ) : (
                  (memoryData.patterns || []).slice(0, 12).map((p, i) => (
                    <div key={i} className="row" style={{ fontSize:"10px" }}>
                      <div>
                        <span style={{ color:"#D4D4D4" }}>{p.pattern}</span>
                        <span style={{ color:"#3a3a3a", fontSize:"8px", marginLeft:"4px" }}>{p.symbol} {p.side} ({p.regime})</span>
                      </div>
                      <span>
                        <span style={{ color: p.win_rate >= 50 ? "#00E676" : "#FF1744", fontWeight:"700" }}>{p.win_rate}%</span>
                        <span style={{ color:"#3a3a3a", marginLeft:"4px" }}>{p.total}x</span>
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── CONFIDENCE CALIBRATION ── */}
        {activeTab === "calibration" && !loading && calibrationData && (
          <div>
            <div className="section-label" style={{ marginBottom:"6px" }}>CONFIDENCE CALIBRATION</div>
            <div style={{ fontSize:"10px", color:"#5C5C5C", marginBottom:"14px" }}>
              Does Claude&apos;s confidence actually predict win rate? Perfect calibration = predicted matches actual.
            </div>
            {(calibrationData.calibration || []).length === 0 ? (
              <div style={{ fontSize:"10px", color:"#2a2a2a", padding:"20px", textAlign:"center" }}>Need more trades with confidence data</div>
            ) : (
              <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(140px, 1fr))", gap:"10px" }}>
                {(calibrationData.calibration || []).map(c => {
                  const predicted = c.avg_predicted;
                  const actual = c.actual_win_rate;
                  const gap = Math.abs(predicted - actual);
                  const calibrated = gap < 10;
                  return (
                    <div key={c.predicted_band} style={{ background:"#0A0A0A", borderRadius:"5px", padding:"12px", border:`1px solid ${calibrated ? "#00E67622" : "#ff990022"}`, textAlign:"center" }}>
                      <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"6px" }}>PREDICTED {c.predicted_band}</div>
                      <div style={{ fontSize:"16px", fontFamily:"'Bebas Neue',sans-serif", fontWeight:"700", color:"#D4AF37" }}>{predicted}%</div>
                      <div style={{ fontSize:"8px", color:"#3a3a3a", margin:"4px 0" }}>vs actual</div>
                      <div style={{ fontSize:"16px", fontFamily:"'Bebas Neue',sans-serif", fontWeight:"700", color: actual >= 50 ? "#00E676" : "#FF1744" }}>{actual}%</div>
                      <div style={{ fontSize:"8px", color: calibrated ? "#00E676" : "#ff9900", marginTop:"6px" }}>
                        {calibrated ? "CALIBRATED" : `${gap.toFixed(0)}% OFF`}
                      </div>
                      <div style={{ fontSize:"8px", color:"#3a3a3a", marginTop:"2px" }}>{c.total} trades | ${c.total_pnl}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ── BACKTEST ── */}
        {activeTab === "backtest" && !loading && (
          <div>
            <div className="section-label" style={{ marginBottom:"12px" }}>HISTORICAL BACKTEST</div>
            <div style={{ display:"flex", gap:"10px", flexWrap:"wrap", alignItems:"flex-end", marginBottom:"14px" }}>
              {[
                { label:"COIN", key:"symbol", type:"select", options:["BTC","ETH","SOL","LINK","DOGE","AVAX"] },
                { label:"DAYS", key:"days", type:"number", min:7, max:365 },
                { label:"TP (ATR x)", key:"tp", type:"number", step:0.5, min:1 },
                { label:"SL (ATR x)", key:"sl", type:"number", step:0.25, min:0.5 },
                { label:"MIN CONFLUENCE", key:"confluence", type:"number", min:1, max:20 },
                { label:"MIN R:R", key:"rr", type:"number", step:0.2, min:1 },
              ].map(f => (
                <div key={f.key}>
                  <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>{f.label}</div>
                  {f.type === "select" ? (
                    <select value={btParams[f.key]} onChange={e => setBtParams(p => ({ ...p, [f.key]: e.target.value }))}
                      style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none" }}>
                      {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <input type="number" value={btParams[f.key]} onChange={e => setBtParams(p => ({ ...p, [f.key]: +e.target.value }))}
                      min={f.min} max={f.max} step={f.step || 1}
                      style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none", width:"70px" }} />
                  )}
                </div>
              ))}
              <button className="btn btn-p" onClick={runBacktest} disabled={backtestLoading} style={{ alignSelf:"flex-end" }}>
                {backtestLoading ? <span className="blink">RUNNING...</span> : "RUN BACKTEST"}
              </button>
            </div>

            {backtestResult && !backtestResult.error && (
              <div>
                <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(120px, 1fr))", gap:"8px", marginBottom:"14px" }}>
                  {[
                    { label:"RETURN", val:`${backtestResult.return_pct >= 0 ? "+" : ""}${backtestResult.return_pct}%`, color: backtestResult.return_pct >= 0 ? "#00E676" : "#FF1744" },
                    { label:"TOTAL P&L", val:`${backtestResult.total_pnl >= 0 ? "+" : ""}$${backtestResult.total_pnl}`, color: backtestResult.total_pnl >= 0 ? "#00E676" : "#FF1744" },
                    { label:"TRADES", val:backtestResult.total_trades, color:"#D4D4D4" },
                    { label:"WIN RATE", val:`${backtestResult.win_rate}%`, color: backtestResult.win_rate >= 50 ? "#00E676" : "#FF1744" },
                    { label:"AVG WIN", val:`+$${backtestResult.avg_win}`, color:"#00E676" },
                    { label:"AVG LOSS", val:`$${backtestResult.avg_loss}`, color:"#FF1744" },
                    { label:"MAX DD", val:`${backtestResult.max_drawdown_pct}%`, color: backtestResult.max_drawdown_pct > 15 ? "#FF1744" : "#ff9900" },
                    { label:"PROFIT FACTOR", val:backtestResult.profit_factor, color: backtestResult.profit_factor >= 1.5 ? "#00E676" : "#ff9900" },
                  ].map(s => (
                    <div key={s.label} style={{ background:"#0A0A0A", borderRadius:"5px", padding:"8px 10px", textAlign:"center" }}>
                      <div style={{ fontSize:"8px", color:"#3a3a3a", marginBottom:"3px" }}>{s.label}</div>
                      <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"13px", fontWeight:"700", color:s.color }}>{s.val}</div>
                    </div>
                  ))}
                </div>
                {backtestResult.trades?.length > 0 && (
                  <div style={{ maxHeight:"200px", overflowY:"auto" }}>
                    {backtestResult.trades.map((t, i) => (
                      <div key={i} className="trow" style={{ fontSize:"10px" }}>
                        <div>
                          <span className="tag" style={{ background: t.side==="buy"?"#00E67618":"#FF174418", color: t.side==="buy"?"#00E676":"#FF1744", marginRight:"4px" }}>
                            {t.side?.toUpperCase()}
                          </span>
                          <span style={{ color:"#D4D4D4" }}>${t.entry?.toLocaleString()} → ${t.exit?.toLocaleString()}</span>
                        </div>
                        <div style={{ textAlign:"right" }}>
                          <span style={{ fontWeight:"700", color: t.win ? "#00E676" : "#FF1744" }}>{t.pnl >= 0 ? "+" : ""}${t.pnl}</span>
                          <span style={{ color:"#3a3a3a", marginLeft:"6px", fontSize:"9px" }}>{t.reason}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {backtestResult?.error && (
              <div style={{ fontSize:"11px", color:"#FF1744", padding:"16px", textAlign:"center" }}>{backtestResult.error}</div>
            )}
            {!backtestResult && (
              <div style={{ textAlign:"center", padding:"30px", color:"#2a2a2a", fontSize:"11px" }}>
                Configure parameters and click RUN BACKTEST to test your strategy against historical data
              </div>
            )}
          </div>
        )}
      </div>

      {/* Loss notification toast */}
      {lossToast && (
        <div
          style={{
            position: "fixed", bottom: "40px", left: "50%", transform: "translateX(-50%)",
            background: "#1a0a0a", border: "1px solid #C0392B55", borderRadius: "8px",
            padding: "12px 20px", boxShadow: "0 4px 24px rgba(192,57,43,0.3)",
            fontFamily: "'Oswald',sans-serif", fontSize: "13px", fontWeight: "600",
            color: "#FF1744", letterSpacing: "2px", zIndex: 9999,
            animation: "lossToastIn 0.3s ease-out",
          }}
          role="alert"
        >
          {lossToast.msg}
        </div>
      )}

      {/* ══ FOOTER — User nav + Status bar (blended) ══ */}
      <div className="status-bar" style={{
        position:"fixed", bottom:0, left:0, right:0, zIndex:9000,
        display:"flex", flexWrap:"wrap", alignItems:"center", justifyContent:"space-between", gap:"8px",
        padding:"8px 16px",
        background:"#0A0A0Aee", borderTop:"2px solid #D4AF3733",
        backdropFilter:"blur(12px)", WebkitBackdropFilter:"blur(12px)",
      }}>
        {/* Left: user identity */}
        <span style={{ fontSize:"11px", color:"#5C5C5C", fontFamily:"'Space Mono',monospace" }}>
          {profile?.display_name || user?.email || ""}
        </span>
        {/* Center: status badges */}
        <div style={{ display:"flex", gap:"6px", flexWrap:"wrap", alignItems:"center", justifyContent:"center", flex:1, minWidth:0 }}>
          {[
            { label:"BACKEND",    ok:connected,  on:"LIVE",        off:"OFFLINE",     okColor:"#D4AF37", offColor:"#FF1744" },
            { label:"COINBASE",   ok:cbLive,     on:"REAL-TIME",   off:"REST",        okColor:"#D4AF37", offColor:"#ff9900" },
            { label:"KRAKEN",     ok:krakenEnabled, on:"SPOT",    off:"OFF",         okColor:"#D4AF37", offColor:"#3a3a3a" },
            { label:"CLAUDE",     ok:hasClaude,  on:"READY",       off:"NO KEY",      okColor:"#D4AF37", offColor:"#ff9900" },
            { label:"MODE",       ok:isLiveMode, on:"LIVE",        off:"PAPER",       okColor:"#C0392B", offColor:"#ff9900" },
            { label:"AGENTKIT",  ok:agentKit.agentkit_ready, on:"ON-CHAIN",   off: paperMode ? "PAPER" : "OFFLINE", okColor:"#D4AF37", offColor:"#3a3a3a" },
          ].map(s => (
            <div key={s.label} style={{ display:"flex", gap:"4px", alignItems:"center", background:"#111111", border:"1px solid #1e1e1e", borderRadius:"4px", padding:"3px 7px" }} role="status" aria-label={`${s.label}: ${s.ok ? s.on : s.off}`}>
              <span style={{ fontSize:"7px", color:"#5C5C5C", letterSpacing:"0.5px" }}>{s.label}</span>
              <span style={{ fontSize:"9px", fontWeight:"700", color: s.ok ? s.okColor : s.offColor }}>
                <span className="dot" style={{ background: s.ok ? s.okColor : s.offColor, width:"4px", height:"4px", marginRight:"2px", verticalAlign:"middle" }} />
                {s.ok ? s.on : s.off}
              </span>
            </div>
          ))}
          {directionBias !== "both" && (
            <div style={{ display:"flex", gap:"4px", alignItems:"center", background:"#111111", border:"1px solid #1e1e1e", borderRadius:"4px", padding:"3px 7px" }}>
              <span style={{ fontSize:"7px", color:"#5C5C5C" }}>DIRECTION</span>
              <span style={{ fontSize:"9px", fontWeight:"700", color: directionBias === "long" ? "#00E676" : "#FF1744" }}>
                {directionBias === "long" ? "\u25B2 LONG ONLY" : "\u25BC SHORT ONLY"}
              </span>
            </div>
          )}
          {requireTradeApproval && (
            <div style={{ display:"flex", gap:"4px", alignItems:"center", background:"#ff990018", border:"1px solid #ff990044", borderRadius:"4px", padding:"3px 7px" }}>
              <span style={{ fontSize:"7px", color:"#ff9900" }}>APPROVAL</span>
              <span style={{ fontSize:"9px", fontWeight:"700", color:"#ff9900" }}>ON</span>
            </div>
          )}
          {price > 0 && <span style={{ fontSize:"8px", color: priceAge > 60 ? "#ff9900" : "#5C5C5C" }}>price <AnimatedNumber value={priceAge} format={(v)=>`${Math.round(v)}s`} duration={100} /> ago</span>}
          {wsRetrying && !connected && <span style={{ fontSize:"8px", color:"#ff9900" }}>Reconnecting...</span>}
          {!connected && !wsRetrying && <span style={{ fontSize:"8px", color:"#ff9900" }}>Start backend.py</span>}
        </div>
        {/* Right: nav links */}
        <div style={{ display:"flex", alignItems:"center", gap:"8px", flexShrink:0 }}>
          <button
            onClick={() => navigate("/history")}
            style={{ fontFamily:"'Oswald',sans-serif", fontSize:"10px", fontWeight:"600", letterSpacing:"1.5px", padding:"4px 12px", border:"1px solid #1A1A1A", borderRadius:"3px", background:"transparent", color:"#888", cursor:"pointer" }}
          >
            HISTORY
          </button>
          <button
            onClick={() => navigate("/billing")}
            style={{ fontFamily:"'Oswald',sans-serif", fontSize:"10px", fontWeight:"600", letterSpacing:"1.5px", padding:"4px 12px", border:"1px solid #1A1A1A", borderRadius:"3px", background:"transparent", color:"#888", cursor:"pointer" }}
          >
            BILLING
          </button>
          <button
            onClick={() => navigate("/settings")}
            style={{ fontFamily:"'Oswald',sans-serif", fontSize:"10px", fontWeight:"600", letterSpacing:"1.5px", padding:"4px 12px", border:"1px solid #1A1A1A", borderRadius:"3px", background:"transparent", color:"#D4AF37", cursor:"pointer" }}
          >
            SETTINGS
          </button>
          <button
            onClick={signOut}
            style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"4px 10px", border:"1px solid #1A1A1A", borderRadius:"3px", background:"transparent", color:"#5C5C5C", cursor:"pointer" }}
          >
            Sign Out
          </button>
        </div>
      </div>
    </div>
  );
}


export default function App() {
  return (
    <ErrorBoundary>
      <Dashboard />
    </ErrorBoundary>
  );
}
