import { TickerTape } from "./TickerTape.jsx";
import { TradeQuote } from "./TradeQuote.jsx";

export function AppHeader({
  marketTickers,
  activeCoins,
  coins,
  price,
  selectedCoin,
  positions,
  onSelectCoin,
}) {
  return (
    <header className="app-header" aria-label="App header">
      <div className="app-header__brand">
        <span className="app-header__logo-wrap">
          <img src="/Bravo.svg" alt="DoYou.trade" className="brand-logo" />
        </span>
        <div className="app-header__brand-text">
          <div className="brand-title">DOYOU.TRADE</div>
          <div className="app-header__brand-rule" aria-hidden="true" />
          <TradeQuote />
        </div>
      </div>
      <div className="app-header__ticker">
        <TickerTape
          marketTickers={marketTickers}
          activeCoins={activeCoins}
          coins={coins}
          price={price}
          selectedCoin={selectedCoin}
          positions={positions}
          onSelectCoin={onSelectCoin}
        />
      </div>
    </header>
  );
}
