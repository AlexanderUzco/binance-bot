/* BinBot — TradingView Lightweight Charts renderer */

(function () {
  "use strict";

  const SYMBOL = document.getElementById("price-chart").dataset.symbol;
  const REFRESH_MS = 10000;

  // State
  let priceChart, rsiChart, adxChart;
  let candleSeries, volumeSeries;
  let ema9Series, ema21Series, bbUpperSeries, bbLowerSeries, supertrendSeries;
  let rsiSeries, adxSeries, plusDiSeries, minusDiSeries;
  let priceLinesAdded = false;
  let refreshTimer = null;

  // Toggle visibility state
  const visible = { bb: true, supertrend: true, ema: true };

  // ── Chart creation ──

  function createCharts() {
    const opts = {
      layout: {
        background: { color: "#0d1117" },
        textColor: "#8b949e",
        fontFamily:
          "'SF Mono','Cascadia Code','Fira Code',monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#1c2128" },
        horzLines: { color: "#1c2128" },
      },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#30363d" },
      timeScale: {
        borderColor: "#30363d",
        timeVisible: true,
        secondsVisible: false,
      },
    };

    // Price chart (400px)
    priceChart = LightweightCharts.createChart(
      document.getElementById("price-chart"),
      { ...opts, height: 400 }
    );

    candleSeries = priceChart.addCandlestickSeries({
      upColor: "#3fb950",
      downColor: "#f85149",
      borderUpColor: "#3fb950",
      borderDownColor: "#f85149",
      wickUpColor: "#3fb950",
      wickDownColor: "#f85149",
    });

    volumeSeries = priceChart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    priceChart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    ema9Series = priceChart.addLineSeries({
      color: "#d29922",
      lineWidth: 1,
      title: "EMA 9",
    });
    ema21Series = priceChart.addLineSeries({
      color: "#58a6ff",
      lineWidth: 1,
      title: "EMA 21",
    });

    bbUpperSeries = priceChart.addLineSeries({
      color: "#58a6ff",
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      title: "BB Upper",
    });
    bbLowerSeries = priceChart.addLineSeries({
      color: "#58a6ff",
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      title: "BB Lower",
    });

    supertrendSeries = priceChart.addLineSeries({
      lineWidth: 2,
      title: "Supertrend",
      color: "#3fb950",
    });

    // RSI chart (120px)
    rsiChart = LightweightCharts.createChart(
      document.getElementById("rsi-chart"),
      { ...opts, height: 120 }
    );

    rsiSeries = rsiChart.addLineSeries({
      color: "#d29922",
      lineWidth: 1,
      title: "RSI",
    });

    // ADX chart (120px)
    adxChart = LightweightCharts.createChart(
      document.getElementById("adx-chart"),
      { ...opts, height: 120 }
    );

    adxSeries = adxChart.addLineSeries({
      color: "#e6edf3",
      lineWidth: 1,
      title: "ADX",
    });
    plusDiSeries = adxChart.addLineSeries({
      color: "#3fb950",
      lineWidth: 1,
      title: "+DI",
    });
    minusDiSeries = adxChart.addLineSeries({
      color: "#f85149",
      lineWidth: 1,
      title: "-DI",
    });

    // Sync time scales
    syncTimeScales([priceChart, rsiChart, adxChart]);

    // Responsive
    const ro = new ResizeObserver(() => {
      const w = document.getElementById("price-chart").clientWidth;
      priceChart.applyOptions({ width: w });
      rsiChart.applyOptions({ width: w });
      adxChart.applyOptions({ width: w });
    });
    ro.observe(document.getElementById("price-chart"));
  }

  function syncTimeScales(charts) {
    let syncing = false;
    charts.forEach((src, i) => {
      src.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (syncing || !range) return;
        syncing = true;
        charts.forEach((dst, j) => {
          if (i !== j) dst.timeScale().setVisibleLogicalRange(range);
        });
        syncing = false;
      });
    });
  }

  // ── Data fetching & rendering ──

  async function fetchAndRender() {
    let data;
    try {
      const resp = await fetch(`/api/pair/${SYMBOL}/chart-data`);
      if (!resp.ok) return;
      data = await resp.json();
    } catch {
      return;
    }
    if (!data.candles || !data.candles.length) return;

    // Price chart
    candleSeries.setData(data.candles);
    volumeSeries.setData(data.volume);

    if (visible.ema) {
      ema9Series.setData(data.ema9);
      ema21Series.setData(data.ema21);
    }
    if (visible.bb) {
      bbUpperSeries.setData(data.bb_upper);
      bbLowerSeries.setData(data.bb_lower);
    }

    // Supertrend: color segments by direction
    if (visible.supertrend && data.supertrend.length) {
      renderSupertrend(data.supertrend);
    }

    // Markers
    if (data.markers && data.markers.length) {
      candleSeries.setMarkers(data.markers);
    }

    // RSI
    rsiSeries.setData(data.rsi);
    if (!priceLinesAdded) {
      rsiSeries.createPriceLine({
        price: 70,
        color: "#f8514966",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: "",
      });
      rsiSeries.createPriceLine({
        price: 30,
        color: "#3fb95066",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: "",
      });
    }

    // ADX
    adxSeries.setData(data.adx);
    plusDiSeries.setData(data.plus_di);
    minusDiSeries.setData(data.minus_di);
    if (!priceLinesAdded) {
      adxSeries.createPriceLine({
        price: 25,
        color: "#8b949e66",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: "",
      });
      priceLinesAdded = true;
    }
  }

  function renderSupertrend(stData) {
    // Build colored segments: split at direction changes
    // LW Charts v4 doesn't support per-point color on LineSeries,
    // so we set the series data and use the last direction's color.
    // For a better visual, we rebuild the data coloring by the dominant direction.
    const lastDir = stData[stData.length - 1].direction;
    supertrendSeries.applyOptions({
      color: lastDir === "up" ? "#3fb950" : "#f85149",
    });
    supertrendSeries.setData(
      stData.map((p) => ({ time: p.time, value: p.value }))
    );
  }

  // ── Toggles ──

  function setupToggles() {
    document.getElementById("toggle-bb").addEventListener("change", (e) => {
      visible.bb = e.target.checked;
      if (!visible.bb) {
        bbUpperSeries.setData([]);
        bbLowerSeries.setData([]);
      } else {
        fetchAndRender();
      }
    });

    document
      .getElementById("toggle-supertrend")
      .addEventListener("change", (e) => {
        visible.supertrend = e.target.checked;
        if (!visible.supertrend) {
          supertrendSeries.setData([]);
        } else {
          fetchAndRender();
        }
      });

    document.getElementById("toggle-ema").addEventListener("change", (e) => {
      visible.ema = e.target.checked;
      if (!visible.ema) {
        ema9Series.setData([]);
        ema21Series.setData([]);
      } else {
        fetchAndRender();
      }
    });
  }

  // ── Init ──

  function init() {
    createCharts();
    setupToggles();
    fetchAndRender();
    refreshTimer = setInterval(fetchAndRender, REFRESH_MS);
  }

  // Wait for LightweightCharts to be available
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
