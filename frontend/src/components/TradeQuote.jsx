import { useState, useEffect } from "react";
import { colors } from "../theme.js";

export const TRADE_QUOTES = [
  "The market rewards patience and punishes greed.",
  "Risk what you can afford, protect what you can't.",
  "Discipline is the bridge between goals and results.",
  "Trade the plan, not the emotion.",
  "In markets, conviction without evidence is just gambling.",
];

export function TradeQuote() {
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
    <div style={{ fontFamily:"'Space Mono',monospace", fontSize:"11px", color:colors.gold, letterSpacing:"0.5px", fontStyle:"italic", maxWidth:"min(300px, calc(100vw - 48px))", lineHeight:"1.5", opacity:fade?1:0, transition:"opacity 0.4s ease" }}>
      &ldquo;{TRADE_QUOTES[idx]}&rdquo;
    </div>
  );
}
