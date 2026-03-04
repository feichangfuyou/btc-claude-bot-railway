import { useEffect, useRef, useCallback } from "react";
import { createChart, CrosshairMode, LineStyle, CandlestickSeries, HistogramSeries } from "lightweight-charts";

const CHART_BG = "#06060f";
const GRID_COLOR = "#0d0d1c";
const TEXT_COLOR = "#2d3748";
const UP_COLOR = "#00ff88";
const DOWN_COLOR = "#ff3366";
const CROSSHAIR_COLOR = "#4a5568";

export default function TradingViewChart({ history, position, priceUp, height }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const volumeSeriesRef = useRef(null);
  const entryLineRef = useRef(null);
  const tpLineRef = useRef(null);
  const slLineRef = useRef(null);
  const resizeObserverRef = useRef(null);

  const initChart = useCallback(() => {
    if (!containerRef.current) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: height || containerRef.current.clientHeight || 380,
      layout: {
        background: { color: CHART_BG },
        textColor: TEXT_COLOR,
        fontFamily: "'Space Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: GRID_COLOR },
        horzLines: { color: GRID_COLOR },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: CROSSHAIR_COLOR, width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#131828" },
        horzLine: { color: CROSSHAIR_COLOR, width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#131828" },
      },
      rightPriceScale: {
        borderColor: "#131828",
        scaleMargins: { top: 0.08, bottom: 0.15 },
      },
      timeScale: {
        borderColor: "#131828",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 5,
        barSpacing: 8,
        fixLeftEdge: false,
        fixRightEdge: false,
      },
      handleScroll: { vertTouchDrag: false },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: UP_COLOR,
      downColor: DOWN_COLOR,
      borderUpColor: UP_COLOR,
      borderDownColor: DOWN_COLOR,
      wickUpColor: UP_COLOR,
      wickDownColor: DOWN_COLOR,
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    resizeObserverRef.current = new ResizeObserver((entries) => {
      const { width, height: h } = entries[0].contentRect;
      chart.applyOptions({ width, height: h });
    });
    resizeObserverRef.current.observe(containerRef.current);
  }, [height]);

  useEffect(() => {
    initChart();
    return () => {
      resizeObserverRef.current?.disconnect();
      chartRef.current?.remove();
      chartRef.current = null;
    };
  }, [initChart]);

  const prevLenRef = useRef(0);

  useEffect(() => {
    if (!candleSeriesRef.current || !history || history.length === 0) return;

    const candles = history
      .filter((h) => h.time != null)
      .map((h) => ({
        time: h.time,
        open: h.open,
        high: h.high,
        low: h.low,
        close: h.close,
      }));

    if (candles.length === 0) return;

    const isFullRefresh = Math.abs(candles.length - prevLenRef.current) > 2 || prevLenRef.current === 0;
    prevLenRef.current = candles.length;

    if (isFullRefresh) {
      candleSeriesRef.current.setData(candles);
    } else {
      candleSeriesRef.current.update(candles[candles.length - 1]);
    }

    const volumes = history
      .filter((h) => h.time != null && h.volume != null)
      .map((h) => ({
        time: h.time,
        value: h.volume || 0,
        color: h.close >= h.open ? UP_COLOR + "30" : DOWN_COLOR + "30",
      }));

    if (volumes.length > 0) {
      if (isFullRefresh) {
        volumeSeriesRef.current.setData(volumes);
      } else {
        volumeSeriesRef.current.update(volumes[volumes.length - 1]);
      }
    }

    if (isFullRefresh) {
      chartRef.current?.timeScale().scrollToPosition(2, false);
    }
  }, [history]);

  useEffect(() => {
    if (!candleSeriesRef.current) return;

    [entryLineRef, tpLineRef, slLineRef].forEach((ref) => {
      if (ref.current) {
        candleSeriesRef.current.removePriceLine(ref.current);
        ref.current = null;
      }
    });

    if (!position) return;

    entryLineRef.current = candleSeriesRef.current.createPriceLine({
      price: position.entry,
      color: "#00d4ff",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "ENTRY",
    });

    tpLineRef.current = candleSeriesRef.current.createPriceLine({
      price: position.tp,
      color: UP_COLOR,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "TP",
    });

    slLineRef.current = candleSeriesRef.current.createPriceLine({
      price: position.sl,
      color: DOWN_COLOR,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "SL",
    });
  }, [position]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", minHeight: 280 }}
    />
  );
}
